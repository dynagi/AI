"""The spec's accounting scenarios, run end to end against real PostgreSQL with the seeded demo data."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.demo.dataset import DEMO_NEXT_SALARY_TIME
from app.services import queries
from app.services.comparison import compare_cycles, progress_vs_previous, cycle_summary
from app.services.cycle_state import get_target, savings_progress_for, set_target
from app.services.dashboard import build_dashboard
from app.services.demo_service import ensure_analytics, reset_simulated, simulate_transaction
from app.services.accounts import create_manual_account
from app.services.ingest import ingest
from app.providers.manual import ManualProvider
from tests.conftest import DEMO_ACCOUNT, DEMO_USER, make_user

D = Decimal
IST = timezone(timedelta(hours=5, minutes=30))


def sim(conn, ttype, amount, **kw):
    return simulate_transaction(conn, user_id=DEMO_USER, account_id=DEMO_ACCOUNT, transaction_type=ttype, amount=D(str(amount)), **kw)


def dash(conn):
    return build_dashboard(conn, DEMO_USER)


def snapshot(conn):
    rows = conn.execute(
        "select id, balance_after, financial_cycle_id, amount, transaction_type from transactions where user_id = %s", (DEMO_USER,)
    ).fetchall()
    return {str(r["id"]): (r["balance_after"], str(r["financial_cycle_id"]), r["amount"], r["transaction_type"]) for r in rows}


def test_seed_is_consistent_and_rebuild_is_a_no_op(conn):
    from app.services.ledger_service import rebuild_account

    before = snapshot(conn)
    rebuild_account(conn, DEMO_USER, DEMO_ACCOUNT)
    assert snapshot(conn) == before
    d = dash(conn)
    assert d["account"]["current_balance"] == D("35000.00")
    assert d["cycle"]["status"] == "ACTIVE"
    assert d["cycle"]["expenses"] == D("42500.00")


def test_opening_balance_is_not_income_for_a_new_account(conn):
    uid = make_user(conn)
    acct = create_manual_account(conn, uid, "My Account", D("35000"))
    assert build_dashboard(conn, uid)["cycle"] is None  # no cycle until money moves
    ingest(conn, user_id=uid, account_id=str(acct["id"]), source="manual",
           raws=[ManualProvider.build(transaction_type="EXPENSE", amount=D("100"), timestamp=datetime(2026, 9, 1, 10, 0, tzinfo=IST), merchant="Cafe")])
    d = build_dashboard(conn, uid)
    assert d["account"]["current_balance"] == D("34900.00")
    assert d["cycle"]["income"] == D("0.00")  # the 35,000 already in the account is not income
    assert d["cycle"]["expenses"] == D("100.00")


def test_success_scenario_end_to_end(conn):
    """The spec's headline flow: salary -> expense -> transfer in -> target -> 6,000 expense."""
    prev_expenses_before = dash(conn)["cycle"]["expenses"]
    assert prev_expenses_before == D("42500.00")

    # 1. Credit salary at exactly 30 Sep 2026 11:27:04
    s = sim(conn, "SALARY", 100000)
    assert s.new_cycle_started
    d = dash(conn)
    assert d["account"]["current_balance"] == D("135000.00")
    assert d["cycle"]["income"] == D("100000.00")
    assert d["cycle"]["expenses"] == D("0.00")
    assert d["cycle"]["opening_balance"] == D("135000.00")
    assert d["cycle"]["carried_over_balance"] == D("35000.00")
    assert d["cycle"]["start_at"] == DEMO_NEXT_SALARY_TIME
    assert d["previous_cycle"]["expenses"] == D("42500.00")
    assert d["previous_cycle"]["status"] == "CLOSED"
    assert d["savings"]["needs_target"] is True
    assert any(a["alert_type"] == "NEW_CYCLE" for a in d["alerts"])
    assert any(a["alert_type"] == "SAVINGS_TARGET_NEEDED" for a in d["alerts"])

    # 2. Add Expense 160 (Swiggy) at 11:35
    sim(conn, "EXPENSE", 160)
    d = dash(conn)
    assert d["account"]["current_balance"] == D("134840.00")
    assert d["cycle"]["income"] == D("100000.00")
    assert d["cycle"]["expenses"] == D("160.00")
    top = d["recent_transactions"][0]
    assert top["merchant"] == "Swiggy" and top["signed_amount"] == D("-160.00") and top["balance_after"] == D("134840.00")
    assert top["timestamp"].astimezone(IST).strftime("%H:%M") == "11:35"

    # 3. Rahul sends 1,000: balance up, salary income unchanged, other inflow shown separately
    sim(conn, "TRANSFER_IN", 1000)
    d = dash(conn)
    assert d["account"]["current_balance"] == D("135840.00")
    assert d["cycle"]["income"] == D("100000.00")
    assert d["cycle"]["other_inflows"] == D("1000.00")
    assert d["cycle"]["expenses"] == D("160.00")

    # 4. The user sets a 25,000 target (never invented for them)
    assert get_target(conn, DEMO_USER, d["cycle"]["id"]) is None
    set_target(conn, DEMO_USER, d["cycle"]["id"], D("25000"))
    d = dash(conn)
    assert d["savings"]["status"] == "ON_TRACK"
    assert d["savings"]["planned_spend_limit"] == "75000.00"
    assert d["spending_progress"]["planned_spend_limit"] == D("75000.00")

    # 5. A 6,000 expense: high-spending alert, comparison still shows the intact previous cycle
    sim(conn, "EXPENSE", 6000, merchant="Croma Electronics")
    d = dash(conn)
    assert d["cycle"]["expenses"] == D("6160.00")
    high = [a for a in d["alerts"] if a["alert_type"] == "HIGH_SPENDING"]
    assert high and "significantly above your recent daily spending average" in high[0]["message"]
    assert d["progress_vs_previous"]["previous"] == D("42500.00")
    assert d["progress_vs_previous"]["current"] == D("6160.00")
    assert d["progress_vs_previous"]["remaining"] == D("36340.00")
    assert "₹36,340" in d["progress_vs_previous"]["message"]

    # history never changed
    closed = conn.execute(
        "select expense_total from financial_cycles where user_id = %s and status = 'CLOSED' order by start_at", (DEMO_USER,)
    ).fetchall()
    assert [c["expense_total"] for c in closed] == [D(x) for x in ("38200.00", "41500.00", "39800.00", "44100.00", "46200.00", "42500.00")]


