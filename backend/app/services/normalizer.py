"""Transaction Normalizer.

Every provider's RawTransaction passes through here before it can touch the
ledger. It validates, defaults the timezone and currency, and attaches the
category. Rows that cannot be made valid are reported, never silently stored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.ledger import TRANSACTION_TYPES, money
from app.providers.base import RawTransaction
from app.services.categorization import Categorizer

VALID_SOURCES = {"demo", "bank", "manual", "csv", "statement"}


@dataclass
class NormalizedTransaction:
    timestamp: datetime
    description: str
    merchant: Optional[str]
    amount: Decimal
    currency: str
    transaction_type: str
    category: str
    subcategory: Optional[str]
    source: str
    external_id: Optional[str]
    metadata: dict[str, Any] = field(default_factory=dict)


class MalformedTransaction(ValueError):
    pass


def normalize(raw: RawTransaction, source: str, categorizer: Categorizer) -> NormalizedTransaction:
    if source not in VALID_SOURCES:
        raise MalformedTransaction(f"unknown source {source!r}")

    ttype = (raw.transaction_type or "").upper()
    if ttype not in TRANSACTION_TYPES:
        raise MalformedTransaction(f"unknown transaction type {raw.transaction_type!r}")

    try:
        amount = money(raw.amount)
    except (InvalidOperation, ValueError, TypeError):
        raise MalformedTransaction(f"invalid amount {raw.amount!r}")
    if amount <= 0:
        raise MalformedTransaction("amount must be greater than zero (direction comes from the transaction type)")

    description = (raw.description or "").strip()
    if not description:
        raise MalformedTransaction("description is required")

    ts = raw.timestamp
    if not isinstance(ts, datetime):
        raise MalformedTransaction("timestamp is required")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ZoneInfo(get_settings().app_timezone))

    merchant = (raw.merchant or "").strip() or None
    cat = categorizer.categorize(description, merchant, ttype, raw.category, raw.subcategory)

    metadata = dict(raw.metadata or {})
    metadata["categorization"] = {"method": cat.method, "confidence": cat.confidence}

    return NormalizedTransaction(
        timestamp=ts,
        description=description[:200],
        merchant=merchant[:100] if merchant else None,
        amount=amount,
        currency=(raw.currency or "INR").upper(),
        transaction_type=ttype,
        category=cat.category,
        subcategory=cat.subcategory,
        source=source,
        external_id=raw.external_id,
        metadata=metadata,
    )
