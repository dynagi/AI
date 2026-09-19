"""Apply the Supabase SQL files to your database (no Supabase CLI needed).

    python -m scripts.apply_sql migrations     # supabase/migrations/*.sql in order
    python -m scripts.apply_sql seed           # supabase/seed/demo_*.sql in dependency order
    python -m scripts.apply_sql all
    python -m scripts.apply_sql stub           # LOCAL TESTING ONLY: fake Supabase auth schema/roles

Connects using SUPABASE_URL + SUPABASE_DB_PASSWORD from backend/.env (see app/db.py). Pass --dsn to override. Migrations are idempotent (IF NOT EXISTS / guarded blocks).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import psycopg

from app.db import resolve_conninfo

ROOT = Path(__file__).resolve().parents[2]
SEED_ORDER = ["demo_user", "demo_account", "demo_cycles", "demo_transactions", "demo_targets", "demo_budgets"]


def run(dsn: str, files: list[Path]) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        for f in files:
            print(f"applying {f.relative_to(ROOT)}")
            conn.execute(f.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("what", choices=["migrations", "seed", "all", "stub"])
    p.add_argument("--dsn", default=None)
    a = p.parse_args()
    dsn = a.dsn or resolve_conninfo()

    migrations = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
    seeds = [ROOT / "supabase" / "seed" / f"{n}.sql" for n in SEED_ORDER]
    stub = [ROOT / "backend" / "tests" / "sql" / "supabase_stub.sql"]
    files = {"migrations": migrations, "seed": seeds, "all": migrations + seeds, "stub": stub}[a.what]
    run(dsn, files)
    print("done")


if __name__ == "__main__":
    main()