def test_savings_goal_at_risk_when_spending_exceeds_the_limit(conn):
    sim(conn, "SALARY", 100000)
    cid = dash(conn)["cycle"]["id"]
    set_target(conn, DEMO_USER, cid, D("25000"))
    sim(conn, "EXPENSE", 6000)
    assert dash(conn)["savings"]["status"] == "ON_TRACK"  # honest maths: 6,160 of 75,000 is not a risk
    sim(conn, "EXPENSE", 70000, merchant="Croma Electronics")
    d = dash(conn)
    assert d["savings"]["status"] == "AT_RISK" and d["savings"]["reason"] == "limit_exceeded"
    risk = [a for a in d["alerts"] if a["alert_type"] == "SAVINGS_AT_RISK"]
    assert risk and "no longer possible" in risk[0]["message"]
    assert risk[0]["evidence"]["net_spend"] == "76000.00"


def test_expense_before_salary_belongs_to_previous_cycle(conn):
    sal = DEMO_NEXT_SALARY_TIME
    sim(conn, "EXPENSE", 500, timestamp=sal - timedelta(minutes=1))
    sim(conn, "SALARY", 100000)
    sim(conn, "EXPENSE", 160, timestamp=sal + timedelta(minutes=8))
    cycles = queries.list_cycles(conn, DEMO_USER, DEMO_ACCOUNT)  # newest first
    cur, prev = cycles[0], cycles[1]
    assert prev["expense_total"] == D("43000.00") and prev["end_at"] == sal
    assert cur["expense_total"] == D("160.00") and cur["start_at"] == sal


def test_backdated_manual_entry_recomputes_balances_and_cycles(conn):
    sim(conn, "SALARY", 100000)
    sim(conn, "EXPENSE", 160)
    # A CSV/manual entry dated before the salary must land in the previous cycle and shift later balances.
    old = DEMO_NEXT_SALARY_TIME - timedelta(days=3)
    ingest(conn, user_id=DEMO_USER, account_id=DEMO_ACCOUNT, source="manual",
           raws=[ManualProvider.build(transaction_type="EXPENSE", amount=D("500"), timestamp=old, merchant="Restaurant")])
    d = dash(conn)
    assert d["account"]["current_balance"] == D("134340.00")
    assert d["cycle"]["expenses"] == D("160.00")
    assert d["previous_cycle"]["expenses"] == D("43000.00")


