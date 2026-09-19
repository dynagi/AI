"""CSV adapter: turns a CSV file into RawTransactions for the shared ingest pipeline.

Accepted columns (case/spacing-insensitive, common aliases understood):

  date | timestamp | datetime   required
  description | narration       required
  amount                        required (positive, or signed)
  merchant | payee              optional
  type | transaction_type       optional (see below)
  category, source, currency    optional

`type` may be an exact ledger type (SALARY, EXPENSE, TRANSFER_IN, ...) or a
loose word from the older FinPilot demo CSV: income, expense, transfer,
credit/debit. Loose types are resolved deterministically:

  expense / debit                       -> EXPENSE
  income / credit                       -> SALARY if it says salary, REFUND if it says refund,
                                           INTEREST if interest, TRANSFER_IN if "received from"/transfer,
                                           otherwise OTHER_INCOME
  transfer                              -> TRANSFER_IN if it looks incoming, else TRANSFER_OUT
  (no type)                             -> negative amount = EXPENSE, positive = as "income" above

A date without a time is placed at 09:00 in the app timezone. Each row gets a
stable external id, so importing the same file twice never duplicates rows.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.providers.base import ConsentRequest, DataSession, FinancialDataProvider, RawTransaction
from app.ledger import TRANSACTION_TYPES

ALIASES = {
    "timestamp": ["timestamp", "datetime", "date", "time", "transactiondate", "valuedate"],
    "description": ["description", "narration", "details", "remarks", "particulars"],
    "merchant": ["merchant", "payee", "name", "counterparty"],
    "amount": ["amount", "value"],
    "type": ["type", "transactiontype", "txntype", "drcr"],
    "category": ["category"],
    "currency": ["currency"],
}

DATE_FORMATS = ["%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y", "%d-%m-%Y %H:%M", "%d %b %Y", "%d %B %Y", "%m/%d/%Y"]


def _norm(h: str) -> str:
    return re.sub(r"[^a-z]", "", h.lower())


def _parse_timestamp(text: str, tz: ZoneInfo) -> datetime:
    text = text.strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        has_time = len(text) > 10
    except ValueError:
        dt, has_time = None, False
        for fmt in DATE_FORMATS:
            try:
                dt = datetime.strptime(text, fmt)
                has_time = "%H" in fmt
                break
            except ValueError:
                continue
        if dt is None:
            raise ValueError(f"unrecognised date {text!r}")
    if not has_time:
        dt = datetime.combine(dt.date(), time(9, 0, 0))
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def _resolve_type(raw_type: Optional[str], amount: Decimal, text: str) -> str:
    t = (raw_type or "").strip().upper().replace(" ", "_")
    low = text.lower()
    if t in TRANSACTION_TYPES:
        return t
    incoming = amount > 0 if raw_type is None or t == "" else True

    def credit() -> str:
        if "salary" in low or "payroll" in low:
            return "SALARY"
        if "refund" in low or "reversal" in low:
            return "REFUND"
        if "interest" in low:
            return "INTEREST"
        if re.search(r"received from|money received|from [a-z]+|transfer in|upi.*from", low):
            return "TRANSFER_IN"
        return "OTHER_INCOME"

    if t in ("EXPENSE", "DEBIT", "DR", "WITHDRAWAL"):
        return "EXPENSE"
    if t in ("INCOME", "CREDIT", "CR", "DEPOSIT"):
        return credit()
    if t in ("TRANSFER", "TRANSFERS"):
        # Direction decides whether the balance goes up or down, so it is never guessed.
        if re.search(r"received|money from|from [a-z]|credit|incoming|deposit", low):
            return "TRANSFER_IN"
        if re.search(r"\bto\b|sent|paid|own savings|outgoing|debit|withdraw|sweep", low) or amount < 0:
            return "TRANSFER_OUT"
        raise ValueError("cannot tell whether this transfer is incoming or outgoing; use type TRANSFER_IN or TRANSFER_OUT")
    if t == "":
        return "EXPENSE" if amount < 0 else credit()
    raise ValueError(f"unknown type {raw_type!r}")


def parse_csv(text: str) -> tuple[list[RawTransaction], list[str]]:
    tz = ZoneInfo(get_settings().app_timezone)
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        return [], ["The file is empty or has no header row."]

    by_norm = {_norm(h): h for h in reader.fieldnames}

    def col(key: str) -> Optional[str]:
        for alias in ALIASES[key]:
            if alias in by_norm:
                return by_norm[alias]
        return None

    c_ts, c_desc, c_amt = col("timestamp"), col("description"), col("amount")
    missing = [n for n, c in (("date/timestamp", c_ts), ("description", c_desc), ("amount", c_amt)) if c is None]
    if missing:
        return [], [f"Missing required column(s): {', '.join(missing)}. Found: {', '.join(reader.fieldnames)}."]
    c_merchant, c_type, c_cat, c_cur = col("merchant"), col("type"), col("category"), col("currency")

    out: list[RawTransaction] = []
    errors: list[str] = []
    seen: dict[str, int] = {}
    for n, row in enumerate(reader, start=2):
        try:
            ts = _parse_timestamp(row[c_ts] or "", tz)
            desc = (row[c_desc] or "").strip()
            if not desc:
                raise ValueError("description is empty")
            try:
                signed = Decimal(re.sub(r"[₹,\s]|rs\.?", "", (row[c_amt] or ""), flags=re.I))
            except InvalidOperation:
                raise ValueError(f"invalid amount {row[c_amt]!r}")
            if signed == 0:
                raise ValueError("amount is zero")
            merchant = (row.get(c_merchant) or "").strip() or None if c_merchant else None
            raw_type = row.get(c_type) if c_type else None
            ttype = _resolve_type(raw_type, signed, f"{desc} {merchant or ''} {row.get(c_cat) or '' if c_cat else ''}")
            fingerprint = f"{ts.isoformat()}|{desc}|{abs(signed)}|{ttype}"
            seen[fingerprint] = seen.get(fingerprint, 0) + 1
            ext = "csv-" + hashlib.sha1(f"{fingerprint}|{seen[fingerprint]}".encode()).hexdigest()[:20]
            out.append(
                RawTransaction(
                    timestamp=ts, description=desc, merchant=merchant, amount=abs(signed), transaction_type=ttype,
                    category=(row.get(c_cat) or "").strip() or None if c_cat else None,
                    currency=((row.get(c_cur) or "INR").strip() or "INR") if c_cur else "INR",
                    external_id=ext,
                )
            )
        except ValueError as exc:
            errors.append(f"Row {n}: {exc}")
    return out, errors


class CsvProvider(FinancialDataProvider):
    id = "csv"
    label = "CSV Import"
    is_sandbox = False
    source_tag = "csv"

    def create_consent_request(self, *a, **k) -> ConsentRequest:
        raise NotImplementedError

    def get_consent_status(self, external_ref: str) -> str:
        return "APPROVED"

    def create_data_session(self, external_ref: str) -> DataSession:
        raise NotImplementedError

    def get_data_session(self, session_id: str) -> DataSession:
        raise NotImplementedError

    def fetch_transactions(self, account_ref: str, from_date: Optional[date] = None, to_date: Optional[date] = None) -> list[RawTransaction]:
        return []

    def disconnect_account(self, account_ref: str) -> None:
        return None

    def refresh_data(self, account_ref: str) -> list[RawTransaction]:
        return []
