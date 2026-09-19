"""Supabase Auth JWT verification.

The browser signs in with Supabase Auth and sends its access token as `Authorization: Bearer <jwt>`.
This module verifies the token and returns the user id; that id (never anything from the request body)
scopes every query the backend makes.

  * Legacy projects sign with a shared HS256 secret  -> set SUPABASE_JWT_SECRET
  * Newer projects sign asymmetrically (ES256/RS256) -> set SUPABASE_URL; keys come from the project's JWKS
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient

from app.config import get_settings


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: Optional[str]


@lru_cache(maxsize=2)
def _jwks(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=3600)


def verify_token(token: str) -> AuthUser:
    s = get_settings()
    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
        if alg == "HS256":
            if not s.supabase_jwt_secret:
                raise HTTPException(503, "Authentication is not configured on the server (SUPABASE_JWT_SECRET).")
            claims = jwt.decode(token, s.supabase_jwt_secret, algorithms=["HS256"], audience=s.supabase_jwt_audience)
        elif alg in ("ES256", "RS256", "EdDSA"):
            if not s.supabase_url:
                raise HTTPException(503, "Authentication is not configured on the server (SUPABASE_URL).")
            key = _jwks(f"{s.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json").get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=[alg], audience=s.supabase_jwt_audience)
        else:
            raise HTTPException(401, "Unsupported token algorithm.")
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid authentication token.")

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(401, "Invalid authentication token.")
    return AuthUser(id=str(sub), email=claims.get("email"))


def bearer_user(request: Request) -> AuthUser:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Please sign in to continue.")
    return verify_token(token)
