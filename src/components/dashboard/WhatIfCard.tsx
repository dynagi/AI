"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { inr, signedInr, type Money } from "@/lib/format";
import { RetroWindow } from "@/components/retro/Window";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface Result {
  verdict: string;
  risk_before: string;
  risk_after: string;
  risk_worsened: boolean;
  lowest_balance_before: Money;
  lowest_balance_after: Money;
  savings_impact: { at_risk: boolean; message: string };
  budget_impact: { at_risk: boolean; message: string };
  timeline: { kind: string; date_label: string; label: string; amount: Money; balance_after: Money }[];
  note: string;
}

/** "What if I buy…?" Sends a hypothetical to POST /whatif. Nothing is saved, paid or changed. */
export default function WhatIfCard() {
  const [amount, setAmount] = useState("");
  const [label, setLabel] = useState("");
  const [days, setDays] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<Result | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    const n = Number(amount);
    if (!(n > 0)) {
      setError("Enter an amount greater than 0.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const d = Math.max(0, Math.min(90, Math.round(Number(days) || 0)));
      setRes(await api<Result>("/whatif", { json: { amount: n, label: label.trim() || "Purchase", days: d } }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <RetroWindow title="What if…?" bodyClassName="space-y-3 p-3">
      <form onSubmit={run} className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_1fr_90px_auto]">
        <Input placeholder="What? (e.g. Phone)" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} aria-label="What you might buy" />
        <Input placeholder="₹ Amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} aria-label="Amount in rupees" />
        <Input placeholder="In days" inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} aria-label="Days from now" title="Days from now (0 = today)" />
        <Button type="submit" disabled={busy}>{busy ? "Checking…" : "Check"}</Button>
      </form>
      {error && <p className="text-xs">{error}</p>}
      {res && (
        <div className="space-y-2">
          <div className={cn("space-y-1 border-2 border-black p-2 text-sm", res.risk_worsened ? "bg-[#ffd0d0]" : "bg-[#d9f2d9]")}>
            <p className="font-bold">{res.risk_before} → {res.risk_after}</p>
            <p>{res.verdict}</p>
            <p className="text-xs">Lowest balance: {inr(res.lowest_balance_before)} → {inr(res.lowest_balance_after)}</p>
          </div>
          <ol className="space-y-1 text-xs">
            {res.timeline.map((t, i) => (
              <li key={i} className="flex justify-between border border-black/40 px-2 py-0.5">
                <span><b>{t.date_label}</b> {t.kind === "start" ? "Balance now" : `${signedInr(t.amount)} ${t.label}`}</span>
                <span className="tabular-nums">{inr(t.balance_after)}</span>
              </li>
            ))}
          </ol>
          {res.savings_impact.at_risk && <p className="text-xs">⚠️ {res.savings_impact.message}</p>}
          {res.budget_impact.at_risk && <p className="text-xs">⚠️ {res.budget_impact.message}</p>}
          <p className="text-[11px] text-muted-foreground">{res.note}</p>
        </div>
      )}
    </RetroWindow>
  );
}
