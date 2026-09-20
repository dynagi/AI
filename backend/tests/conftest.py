"""Test fixtures.

Integration tests need a real PostgreSQL. Point TEST_ADMIN_DSN at any Postgres server you can create
databases on (default: postgresql://postgres@localhost:54329/postgres):

    export TEST_ADMIN_DSN=postgresql://postgres:postgres@localhost:54322/postgres   # `supabase start`

A template database (Supabase stub + all migrations + demo seed) is built once per session and cloned for
every test, so tests never see each other's writes. If no server is reachable the DB tests are skipped.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
ADMIN_DSN = os.environ.get("TEST_ADMIN_DSN", "postgresql://postgres@localhost:54329/postgres")
TEMPLATE = "finpilot_pytest_template"

DEMO_USER = "a1b2c3d4-0000-4000-8000-000000000001"
DEMO_ACCOUNT = "a1b2c3d4-0000-4000-8000-0000000000a1"

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-test-secret-test-secret-123456")
os.environ["GEMINI_API_KEY"] = ""  # tests must never call a real LLM


def _dsn_for(db: str) -> str:
    base, _, _ = ADMIN_DSN.rpartition("/")
    return f"{base}/{db}"


def _run_files(dsn: str, files: list[Path]) -> None:
    with psycopg.connect(dsn, autocommit=True) as c:
        for f in files:
            c.execute(f.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def template_db():
    try:
        admin = psycopg.connect(ADMIN_DSN, autocommit=True)
    except Exception as exc:  # no server
        pytest.skip(f"PostgreSQL not reachable at TEST_ADMIN_DSN ({exc})")
    admin.execute(f"drop database if exists {TEMPLATE} with (force)")
    admin.execute(f"create database {TEMPLATE}")
    dsn = _dsn_for(TEMPLATE)
    _run_files(dsn, [ROOT / "backend" / "tests" / "sql" / "supabase_stub.sql"])
    # A stand-in for Supabase's realtime publication so migration 015 has something to attach to.
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("create publication supabase_realtime")
    _run_files(dsn, sorted((ROOT / "supabase" / "migrations").glob("*.sql")))
    seeds = ["demo_user", "demo_account", "demo_cycles", "demo_transactions", "demo_goals", "demo_budgets", "demo_summaries"]
    _run_files(dsn, [ROOT / "supabase" / "seed" / f"{n}.sql" for n in seeds])
    yield TEMPLATE
    admin.execute(f"drop database if exists {TEMPLATE} with (force)")
    admin.close()


@pytest.fixture()
def dsn(template_db):
    name = f"finpilot_t_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f"create database {name} template {template_db}")
    yield _dsn_for(name)
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f"drop database if exists {name} with (force)")


@pytest.fixture()
def conn(dsn):
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        yield c


def make_user(conn, email: str | None = None) -> str:
    """Create a Supabase-style auth user (the trigger creates the profile row)."""
    uid = str(uuid.uuid4())
    email = email or f"user-{uid[:8]}@example.test"
    conn.execute(
        """insert into auth.users (instance_id, id, aud, role, email, raw_app_meta_data, raw_user_meta_data, created_at, updated_at)
           values ('00000000-0000-0000-0000-000000000000', %s, 'authenticated', 'authenticated', %s, '{}', '{}', now(), now())""",
        (uid, email),
    )
    return uid


@pytest.fixture(autouse=True)
def _frozen_wall_clock(monkeypatch):
    """Cycle maths treats 'now' as max(wall clock, latest ledger entry). Freezing the wall clock in the past makes 'now'
    always the latest ledger entry, so results never depend on the day the tests are run."""
    import app.services.cycle_state as cs
    from datetime import datetime as _dt, timezone as _tz

    class _Frozen(_dt):
        @classmethod
        def now(cls, tz=None):
            v = _dt(2026, 1, 1, tzinfo=_tz.utc)
            return v.astimezone(tz) if tz else v.replace(tzinfo=None)

    monkeypatch.setattr(cs, "datetime", _Frozen)
