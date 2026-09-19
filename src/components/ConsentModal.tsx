"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export interface ConsentInfo {
  consent_id: string;
  account_label: string;
  is_sandbox: boolean;
  purpose: string;
  data_requested: string;
  from_date: string;
  to_date: string;
  fetch_frequency: string;
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-6 py-1.5">
      <span className="text-muted-foreground">{k}</span>
      <span className="text-right">{v}</span>
    </div>
  );
}

export default function ConsentModal({ consent, busy, onApprove, onReject }: { consent: ConsentInfo; busy: boolean; onApprove: () => void; onReject: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4" role="dialog" aria-modal="true" aria-labelledby="consent-title">
      <Card className="w-full max-w-md p-6">
        {consent.is_sandbox && <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-positive">{consent.account_label}. Demo / Sandbox, no real banking data</p>}
        <h2 id="consent-title" className="text-lg font-semibold">FinPilot requests access to your financial information</h2>
        <p className="mb-4 mt-1 text-sm text-muted-foreground">
          This is a sandbox consent screen that demonstrates the Account Aggregator concept. FinPilot never asks for your bank password, UPI PIN, card PIN or banking OTP.
        </p>
        <div className="divide-y divide-border border-y border-border py-1 text-sm">
          <Row k="Data requested" v={consent.data_requested} />
          <Row k="Purpose" v={consent.purpose} />
          <Row k="Date range" v={`${consent.from_date} to ${consent.to_date}`} />
          <Row k="Access frequency" v={consent.fetch_frequency} />
        </div>
        <div className="mt-5 flex gap-3">
          <Button variant="secondary" className="flex-1" onClick={onReject} disabled={busy}>Reject</Button>
          <Button className="flex-1" onClick={onApprove} disabled={busy}>{busy ? "Connecting…" : "Approve"}</Button>
        </div>
      </Card>
    </div>
  );
}
