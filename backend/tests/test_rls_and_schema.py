"""Row Level Security and schema-level guarantees, tested with real Postgres roles."""

import psycopg
import pytest

from app.demo.dataset import generate_demo_history
from app.ledger import signed_amount
from app.services.categorization import Categorizer
from app.services.demo_service import ensure_analytics
from tests.conftest import DEMO_ACCOUNT, DEMO_USER, make_user

TABLES = [
    "financial_accounts", "transactions", "category_rules", "financial_cycles", "monthly_savings_targets",
    "budgets", "recurring_payments", "financial_insights", "agent_alerts", "agent_conversations",
    "agent_messages", "data_sources", "consents", "financial_goals", "goal_contributions", "monthly_summaries",
    "monthly_summary_actions",
]


def as_user(conn, uid, role="authenticated"):
    conn.execute(f"set local role {role}")
    conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (uid or "",))


def test_rls_is_enabled_on_every_table(conn):
    rows = conn.execute(
        "select relname, relrowsecurity from pg_class where relnamespace = 'public'::regnamespace and relname = any(%s)",
        (TABLES + ["users"],),
    ).fetchall()
    assert len(rows) == len(TABLES) + 1 and all(r["relrowsecurity"] for r in rows)


@pytest.mark.parametrize("table", TABLES)
def test_a_user_only_sees_their_own_rows(conn, table):
    conn.execute("insert into agent_conversations (user_id, title) values (%s, 'c')", (DEMO_USER,))
    ensure_analytics(conn, DEMO_USER, DEMO_ACCOUNT)  # alerts/insights are generated on first dashboard load
    other = make_user(conn)
    conn.commit()
    as_user(conn, DEMO_USER)
    mine = conn.execute(f"select count(*) as n from {table}").fetchone()["n"]
    conn.rollback()
    as_user(conn, other)
    theirs = conn.execute(f"select count(*) as n from {table}").fetchone()["n"]
    conn.rollback()
    as_user(conn, None)
    nobody = conn.execute(f"select count(*) as n from {table}").fetchone()["n"]
    conn.rollback()
    assert theirs == 0 and nobody == 0
    if table not in ("category_rules", "agent_messages"):  # empty in the seed
        assert mine > 0, f"demo user should see their own {table}"


def test_users_table_is_isolated_too(conn):
    other = make_user(conn)
    conn.commit()
    as_user(conn, other)
    assert conn.execute("select count(*) as n from users").fetchone()["n"] == 1  # only themselves
    conn.rollback()


@pytest.mark.parametrize("table,stmt", [
    ("transactions", "delete from transactions"),
    ("transactions", "update transactions set amount = 1"),
    ("financial_accounts", "update financial_accounts set current_balance = 999999"),
    ("budgets", "insert into budgets (user_id, category, amount) values (auth.uid(), 'Food', 1)"),
])
def test_clients_cannot_write_directly(conn, table, stmt):
    as_user(conn, DEMO_USER)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(stmt)
    conn.rollback()


def test_anon_role_has_no_access(conn):
    conn.commit()
    as_user(conn, DEMO_USER, role="anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("select * from transactions")
    conn.rollback()


def test_realtime_publication_includes_the_ledger_tables(conn):
    tables = {r["tablename"] for r in conn.execute("select tablename from pg_publication_tables where pubname = 'supabase_realtime'").fetchall()}
    assert {"transactions", "financial_accounts", "financial_cycles", "agent_alerts", "financial_insights", "financial_goals",
            "goal_contributions", "monthly_summaries", "monthly_summary_actions"} <= tables


def test_sql_signed_amount_matches_the_python_engine(conn):
    rows = conn.execute("select transaction_type, amount, signed_amount, metadata from transactions").fetchall()
    assert len(rows) == 236
    for r in rows:
        assert r["signed_amount"] == signed_amount(r["transaction_type"], r["amount"], r["metadata"])
    conn.execute(
        """insert into transactions (user_id, account_id, "timestamp", description, amount, transaction_type, source, metadata)
           select user_id, id, now(), 'other credit', 10, 'OTHER', 'manual', '{"direction":"credit"}' from financial_accounts limit 1"""
    )
    assert conn.execute("select signed_amount from transactions where description = 'other credit'").fetchone()["signed_amount"] == 10


def test_database_rejects_non_positive_amounts_and_unknown_types(conn):
    base = """insert into transactions (user_id, account_id, "timestamp", description, amount, transaction_type, source)
              select user_id, id, now(), 'x', %s, %s, 'manual' from financial_accounts limit 1"""
    for amount, ttype in [(-5, "EXPENSE"), (0, "EXPENSE"), (5, "BOGUS")]:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(base, (amount, ttype))
        conn.rollback()


def test_only_one_active_cycle_per_account(conn):
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            """insert into financial_cycles (user_id, account_id, start_at, status)
               select user_id, account_id, now(), 'ACTIVE' from financial_cycles where status = 'ACTIVE' limit 1"""
        )
    conn.rollback()


def test_rules_agree_with_the_seed_categories_so_bank_connect_matches_the_seed(conn):
    """A user who clicks Connect Demo Bank goes through the categorizer; it must reproduce the seed's categories."""
    cat = Categorizer(conn, DEMO_USER, llm_budget=0)
    mismatches = []
    for r in generate_demo_history():
        got = cat.categorize(r.description, r.merchant, r.transaction_type, r.category, r.subcategory)
        if got.category != r.category:
            mismatches.append((r.merchant, r.category, got.category))
    assert not mismatches, mismatches[:5]
