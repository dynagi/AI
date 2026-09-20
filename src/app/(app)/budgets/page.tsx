"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useLedgerData } from "@/hooks/useLedgerData";
import { useLedger } from "@/components/providers/LedgerProvider";
import type { BudgetRow, Commitments } from "@/lib/types";
import { dateShort, inr, num, type Money } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";

interface Resp {
  budgets: BudgetRow[];
  totals: { total_budget: Money; spent: Money; remaining: Money; committed: Money; projected: Money } | null;
  commitments: Commitments | null;
  categories: string[];
}

const STATUS = { ON_TRACK: ["positive", "On track"], AT_RISK: ["warning", "At risk"], OVER_BUDGET: ["negative", "Over budget"] } as const;

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </Card>
  );
}

export default function BudgetsPage() {
  const { bump } = useLedger();
  const { data, error, loading } = useLedgerData<Resp>("/budgets");
  const [category, setCategory] = useState("Food");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api("/budgets", { method: "PUT", json: { category, amount: Number(amount) } });
      setAmount("");
      bump();
    } catch (e2) {
      setErr((e2 as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    await api(`/budgets/${id}`, { method: "DELETE" }).catch(() => {});
    bump();
  }

  const t = data?.totals;
  const c = data?.commitments;
  const hasCommit = c && !c.error && c.monthly_budget !== undefined && c.monthly_budget !== null;

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Budgets</h1>
        <p className="text-sm text-muted-foreground">Category limits measured against your current financial cycle. They are separate from your savings target and your goals.</p>
      </div>

      {t && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Tile label="Total budget" value={inr(t.total_budget)} sub="Sum of category budgets" />
          <Tile label="Spent" value={inr(t.spent)} sub="In budgeted categories" />
          <Tile label="Remaining" value={inr(t.remaining)} />
          <Tile label="Projected" value={inr(t.projected)} sub="Spent + expected recurring + typical rest of cycle" />
        </div>
      )}

      <Card>
        <CardHeader><CardTitle className="text-foreground">How much of my budget is already committed?</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          {!hasCommit ? (
            <p className="text-muted-foreground">{c?.message ?? "Set a savings target or category budgets to see how much of your budget is committed."}</p>
          ) : (
            <>
              <p className="text-xs text-muted-foreground">Budget = {c!.budget_basis_explained}.</p>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <div><p className="text-xs text-muted-foreground">Monthly budget</p><p className="text-lg font-semibold tabular-nums">{inr(c!.monthly_budget)}</p></div>
                <div><p className="text-xs text-muted-foreground">Already spent</p><p className="text-lg font-semibold tabular-nums">{inr(c!.already_spent)}</p></div>
                <div><p className="text-xs text-muted-foreground">Expected recurring</p><p className="text-lg font-semibold tabular-nums">{inr(c!.upcoming_recurring_expected)}</p></div>
                <div><p className="text-xs text-muted-foreground">Committed</p><p className="text-lg font-semibold tabular-nums">{inr(c!.committed_total)}</p></div>
              </div>
              <Progress value={c!.percent_of_budget_committed ?? 0} tone={(c!.percent_of_budget_committed ?? 0) > 100 ? "negative" : (c!.percent_of_budget_committed ?? 0) > 80 ? "warning" : "primary"} />
              <p>
                <span className="font-medium">{inr(c!.remaining_flexible_capacity)}</span> of flexible capacity remains
                {c!.percent_of_budget_committed !== null && c!.percent_of_budget_committed !== undefined ? ` (${c!.percent_of_budget_committed}% of the budget is committed)` : ""}.
              </p>
              <p className="text-xs text-muted-foreground">{c!.calculation}. "Already spent" is money that has left the account; "expected recurring" is not spent yet.</p>
              {(c!.upcoming_recurring_items ?? []).length > 0 && (
                <div className="rounded-md border border-border p-3">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Recurring payments still expected this cycle</p>
                  {c!.upcoming_recurring_items!.map((i) => (
                    <div key={i.merchant} className="flex justify-between py-0.5"><span>{i.merchant} <span className="text-xs text-muted-foreground">~{dateShort(i.expected_at)}</span></span><span className="tabular-nums">{inr(i.amount)}</span></div>
                  ))}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-5">
          <form onSubmit={save} className="flex flex-wrap items-end gap-3">
            <div className="w-48 space-y-1.5">
              <Label>Category</Label>
              <Select value={category} onChange={(e) => setCategory(e.target.value)}>
                {(data?.categories ?? ["Food"]).filter((x) => !["Salary", "Transfer"].includes(x)).map((x) => <option key={x}>{x}</option>)}
              </Select>
            </div>
            <div className="w-40 space-y-1.5">
              <Label>Budget per cycle (₹)</Label>
              <Input type="number" min="1" required value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Set budget"}</Button>
          </form>
          {err && <p className="mt-2 text-sm text-negative">{err}</p>}
        </CardContent>
      </Card>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && !data && <p className="text-sm text-negative">{error}</p>}
      {data && data.budgets.length === 0 && <p className="text-sm text-muted-foreground">No category budgets yet.</p>}

      <div className="space-y-3">
        {(data?.budgets ?? []).map((b) => {
          const [variant, label] = STATUS[b.status];
          return (
            <Card key={b.id}>
              <CardContent className="space-y-2 pt-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2"><p className="text-sm font-medium">{b.category}</p><Badge variant={variant}>{label}</Badge></div>
                  <div className="flex items-center gap-3">
                    <p className="text-sm tabular-nums text-muted-foreground">{inr(b.spent)} / {inr(b.amount)}</p>
                    <button aria-label={`Delete ${b.category} budget`} className="text-muted-foreground hover:text-negative" onClick={() => remove(b.id)}><Trash2 className="h-4 w-4" /></button>
                  </div>
                </div>
                <Progress value={b.percent_used} tone={b.status === "OVER_BUDGET" ? "negative" : b.status === "AT_RISK" ? "warning" : "primary"} />
                <p className="text-xs text-muted-foreground">
                  {Math.round(b.percent_used)}% used · {num(b.remaining) >= 0 ? `${inr(b.remaining)} remaining` : `${inr(Math.abs(num(b.remaining)))} over budget`}
                  {num(b.upcoming_recurring) > 0 ? ` · ${inr(b.upcoming_recurring)} recurring still expected` : ""} · projected {inr(b.projected_spend)}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
