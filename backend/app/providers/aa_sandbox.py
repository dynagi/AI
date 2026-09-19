"""Account Aggregator SANDBOX adapter (Setu FIU sandbox).

Implements the same FinancialDataProvider interface as the Demo Bank, so the
ledger, analytics and AI agent are untouched when it is enabled.

  * Sandbox only. Never used with real bank credentials.
  * Credentials come only from environment variables (SETU_CLIENT_ID,
    SETU_CLIENT_SECRET, SETU_PRODUCT_INSTANCE_ID) and are never logged.
  * Inactive until configured: every call raises a clear "not configured" error.
    It never silently falls back to mock data.
  * Production AA access needs onboarding/certification with the AA ecosystem. This adapter
    does not pretend otherwise. The request/response mapping below follows the sandbox's
    consent -> data session -> fetch flow and must be verified against Setu's current API
    reference and sandbox credentials before relying on it.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

from app.config import get_settings
from app.logging_utils import log_event
from app.providers.base import ConsentRequest, DataSession, FinancialDataProvider, RawTransaction


class AASandboxNotConfigured(RuntimeError):
    pass


class AASandboxProvider(FinancialDataProvider):
    id = "aa_sandbox"
    label = "Account Aggregator Sandbox (Setu)"
    is_sandbox = True
    source_tag = "bank"

    def _cfg(self):
        s = get_settings()
        if not (s.setu_client_id and s.setu_client_secret and s.setu_product_instance_id):
            raise AASandboxNotConfigured(
                "The Account Aggregator sandbox is not configured. Set SETU_CLIENT_ID, SETU_CLIENT_SECRET and "
                "SETU_PRODUCT_INSTANCE_ID to enable it."
            )
        return s

    def _client(self) -> httpx.Client:
        s = self._cfg()
        return httpx.Client(
            base_url=s.setu_base_url, timeout=20,
            headers={
                "x-client-id": s.setu_client_id, "x-client-secret": s.setu_client_secret,
                "x-product-instance-id": s.setu_product_instance_id, "Content-Type": "application/json",
            },
        )

    @staticmethod
    def is_configured() -> bool:
        s = get_settings()
        return bool(s.setu_client_id and s.setu_client_secret and s.setu_product_instance_id)

    def create_consent_request(self, user_id, purpose, from_date, to_date, fetch_frequency) -> ConsentRequest:
        with self._client() as c:
            r = c.post("/consents", json={
                "consentDuration": {"unit": "MONTH", "value": "12"},
                "dataRange": {"from": from_date.isoformat(), "to": to_date.isoformat()},
                "consentTypes": ["TRANSACTIONS", "PROFILE", "SUMMARY"], "fiTypes": ["DEPOSIT"],
                "Purpose": {"code": "101", "text": purpose},
                "fetchType": "ONETIME" if fetch_frequency == "on-demand" else "PERIODIC",
                "vua": f"{user_id}@finpilot-sandbox",
            })
            r.raise_for_status()
            body = r.json()
        log_event("consent.created", provider=self.id, user_id=user_id)
        return ConsentRequest(
            consent_id=body["id"], external_ref=body["id"], status="PENDING", purpose=purpose, from_date=from_date,
            to_date=to_date, fetch_frequency=fetch_frequency, account_label=self.label, is_sandbox=True,
        )

    def get_consent_status(self, external_ref: str) -> str:
        with self._client() as c:
            r = c.get(f"/consents/{external_ref}")
            if r.status_code >= 400:
                return "EXPIRED"
            status = (r.json().get("status") or "").upper()
        return {"ACTIVE": "APPROVED", "REJECTED": "REJECTED", "EXPIRED": "EXPIRED", "REVOKED": "REVOKED"}.get(status, "PENDING")

    def create_data_session(self, external_ref: str) -> DataSession:
        with self._client() as c:
            r = c.post("/sessions", json={"consentId": external_ref, "format": "json"})
            r.raise_for_status()
            sid = r.json()["id"]
        log_event("data_session.created", provider=self.id, session_id=sid)
        return DataSession(session_id=sid, status="PENDING", account_ref=sid)

    def get_data_session(self, session_id: str) -> DataSession:
        with self._client() as c:
            r = c.get(f"/sessions/{session_id}")
            r.raise_for_status()
            status = "READY" if (r.json().get("status") or "").upper() == "COMPLETED" else "PENDING"
        return DataSession(session_id=session_id, status=status, account_ref=session_id)

    def fetch_transactions(self, account_ref: str, from_date: Optional[date] = None, to_date: Optional[date] = None) -> list[RawTransaction]:
        with self._client() as c:
            r = c.get(f"/sessions/{account_ref}")
            r.raise_for_status()
            body = r.json()
        out = []
        for t in body.get("transactions", []):
            credit = str(t.get("type", "")).upper() == "CREDIT"
            ts = datetime.fromisoformat(t["valueDate"]).replace(tzinfo=timezone.utc) if "T" in t["valueDate"] else datetime.fromisoformat(t["valueDate"] + "T09:00:00+05:30")
            narration = t.get("narration", "")
            out.append(RawTransaction(
                timestamp=ts, description=narration, amount=abs(Decimal(str(t["amount"]))),
                transaction_type=("SALARY" if "salary" in narration.lower() else "OTHER_INCOME") if credit else "EXPENSE",
                external_id=str(t["txnId"]),
            ))
        log_event("data_fetch.completed", provider=self.id, count=len(out))
        return out

    def disconnect_account(self, account_ref: str) -> None:
        with self._client() as c:
            c.delete(f"/consents/{account_ref}")
        log_event("account.disconnected", provider=self.id)

    def refresh_data(self, account_ref: str) -> list[RawTransaction]:
        return self.fetch_transactions(account_ref)
