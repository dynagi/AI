"use client";

import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { api } from "@/lib/api";
import { inr, signedInr } from "@/lib/format";
import { useLedger } from "@/components/providers/LedgerProvider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Action {
  label: string;
  body: { type: string; amount: number; merchant?: string };
  variant?: "default" | "secondary" | "destructive";
}

const ACTIONS: Action[] = [
  { label: "Credit Salary ₹1,00,000", body: { type: "SALARY", amount: 100000 } },
  { label: "Receive ₹1,000 (Rahul)", body: { type: "TRANSFER_IN", amount: 1000, merchant: "Rahul" }, variant: "secondary" },
  { label: "Add Expense ₹160 (Swiggy)", body: { type: "EXPENSE", amount: 160, merchant: "Swiggy" }, variant: "secondary" },
  { label: "Add Expense ₹2,500 (Amazon)", body: { type: "EXPENSE", amount: 2500, merchant: "Amazon" }, variant: "secondary" },
  { label: "Add Large Expense ₹6,000", body: { type: "EXPENSE", amount: 6000, merchant: "Croma Electronics" }, variant: "secondary" },
  { label: "Add Refund ₹500", body: { type: "REFUND", amount: 500, merchant: "Amazon" }, variant: "secondary" },
  { label: "Savings-risk demo: ₹70,000 expense", body: { type: "EXPENSE", amount: 70000, merchant: "Croma Electronics" }, variant: "destructive" },
];

interface Result {
  transaction: { merchant: string | null; description: string; signed_amount: number | string; balance_after: number | string };
  balance: number | string;
  alerts: { title: string; message: string }[];
  new_cycle_started: boolean;
}

export default function SimulatorPanel({ accountId }: { accountId?: string }) {
  const { bump } = useLedger();
  const [busy, setBusy] = useState<string | null>(null);
  const [last, setLast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function fire(a: Action) {
    setBusy(a.label);
    setError(null);
    try {
      const r = await api<Result>("/demo/transactions", { json: { ...a.body, account_id: accountId } });
      const t = r.transaction;
      setLast(
        `${t.merchant || t.description} ${signedInr(t.signed_amount)} · balance ${inr(r.balance)}` +
          (r.new_cycle_started ? " · new financial cycle started" : "") +
          (r.alerts.length ? ` · ${r.alerts.map((x) => x.title).join(", ")}` : ""),
      );
      bump();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function reset() {
    if (!confirm("Remove ONLY the transactions created by this simulator? Seeded and imported data stay untouched.")) return;
    setBusy("reset");
    setError(null);
    try {
      const r = await api<{ removed: number }>("/demo/reset", { method: "POST" });
      setLast(`Removed ${r.removed} simulated transaction(s). Seeded history is unchanged.`);
      bump();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-foreground">
          <FlaskConical className="h-4 w-4 text-primary" /> Demo Bank Simulator
        </CardTitle>
        <p className="text-xs text-muted-foreground">Sandbox events sent through the same pipeline a real bank feed uses. No real banking data.</p>
      </CardHeader>
      <CardContent className="space-y-2">
        {ACTIONS.map((a) => (
          <Button key={a.label} size="sm" variant={a.variant ?? "default"} className="w-full justify-start" disabled={busy !== null} onClick={() => fire(a)}>
            {busy === a.label ? "Posting…" : a.label}
          </Button>
        ))}
        <Button size="sm" variant="ghost" className="w-full justify-start text-muted-foreground" disabled={busy !== null} onClick={reset}>
          Reset simulator events
        </Button>
        {last && <p className="pt-1 text-xs text-positive">{last}</p>}
        {error && <p className="pt-1 text-xs text-negative">{error}</p>}
      </CardContent>
    </Card>
  );
}
