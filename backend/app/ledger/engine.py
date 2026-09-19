"""Deterministic ledger + financial-cycle engine.

Pure functions only: no database, no clock, no randomness. Given an account's
opening balance and every transaction on it, `rebuild` recomputes, from scratch,

  * the running balance after each transaction (`balance_after`)
  * which financial cycle each transaction belongs to
  * every cycle's totals

Recomputing the whole ledger (instead of patching incrementally) means
back-dated entries (CSV imports, manual entries with an earlier timestamp) are
handled correctly, and the result never depends on insertion order.

Rules encoded here:

  * amount is always a positive magnitude; direction comes from the type.
  * The opening balance is money that was already in the account. It is never
    income.
  * A SALARY transaction starts a new cycle AT ITS EXACT TIMESTAMP. Anything
    strictly earlier belongs to the previous cycle, anything at/after belongs
    to the new one. The previous cycle is closed, never deleted.
  * Money from other people (TRANSFER_IN) raises the balance but is NOT income.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Mapping, Optional

CENT = Decimal("0.01")

CREDIT_TYPES = frozenset({"SALARY", "OTHER_INCOME", "TRANSFER_IN", "REFUND", "INTEREST"})
DEBIT_TYPES = frozenset({"TRANSFER_OUT", "EXPENSE"})
INCOME_TYPES = frozenset({"SALARY", "OTHER_INCOME", "INTEREST"})
TRANSACTION_TYPES = CREDIT_TYPES | DEBIT_TYPES | {"OTHER"}

INITIAL_CYCLE_KEY = "initial"


def money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def is_credit(transaction_type: str, metadata: Optional[Mapping[str, Any]] = None) -> bool:
    """True when the transaction adds money to the account."""
    if transaction_type not in TRANSACTION_TYPES:
        raise ValueError(f"Unknown transaction_type: {transaction_type!r}")
    if transaction_type in CREDIT_TYPES:
        return True
    if transaction_type == "OTHER":
        return bool(metadata) and metadata.get("direction") == "credit"
    return False


def signed_amount(
    transaction_type: str, amount: Decimal, metadata: Optional[Mapping[str, Any]] = None
) -> Decimal:
    """+amount for money in, -amount for money out. Mirrors the SQL generated column."""
    amount = money(amount)
    if amount <= 0:
        raise ValueError("amount must be a positive magnitude; direction comes from transaction_type")
    return amount if is_credit(transaction_type, metadata) else -amount


@dataclass(frozen=True)
class LedgerTxn:
    id: str
    timestamp: datetime
    seq: int
    transaction_type: str
    amount: Decimal
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class TxnState:
    id: str
    balance_after: Decimal
    cycle_key: str


@dataclass
class CycleState:
    key: str  # id of the salary transaction, or INITIAL_CYCLE_KEY
    salary_transaction_id: Optional[str]
    start_at: datetime
    end_at: Optional[datetime]
    opening_balance: Decimal  # balance immediately AFTER the salary landed
    carried_over_balance: Decimal  # balance immediately BEFORE the salary (never income)
    closing_balance: Optional[Decimal] = None
    income_total: Decimal = Decimal("0.00")  # SALARY + OTHER_INCOME + INTEREST
    other_inflow_total: Decimal = Decimal("0.00")  # TRANSFER_IN
    refund_total: Decimal = Decimal("0.00")
    expense_total: Decimal = Decimal("0.00")  # gross EXPENSE only
    transaction_count: int = 0
    status: str = "ACTIVE"


@dataclass
class LedgerResult:
    txns: dict[str, TxnState]
    cycles: list[CycleState]
    final_balance: Decimal


def _sort_key(t: LedgerTxn) -> tuple:
    # A salary sorts before other transactions with the identical timestamp so it
    # is the transaction that opens the cycle.
    return (t.timestamp, 0 if t.transaction_type == "SALARY" else 1, t.seq)


def rebuild(opening_balance: Decimal, txns: Iterable[LedgerTxn]) -> LedgerResult:
    balance = money(opening_balance)
    ordered = sorted(txns, key=_sort_key)

    states: dict[str, TxnState] = {}
    cycles: list[CycleState] = []
    current: Optional[CycleState] = None

    for t in ordered:
        amount = money(t.amount)
        if t.timestamp.tzinfo is None:
            raise ValueError("Transaction timestamps must be timezone-aware")

        if t.transaction_type == "SALARY":
            carried = balance
            if current is not None:
                current.end_at = t.timestamp
                current.closing_balance = balance
                current.status = "CLOSED"
            balance = balance + amount
            current = CycleState(
                key=t.id,
                salary_transaction_id=t.id,
                start_at=t.timestamp,
                end_at=None,
                opening_balance=balance,
                carried_over_balance=carried,
            )
            cycles.append(current)
        else:
            if current is None:
                current = CycleState(
                    key=INITIAL_CYCLE_KEY,
                    salary_transaction_id=None,
                    start_at=t.timestamp,
                    end_at=None,
                    opening_balance=balance,
                    carried_over_balance=balance,
                )
                cycles.append(current)
            balance = balance + signed_amount(t.transaction_type, amount, t.metadata)

        current.transaction_count += 1
        if t.transaction_type in INCOME_TYPES:
            current.income_total += amount
        elif t.transaction_type == "TRANSFER_IN":
            current.other_inflow_total += amount
        elif t.transaction_type == "REFUND":
            current.refund_total += amount
        elif t.transaction_type == "EXPENSE":
            current.expense_total += amount

        states[t.id] = TxnState(id=t.id, balance_after=balance, cycle_key=current.key)

    return LedgerResult(txns=states, cycles=cycles, final_balance=balance)
