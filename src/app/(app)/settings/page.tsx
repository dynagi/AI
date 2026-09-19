"use client";

import { useState } from "react";
import Link from "next/link";
import { Landmark, PenLine, RefreshCw, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { useLedgerData } from "@/hooks/useLedgerData";
import { useLedger } from "@/components/providers/LedgerProvider";
import { dateTime } from "@/lib/format";
import ConsentModal, { type ConsentInfo } from "@/components/ConsentModal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Resp {
  accounts: { id: string; name: string; source: string; status: string; last_synced_at: string | null }[];
  data_sources: { id: string; account_id: string | null; source_type: string; label: string; status: string; record_count: number; last_synced_at: string | null }[];
  aa_sandbox_configured: boolean;
}

export default function DataSourcesPage() {
  const { bump } = useLedger();
  const { data, error, loading } = useLedgerData<Resp>("/accounts");
  const [consent, setConsent] = useState<ConsentInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const demoConnected = data?.accounts.some((a) => a.source === "demo" && a.status === "ACTIVE");

  async function startConsent(provider: "demo_bank" | "aa_sandbox") {
    setMsg(null);
    try {
      setConsent(await api<ConsentInfo>("/consents", { json: { provider } }));
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  }

  async function decide(approve: boolean) {
    if (!consent) return;
    setBusy(true);
    try {
      const r = await api<{ status: string; inserted?: number }>(`/consents/${consent.consent_id}/decision`, { json: { decision: approve ? "approve" : "reject" } });
      setConsent(null);
      setMsg(
        approve
          ? { ok: true, text: `Connected. ${r.inserted ?? 0} sandbox transactions were imported, categorized and analysed.` }
          : { ok: true, text: "Consent rejected. No data was accessed." },
      );
      bump();
    } catch (e) {
      setConsent(null);
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function act(path: string, ok: string) {
    setMsg(null);
    try {
      await api(path, { method: "POST" });
      setMsg({ ok: true, text: ok });
      bump();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Financial data sources</h1>
        <p className="text-sm text-muted-foreground">Bank data and manual data become the same normalized transactions and feed the same analysis.</p>
      </div>

      {msg && <p className={`text-sm ${msg.ok ? "text-positive" : "text-negative"}`}>{msg.text}</p>}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Connect a financial account</h2>
        <p className="text-sm text-muted-foreground">Connect a financial account to automatically import transactions.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center gap-2"><Landmark className="h-4 w-4 text-primary" /><p className="font-medium">Demo Bank</p></div>
              <p className="text-xs font-medium uppercase tracking-wider text-positive">Demo / Sandbox: no real banking data</p>
              {demoConnected ? <Badge variant="positive">Connected</Badge> : <Button onClick={() => startConsent("demo_bank")}>Connect Demo Bank</Button>}
            </CardContent>
          </Card>
          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center gap-2"><Landmark className="h-4 w-4 text-muted-foreground" /><p className="font-medium">Account Aggregator sandbox (Setu)</p></div>
              <p className="text-xs text-muted-foreground">
                {data?.aa_sandbox_configured ? "Sandbox credentials detected." : "Not configured. Set the SETU_* environment variables on the backend to enable it."}
              </p>
              <Button variant="secondary" disabled={!data?.aa_sandbox_configured} onClick={() => startConsent("aa_sandbox")}>Connect AA sandbox</Button>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Add financial data</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Card><CardContent className="space-y-2 pt-5"><PenLine className="h-4 w-4 text-primary" /><p className="text-sm font-medium">Add transaction</p><Button asChild variant="secondary" size="sm"><Link href="/transactions">Add transaction</Link></Button></CardContent></Card>
          <Card><CardContent className="space-y-2 pt-5"><Upload className="h-4 w-4 text-primary" /><p className="text-sm font-medium">Import CSV</p><Button asChild variant="secondary" size="sm"><Link href="/transactions">Import CSV</Link></Button></CardContent></Card>
          <Card><CardContent className="space-y-2 pt-5"><Upload className="h-4 w-4 text-muted-foreground" /><p className="text-sm font-medium">Upload statement</p><Button variant="secondary" size="sm" disabled>Coming soon</Button></CardContent></Card>
        </div>
      </section>

      <Card>
        <CardHeader><CardTitle>Your sources</CardTitle></CardHeader>
        <CardContent className="divide-y divide-border">
          {loading && <p className="py-3 text-sm text-muted-foreground">Loading…</p>}
          {error && !data && <p className="py-3 text-sm text-negative">{error}</p>}
          {data && data.data_sources.length === 0 && <p className="py-3 text-sm text-muted-foreground">No data sources yet.</p>}
          {(data?.data_sources ?? []).map((s) => {
            const isBank = s.source_type === "demo_bank" || s.source_type === "aa_sandbox";
            return (
              <div key={s.id} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-sm font-medium">{s.label}</p>
                  <p className="text-xs text-muted-foreground">
                    {isBank
                      ? s.status === "ACTIVE" ? `Connected · Last synced ${s.last_synced_at ? dateTime(s.last_synced_at) : "just now"}` : "Disconnected · your existing data is still available"
                      : `${s.record_count} transaction${s.record_count === 1 ? "" : "s"}`}
                  </p>
                </div>
                {isBank && s.account_id && s.status === "ACTIVE" && (
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" onClick={() => act(`/accounts/${s.account_id}/refresh`, "Refreshed. Your existing data is unchanged; only new transactions were added.")}><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>
                    <Button size="sm" variant="destructive" onClick={() => confirm("Disconnect this source? Your existing transactions stay.") && act(`/accounts/${s.account_id}/disconnect`, "Disconnected. Your existing financial data is still available.")}>Disconnect</Button>
                  </div>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>

      {consent && <ConsentModal consent={consent} busy={busy} onApprove={() => decide(true)} onReject={() => decide(false)} />}
    </div>
  );
}
