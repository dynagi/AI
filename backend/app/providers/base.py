"""Financial data provider abstraction.

Every way of getting transactions into FinPilot (Demo Bank, an Account
Aggregator, manual entry, CSV) implements FinancialDataProvider and emits
RawTransaction objects. Those are turned into normalized ledger rows by the
Transaction Normalizer and written by the Transaction Service, so the AI agent
and the analytics never know or care where a transaction came from.

    Data Provider -> Transaction Normalizer -> Transaction Service -> Supabase -> AI Agent
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional


@dataclass
class RawTransaction:
    """What a provider hands over, before normalization/categorization."""

    timestamp: datetime  # timezone-aware
    description: str
    amount: Decimal  # positive magnitude
    transaction_type: str  # SALARY | OTHER_INCOME | TRANSFER_IN | TRANSFER_OUT | EXPENSE | REFUND | INTEREST | OTHER
    merchant: Optional[str] = None
    category: Optional[str] = None  # hint from the source; the categorizer decides the final value
    subcategory: Optional[str] = None
    external_id: Optional[str] = None  # used for de-duplication
    currency: str = "INR"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConsentRequest:
    consent_id: str
    external_ref: str
    status: str  # PENDING | APPROVED | REJECTED | EXPIRED | REVOKED
    purpose: str
    from_date: date
    to_date: date
    fetch_frequency: str
    account_label: str
    is_sandbox: bool


@dataclass
class DataSession:
    session_id: str
    status: str  # PENDING | READY | FAILED
    account_ref: str


class FinancialDataProvider(ABC):
    id: str
    label: str
    is_sandbox: bool
    source_tag: str  # value stored in transactions.source (demo | bank | manual | csv | statement)

    @abstractmethod
    def create_consent_request(self, user_id: str, purpose: str, from_date: date, to_date: date, fetch_frequency: str) -> ConsentRequest: ...

    @abstractmethod
    def get_consent_status(self, external_ref: str) -> str: ...

    @abstractmethod
    def create_data_session(self, external_ref: str) -> DataSession: ...

    @abstractmethod
    def get_data_session(self, session_id: str) -> DataSession: ...

    @abstractmethod
    def fetch_transactions(self, account_ref: str, from_date: Optional[date] = None, to_date: Optional[date] = None) -> list[RawTransaction]: ...

    @abstractmethod
    def disconnect_account(self, account_ref: str) -> None: ...

    @abstractmethod
    def refresh_data(self, account_ref: str) -> list[RawTransaction]: ...
