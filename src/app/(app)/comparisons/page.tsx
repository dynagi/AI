"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useLedgerData } from "@/hooks/useLedgerData";
import type { CycleSummary, LargestTxn } from "@/lib/types";
import { dateShort, inr, num, pct, type Money } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface Change { category: string; a: Money; b: Money; change: Money; change_percent: number | null }
interface Comparison {
  a: CycleSummary;
  b: CycleSummary;
  expense_difference: Money;
  expense_change_percent: number | null;
  income_difference: Money;
  savings_difference: Money;
  category_changes: Change[];
  top_increases: Change[];
  top_decreases: Change[];
  explanation: string[];
}
interface Resp { cycles: { id: string; label: string; status: string }[]; comparison: Comparison | null; message?: string }

function Row({ label, a, b, delta, deltaTone }: { label: string; a: string; b: string; delta?: string; deltaTone?: "up" | "down" }) {
  return (
    <tr className="border-b border-border last:border-0">
      <td className="py-2.5 text-muted-foreground">{label}</td>
      <td className="py-2.5 text-right tabular-nums">{a}</td>
      <td className="py-2.5 text-right tabular-nums">{b}</td>
      <td className={cn("py-2.5 text-right tabular-nums", deltaTone === "up" && "text-negative", deltaTone === "down" && "text-positive")}>{delta ?? ""}</td>
    </tr>
  );
}

function Largest({ items }: { items: LargestTxn[] }) {
  return (
    <ul className="space-y-1.5 text-sm">
      {items.length === 0 && <li className="text-muted-foreground">None</li>}
      {items.map((t) => (
        <li key={t.id} className="flex justify-between gap-3">
          <span className="truncate">{t.merchant || t.description} <span className="text-xs text-muted-foreground">· {dateShort(t.timestamp)}</span></span>
          <span className="tabular-nums">{inr(t.amount)}</span>
        </li>
      ))}
    </ul>
  );
}

export default function ComparisonsPage() {
  const [a, setA] = useState("previous");
  const [b, setB] = useState("current");
  const { data, error, loading } = useLedgerData<Resp>(`/comparisons?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  const c = data?.comparison;

  const chart = (c?.category_changes ?? []).slice(0, 8).map((x) => ({ category: x.category, [c!.a.label]: num(x.a), [c!.b.label]: num(x.b) }));

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Spending comparison</h1>
        <p className="text-sm text-muted-foreground">Compare any two financial cycles. Every figure comes from your stored ledger; nothing is deleted when a new cycle starts.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {([["Cycle A", a, setA], ["Cycle B", b, setB]] as const).map(([label, val, set]) => (
          <div key={label} className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">{label}</p>
            <Select value={val} onChange={(e) => set(e.target.value)}>
              <option value="previous">Previous cycle</option>
              <option value="current">Current cycle</option>
              {(data?.cycles ?? []).map((cy) => <option key={cy.id} value={cy.id}>{cy.label}{cy.status === "ACTIVE" ? " (current)" : ""}</option>)}
            </Select>
          </div>
        ))}
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && !data && <p className="text-sm text-negative">{error}</p>}
      {data && !c && <Card className="p-5 text-sm text-muted-foreground">{data.message ?? "Nothing to compare yet."}</Card>}

      {c && (
        <>
          <Card>
            <CardHeader><CardTitle>Overview</CardTitle></CardHeader>
            <CardContent>
              <div className="mb-4 flex flex-wrap items-baseline gap-3">
                <span className="text-3xl font-semibold tabular-nums">{inr(c.expense_difference, { sign: true })}</span>
                <span className="text-sm text-muted-foreground">expenses ({pct(c.expense_change_percent)}) in {c.b.label} vs {c.a.label}</span>
                {c.b.status === "ACTIVE" && num(c.expense_difference) < 0 && <Badge variant="positive">{inr(Math.abs(num(c.expense_difference)))} left before reaching {c.a.label}'s total</Badge>}
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="pb-2 text-left font-medium" />
                    <th className="pb-2 text-right font-medium">{c.a.label}</th>
                    <th className="pb-2 text-right font-medium">{c.b.label}</th>
                    <th className="pb-2 text-right font-medium">Change</th>
                  </tr>
                </thead>
                <tbody>
                  <Row label="Income" a={inr(c.a.income)} b={inr(c.b.income)} delta={inr(c.income_difference, { sign: true })} />
                  <Row label="Expenses" a={inr(c.a.expenses)} b={inr(c.b.expenses)} delta={inr(c.expense_difference, { sign: true })} deltaTone={num(c.expense_difference) > 0 ? "up" : "down"} />
                  <Row label="Savings" a={inr(c.a.savings)} b={inr(c.b.savings)} delta={inr(c.savings_difference, { sign: true })} deltaTone={num(c.savings_difference) < 0 ? "up" : "down"} />
                  <Row label="Savings rate" a={c.a.savings_rate === null ? "n/a" : `${c.a.savings_rate}%`} b={c.b.savings_rate === null ? "n/a" : `${c.b.savings_rate}%`} />
                  <Row label="Recurring expenses" a={inr(c.a.recurring_expenses.total)} b={inr(c.b.recurring_expenses.total)} />
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>What explains the difference</CardTitle></CardHeader>
            <CardContent>
              <ul className="list-disc space-y-1.5 pl-5 text-sm">{c.explanation.map((l, i) => <li key={i}>{l}</li>)}</ul>
              <p className="mt-3 text-xs text-muted-foreground">Generated directly from your transactions (no AI estimation). Ask FinPilot in chat for a deeper walk-through.</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Category comparison</CardTitle></CardHeader>
            <CardContent>
              {chart.length === 0 ? <p className="text-sm text-muted-foreground">No categorized spending in either cycle.</p> : (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={chart}>
                    <CartesianGrid vertical={false} stroke="hsl(222 16% 18%)" />
                    <XAxis dataKey="category" tick={{ fill: "hsl(220 10% 70%)", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "hsl(220 10% 60%)", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => inr(v)} width={70} />
                    <Tooltip contentStyle={{ background: "hsl(222 22% 10%)", border: "1px solid hsl(222 16% 22%)", borderRadius: 8, fontSize: 12 }} formatter={(v: number) => inr(v)} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey={c.a.label} fill="#5b6b9a" radius={[4, 4, 0, 0]} />
                    <Bar dataKey={c.b.label} fill="#6d86ff" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Top increases</CardTitle></CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                {c.top_increases.length === 0 && <p className="text-muted-foreground">No category increased.</p>}
                {c.top_increases.map((x) => (
                  <div key={x.category} className="flex justify-between"><span>{x.category}</span><span className="tabular-nums text-negative">{inr(x.change, { sign: true })} ({pct(x.change_percent)})</span></div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Top decreases</CardTitle></CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                {c.top_decreases.length === 0 && <p className="text-muted-foreground">No category decreased.</p>}
                {c.top_decreases.map((x) => (
                  <div key={x.category} className="flex justify-between"><span>{x.category}</span><span className="tabular-nums text-positive">{inr(x.change, { sign: true })} ({pct(x.change_percent)})</span></div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Largest transactions: {c.a.label}</CardTitle></CardHeader>
              <CardContent><Largest items={c.a.largest_transactions} /></CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Largest transactions: {c.b.label}</CardTitle></CardHeader>
              <CardContent><Largest items={c.b.largest_transactions} /></CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
