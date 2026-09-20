"use client";

import { useState } from "react";
import Link from "next/link";
import { FileText, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useLedgerData } from "@/hooks/useLedgerData";
import { useLedger } from "@/components/providers/LedgerProvider";
import type { SummaryRow } from "@/lib/types";
import { inr, num } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface Resp {
  summaries: SummaryRow[];
  open_actions: { id: string; title: string; description: string; priority: string; summary_title: string; summary_id: string }[];
}

const PRIORITY_VARIANT = { HIGH: "negative", MEDIUM: "warning", LOW: "outline" } as const;

export default function SummariesPage() {
  const { bump } = useLedger();
  const { data, error, loading } = useLedgerData<Resp>("/summaries");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setMsg(null);
    try {
      const s = await api<{ id: string; title: string }>("/summaries/generate", { json: {} });
      setMsg(`Generated: ${s.title}`);
      bump();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error && !data) return <p className="text-sm text-negative">{error}</p>;
  const rows = data?.summaries ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Monthly summaries</h1>
          <p className="text-sm text-muted-foreground">One report per financial cycle, generated automatically when the cycle closes. Observations and action items come straight from your ledger.</p>
        </div>
        <Button onClick={generate} disabled={busy}><Sparkles className="h-4 w-4" /> {busy ? "Generating…" : "Generate summary"}</Button>
      </div>
      {msg && <p className="text-sm text-positive">{msg}</p>}

      {(data?.open_actions ?? []).length > 0 && (
        <Card>
          <CardContent className="space-y-2 pt-5">
            <p className="text-sm font-medium">Open action items</p>
            {data!.open_actions.slice(0, 5).map((a) => (
              <Link key={a.id} href={`/summaries/${a.summary_id}`} className="flex items-start gap-3 rounded-md border border-border p-3 text-sm hover:bg-secondary">
                <Badge variant={PRIORITY_VARIANT[a.priority as keyof typeof PRIORITY_VARIANT]}>{a.priority}</Badge>
                <div className="min-w-0"><p className="font-medium">{a.title}</p><p className="text-xs text-muted-foreground">{a.description}</p></div>
              </Link>
            ))}
          </CardContent>
        </Card>
      )}

      {rows.length === 0 && <p className="text-sm text-muted-foreground">No summaries yet. They are created when a financial cycle closes, or with the button above.</p>}

      <div className="space-y-3">
        {rows.map((s) => (
          <Link key={s.id} href={`/summaries/${s.id}`} className="block">
            <Card className="transition-colors hover:border-primary/50">
              <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-5">
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-primary" />
                  <div>
                    <p className="font-medium">{s.title.replace("Financial summary: ", "")}</p>
                    <p className="text-xs text-muted-foreground">
                      {s.is_final ? "Completed cycle" : "In progress"}{s.top_category ? ` · top category ${s.top_category}` : ""}
                      {(s.open_actions ?? 0) > 0 ? ` · ${s.open_actions} open action item${s.open_actions === 1 ? "" : "s"}` : ""}
                    </p>
                  </div>
                </div>
                <dl className="flex gap-6 text-right text-sm">
                  <div><dt className="text-xs text-muted-foreground">Income</dt><dd className="tabular-nums">{inr(s.income_total)}</dd></div>
                  <div><dt className="text-xs text-muted-foreground">Expenses</dt><dd className="tabular-nums">{inr(s.expense_total)}</dd></div>
                  <div><dt className="text-xs text-muted-foreground">Saved</dt><dd className="tabular-nums text-positive">{inr(s.savings_total)}{s.savings_rate !== null ? ` (${num(s.savings_rate).toFixed(1)}%)` : ""}</dd></div>
                  {s.expense_change !== null && <div><dt className="text-xs text-muted-foreground">vs previous</dt><dd className={`tabular-nums ${num(s.expense_change) > 0 ? "text-negative" : "text-positive"}`}>{inr(s.expense_change, { sign: true })}</dd></div>}
                </dl>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