def test_manual_transaction_behaves_like_a_bank_transaction(conn):
    sim(conn, "SALARY", 100000)
    ingest(conn, user_id=DEMO_USER, account_id=DEMO_ACCOUNT, source="manual",
           raws=[ManualProvider.build(transaction_type="EXPENSE", amount=D("500"), timestamp=DEMO_NEXT_SALARY_TIME + timedelta(hours=1), merchant="Restaurant")])
    d = dash(conn)
    assert d["account"]["current_balance"] == D("134500.00")
    assert d["cycle"]["expenses"] == D("500.00")
    assert d["recent_transactions"][0]["source"] == "manual"


def test_duplicate_external_ids_are_ignored(conn):
    from app.providers.base import RawTransaction

    raw = RawTransaction(timestamp=DEMO_NEXT_SALARY_TIME + timedelta(hours=2), description="X", amount=D("10"), transaction_type="EXPENSE", external_id="dup-1")
    a = ingest(conn, user_id=DEMO_USER, account_id=DEMO_ACCOUNT, source="manual", raws=[raw])
    b = ingest(conn, user_id=DEMO_USER, account_id=DEMO_ACCOUNT, source="manual", raws=[raw])
    assert (a.inserted, a.duplicates) == (1, 0) and (b.inserted, b.duplicates) == (0, 1)


def test_comparison_current_vs_previous(conn):
    sim(conn, "SALARY", 100000)
    sim(conn, "EXPENSE", 6160, merchant="Amazon")
    cycles = queries.list_cycles(conn, DEMO_USER, DEMO_ACCOUNT)
    cmp = compare_cycles(conn, DEMO_USER, cycles[1], cycles[0])
    assert cmp["a"]["expenses"] == D("42500.00") and cmp["b"]["expenses"] == D("6160.00")
    assert cmp["expense_difference"] == D("-36340.00")
    assert cmp["expense_change_percent"] == pytest.approx(-85.5, abs=0.05)
    cats = {c["category"] for c in cmp["category_changes"]}
    assert "Shopping" in cats
    assert "Insurance" not in cats and "EMI/Loans" not in cats  # no such spending in the data => never shown
    assert cmp["explanation"] and "lower" in cmp["explanation"][0]


def test_no_categories_without_transactions_and_no_invented_insights(conn):
    d = dash(conn)
    cats = {c["category"] for c in d["cycle"]["categories"]}
    assert not cats & {"Insurance", "EMI/Loans", "Investment", "Education", "Travel"}
    ensure_analytics(conn, DEMO_USER, DEMO_ACCOUNT)
    text = " ".join(i["message"] + i["title"] for i in dash(conn)["insights"]) + " ".join(a["message"] for a in dash(conn)["alerts"])
    assert "Insurance" not in text and "EMI" not in text
    for i in dash(conn)["insights"]:
        assert i["evidence"], f"insight without evidence: {i['title']}"


def test_seed_unusual_spending_and_threshold_alerts_reference_real_data(conn):
    ensure_analytics(conn, DEMO_USER, DEMO_ACCOUNT)
    d = dash(conn)
    types = {a["alert_type"] for a in d["alerts"]}
    assert "CATEGORY_SPIKE" in types  # healthcare 8,699 vs ~2,666 average
    assert "PREVIOUS_CYCLE_THRESHOLD" in types  # 42,500 is 92% of 46,200
    spike = next(a for a in d["alerts"] if a["alert_type"] == "CATEGORY_SPIKE")
    assert spike["evidence"]["category"] == "Healthcare" and spike["evidence"]["top_transaction_ids"]
    assert any(a["alert_type"] == "BUDGET_THRESHOLD" and a["evidence"]["category"] == "Food" for a in d["alerts"])
    assert d["recurring"]["count"] == 7


def test_demo_reset_removes_only_simulated_rows(conn):
    before = snapshot(conn)
    sim(conn, "SALARY", 100000)
    sim(conn, "EXPENSE", 160)
    res = reset_simulated(conn, DEMO_USER, DEMO_ACCOUNT)
    assert res["removed"] == 2
    assert snapshot(conn) == before
    assert dash(conn)["cycle"]["status"] == "ACTIVE" and dash(conn)["account"]["current_balance"] == D("35000.00")
