"""FastAPI dependencies: authenticated request context and rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterator

import psycopg
from fastapi import Depends, HTTPException

from app.auth import AuthUser, bearer_user
from app.db import transaction


@dataclass
class Ctx:
    user_id: str
    email: str | None
    conn: psycopg.Connection


def get_ctx(user: AuthUser = Depends(bearer_user)) -> Iterator[Ctx]:
    """One database transaction per request, committed on success and rolled back if the handler raises."""
    with transaction() as conn:
        # The auth trigger normally creates this; the upsert makes first login robust if it did not fire.
        conn.execute(
            "insert into users (id, email) values (%s, %s) on conflict (id) do nothing", (user.id, user.email)
        )
        yield Ctx(user_id=user.id, email=user.email, conn=conn)


class RateLimit:
    """Fixed-window per-user limiter (in-memory: per process; use Redis or a gateway when scaling out)."""

    def __init__(self, max_calls: int, per_seconds: int):
        self.max_calls, self.per_seconds = max_calls, per_seconds
        self.hits: dict[str, deque] = defaultdict(deque)

    def __call__(self, user: AuthUser = Depends(bearer_user)) -> None:
        now = time.monotonic()
        q = self.hits[user.id]
        while q and now - q[0] > self.per_seconds:
            q.popleft()
        if len(q) >= self.max_calls:
            raise HTTPException(429, "You're doing that too quickly. Please wait a moment and try again.")
        q.append(now)
