"""Demo Bank (sandbox). Produces mock data only — never real banking data.

Stateless on purpose: consent status lives in our own `consents` table (written
by the API layer), not in this object, so it behaves identically across
workers and restarts.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from app.demo.dataset import generate_demo_history
from app.logging_utils import log_event
from app.providers.base import ConsentRequest, DataSession, FinancialDataProvider, RawTransaction


class DemoBankProvider(FinancialDataProvider):
    id = "demo_bank"
    label = "Demo Bank / Sandbox Account"
    is_sandbox = True
    source_tag = "demo"

    def create_consent_request(self, user_id, purpose, from_date, to_date, fetch_frequency) -> ConsentRequest:
        cid = str(uuid.uuid4())
        log_event("consent.created", provider=self.id, user_id=user_id, consent_id=cid)
        return ConsentRequest(
            consent_id=cid, external_ref=f"demo-consent-{cid[:8]}", status="PENDING", purpose=purpose,
            from_date=from_date, to_date=to_date, fetch_frequency=fetch_frequency,
            account_label=self.label, is_sandbox=True,
        )

    def get_consent_status(self, external_ref: str) -> str:
        return "APPROVED"  # authoritative status is the consents table

    def create_data_session(self, external_ref: str) -> DataSession:
        sid = str(uuid.uuid4())
        log_event("data_session.created", provider=self.id, session_id=sid)
        return DataSession(session_id=sid, status="READY", account_ref=external_ref)

    def get_data_session(self, session_id: str) -> DataSession:
        return DataSession(session_id=session_id, status="READY", account_ref=session_id)

    def fetch_transactions(self, account_ref: str, from_date: Optional[date] = None, to_date: Optional[date] = None) -> list[RawTransaction]:
        log_event("data_fetch.requested", provider=self.id)
        txns = generate_demo_history()
        log_event("data_fetch.completed", provider=self.id, count=len(txns))
        return txns

    def disconnect_account(self, account_ref: str) -> None:
        log_event("account.disconnected", provider=self.id)

    def refresh_data(self, account_ref: str) -> list[RawTransaction]:
        # The sandbox re-serves the same history; external ids make the re-import a no-op.
        return self.fetch_transactions(account_ref)
