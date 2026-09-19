"""Manual entry provider.

A manual transaction is not a second-class citizen: it becomes a RawTransaction
and goes through exactly the same normalizer, ledger and analytics as a bank
transaction. There is no consent or data-session concept (the user is the source).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from app.providers.base import ConsentRequest, DataSession, FinancialDataProvider, RawTransaction


class ManualProvider(FinancialDataProvider):
    id = "manual"
    label = "Manual Transactions"
    is_sandbox = False
    source_tag = "manual"

    def create_consent_request(self, *a, **k) -> ConsentRequest:
        raise NotImplementedError("Manual entry does not use consent")

    def get_consent_status(self, external_ref: str) -> str:
        return "APPROVED"

    def create_data_session(self, external_ref: str) -> DataSession:
        raise NotImplementedError("Manual entry does not use data sessions")

    def get_data_session(self, session_id: str) -> DataSession:
        raise NotImplementedError("Manual entry does not use data sessions")

    def fetch_transactions(self, account_ref: str, from_date: Optional[date] = None, to_date: Optional[date] = None) -> list[RawTransaction]:
        return []  # manual data is pushed in, never pulled

    def disconnect_account(self, account_ref: str) -> None:
        return None

    def refresh_data(self, account_ref: str) -> list[RawTransaction]:
        return []

    @staticmethod
    def build(
        *, transaction_type: str, amount: Decimal, timestamp: datetime, merchant: Optional[str] = None,
        description: Optional[str] = None, category: Optional[str] = None,
    ) -> RawTransaction:
        text = (description or "").strip() or (merchant or "").strip() or transaction_type.title()
        return RawTransaction(
            timestamp=timestamp, description=text, merchant=merchant, amount=amount,
            transaction_type=transaction_type, category=category,
        )
