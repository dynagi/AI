"""Structured logging that never records financial payloads or secrets."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("finpilot")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

_SENSITIVE = {"password", "secret", "token", "api_key", "apikey", "authorization", "otp", "pin", "jwt"}


def log_event(event: str, **data) -> None:
    safe = {k: ("[redacted]" if k.lower() in _SENSITIVE else v) for k, v in data.items()}
    logger.info(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "event": event, **safe}, default=str))
