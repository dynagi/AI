"""PostgreSQL access (Supabase). Plain SQL through psycopg 3; there is no ORM.

The backend connects with Supabase's privileged database role, so row level security does not protect the API
path. User isolation on this path is enforced in code: every query in the service layer is scoped by the
`user_id` taken from the verified JWT, never from request input. RLS protects the other path (browsers reading
via the anon key / Realtime).

Connection: you only provide SUPABASE_URL and SUPABASE_DB_PASSWORD (and SUPABASE_REGION if needed). The
connection details are derived from the project ref, trying the direct host first and then the Supabase pooler.
DATABASE_URL, if set, overrides all of this.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Iterator, Optional
from urllib.parse import urlparse

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import Settings, get_settings
from .logging_utils import log_event

_pool: Optional[ConnectionPool] = None

HELP = (
    "Set SUPABASE_URL and SUPABASE_DB_PASSWORD in backend/.env (Project Settings > Database > Database password; "
    "reset it there if you forgot it). If the direct host does not resolve on your network (IPv4-only), also set "
    "SUPABASE_REGION to your project's region (shown on the Connect dialog, e.g. ap-south-1)."
)


def project_ref(settings: Settings) -> Optional[str]:
    if not settings.supabase_url or "YOUR-" in settings.supabase_url:
        return None
    host = urlparse(settings.supabase_url).hostname or ""
    return host.split(".")[0] or None


def connection_candidates(settings: Optional[Settings] = None) -> list[str]:
    """Ordered libpq conninfo strings to try. Uses keyword form, so passwords never need URL-encoding."""
    s = settings or get_settings()
    if s.database_url and "YOUR-" not in s.database_url:
        return [s.database_url]

    ref = project_ref(s)
    if not ref or not s.supabase_db_password:
        raise RuntimeError(f"Database is not configured. {HELP}")

    common = dict(dbname="postgres", password=s.supabase_db_password, sslmode="require", connect_timeout=8)
    direct = make_conninfo(host=f"db.{ref}.supabase.co", port=5432, user="postgres", **common)
    if not s.supabase_region:
        return [direct]
    # A known region means the direct host is not reachable from here (it is IPv6-only): try the pooler first so
    # a cold start does not wait on it. The direct host stays as the last resort.
    pooled = [
        make_conninfo(host=f"{prefix}-{s.supabase_region}.pooler.supabase.com", port=5432, user=f"postgres.{ref}", **common)
        for prefix in ("aws-0", "aws-1")  # older and newer Supabase pooler hostnames
    ]
    return pooled + [direct]


# Supabase pooler regions, most likely first for this project's users.
REGIONS = [
    "ap-south-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-northeast-2", "eu-west-1", "eu-west-2",
    "eu-west-3", "eu-central-1", "eu-central-2", "eu-north-1", "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "ca-central-1", "sa-east-1",
]


def _try(info: str) -> tuple[bool, str]:
    try:
        with psycopg.connect(info, connect_timeout=6):
            return True, ""
    except Exception as exc:
        return False, str(exc).strip().splitlines()[0][:160]


def _probe_regions(settings: Settings, ref: str) -> tuple[Optional[str], list[str]]:
    """The direct host is IPv6-only, so on IPv4 networks try the pooler in every region until one accepts us.

    A wrong region answers "tenant or user not found"; only the right one lets the password be checked.
    """
    base = dict(dbname="postgres", password=settings.supabase_db_password, sslmode="require", connect_timeout=6)
    infos = {
        (region, prefix): make_conninfo(host=f"{prefix}-{region}.pooler.supabase.com", port=5432, user=f"postgres.{ref}", **base)
        for region in REGIONS for prefix in ("aws-0", "aws-1")
    }
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda kv: (kv[0], kv[1], *_try(kv[1])), infos.items()))
    errors = []
    for (region, prefix), info, ok, err in results:
        if ok:
            log_event("db.region_detected", region=region)
            print(f"[FinPilot] Connected through the Supabase pooler in {region}. "
                  f"Add SUPABASE_REGION={region} to backend/.env to skip this search next time.")
            return info, errors
        if err and "not found" not in err.lower():
            errors.append(err)
    return None, errors


def resolve_conninfo(settings: Optional[Settings] = None) -> str:
    """The first candidate that actually connects."""
    s = settings or get_settings()
    errors: list[str] = []
    for info in connection_candidates(s):
        ok, err = _try(info)
        if ok:
            return info
        errors.append(err)

    ref = project_ref(s)
    if not s.database_url and not s.supabase_region and ref and s.supabase_db_password:
        found, probe_errors = _probe_regions(s, ref)
        if found:
            return found
        errors.extend(probe_errors)

    hint = ""
    if any("password authentication failed" in e.lower() for e in errors):
        hint = " The project was found but the database password was rejected: check SUPABASE_DB_PASSWORD (reset it in Project Settings > Database)."
    raise RuntimeError(
        "Could not connect to your Supabase database." + hint + " " + HELP + " Last errors: " + " | ".join(dict.fromkeys(errors[-3:]))
    )


def open_pool(dsn: Optional[str] = None, min_size: int = 1, max_size: int = 10) -> ConnectionPool:
    global _pool
    if _pool is None:
        target = dsn or resolve_conninfo()
        pool = ConnectionPool(
            target, min_size=min_size, max_size=max_size,
            kwargs={"row_factory": dict_row, "autocommit": False, "connect_timeout": 10}, open=True,
        )
        try:
            pool.wait(timeout=15)  # fail fast instead of retrying quietly in the background
        except Exception as exc:
            pool.close()
            raise RuntimeError("Could not open the database connection pool. " + HELP) from exc
        log_event("db.connected")
        _pool = pool
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """A connection wrapped in a single database transaction (commit on success)."""
    pool = open_pool()
    with pool.connection() as conn:  # commits on clean exit, rolls back on exception
        yield conn
