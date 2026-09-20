"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Check, RotateCcw, X } from "lucide-react";
import { api } from "@/lib/api";
import { useLedgerData } from "@/hooks/useLedgerData";
import { useLedger } from "@/components/providers/LedgerProvider";
import type { ActionItem, SummaryDetail } from "@/lib/types";
import { dateTime, inr, num, pct } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { GOAL_TYPE_LABEL, GoalStatusBadge, goalTone } from "@/components/goals/GoalBits";
import CategoryBars from "@/components/charts/CategoryBars";

const PRIORITY_VARIANT = { HIGH: "negative", MEDIUM: "warning", LOW: "outline" } as const;

function ActionRow({ a, onChange }: { a: ActionItem; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  async function set(status: string) {
    setBusy(true);
    await api(`/summary-actions/${a.id}`, { method: "PATCH", json: { status } }).catch(() => {});
    setBusy(false);
    onChange();
  }
  const done = a.status !== "OPEN";
  return (
    <div className={`flex items-start gap-3 rounded-md border border-border p-3 ${done ? "opacity-60" : ""}`}>
      <Badge variant={PRIORITY_VARIANT[a.priority]}>{a.priority}</Badge>
      <div className="min-w-0 flex-1">
        <p className={`text-sm font-medium ${a.status === "COMPLETED" ? "line-through" : ""}`}>{a.title}</p>
        <p className="mt-0.5 text-sm text-muted-foreground">{a.description}</p>
        {done && <p className="mt-1 text-xs text-muted-foreground">{a.status === "COMPLETED" ? "Completed" : "Dismissed"}</p>}
      </div>
      <div className="flex shrink-0 gap-1">
        {a.status === "OPEN" ? (
          <>
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => set("COMPLETED")} title="Mark complete"><Check className="h-3.5 w-3.5" /></Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => set("DISMISSED")} title="Dismiss"><X className="h-3.5 w-3.5" /></Button>
          </>
        ) : (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => set("OPEN")} title="Reopen"><RotateCcw className="h-3.5 w-3.5" /></Button>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

export default function SummaryPage() {
  const { id } = useParams<{ id: string }>();
  const { bump } = useLedger();
  const { data: s, error, loading } = useLedgerData<SummaryDetail>(`/summaries/${id}`);

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error && !s) return <p className="text-sm text-negative">{error}</p>;
  if (!s) return null;
  const c = s.content;
  const open = s.actions.filter((a) => a.status === "OPEN");
  const closed = s.actions.filter((a) => a.status !== "OPEN");

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link href="/summaries" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3.5 w-3.5" /> All summaries</Link>
      <div>
        <h1 className="text-xl font-semibold">{s.title}</h1>
        <p className="text-sm text-muted-foreground">
          {s.is_final ? "Completed cycle" : "Cycle in progress: figures will keep changing until the next salary"} · generated {dateTime(s.generated_at)}
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle>Overview</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 gap-5 md:grid-cols-4">
          <Stat label="Income" value={inr(s.income_total)} sub={num(c.overview.other_inflows) > 0 ? `+ ${inr(c.overview.other_inflows)} other inflows` : undefined} />
          <Stat label="Expenses" value={inr(s.expense_total)} sub={num(c.overview.refunds) > 0 ? `${inr(c.overview.refunds)} refunded` : undefined} />
          <Stat label="Savings" value={inr(s.savings_total)} sub={c.overview.savings_target !== null && c.overview.savings_target !== undefined ? `Target ${inr(c.overview.savings_target)}` : "No target set"} />
          <Stat label="Savings rate" value={s.savings_rate !== null ? `${num(s.savings_rate).toFixed(1)}%` : "n/a"} />
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Top spending categories</CardTitle></CardHeader>
          <CardContent>
            <ul className="mb-3 space-y-1.5 text-sm">
              {c.top_categories.map((t) => <li key={t.category} className="flex justify-between"><span>{t.category}</span><span className="tabular-nums">{inr(t.total)}{t.percent ? <span className="ml-2 text-xs text-muted-foreground">{t.percent}%</span> : null}</span></li>)}
              {c.top_categories.length === 0 && <li className="text-muted-foreground">No spending in this cycle.</li>}
            </ul>
            <CategoryBars data={c.categories} />
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Compared with the previous cycle</CardTitle></CardHeader>
            <CardContent className="space-y-1.5 text-sm">
              {c.previous_comparison ? (
                <>
                  <div className="flex justify-between"><span className="text-muted-foreground">{c.previous_comparison.previous_label}</span><span className="tabular-nums">{inr(c.previous_comparison.previous_expenses)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">This cycle</span><span className="tabular-nums">{inr(s.expense_total)}</span></div>
                  <div className="flex justify-between font-medium"><span>Change</span><span className={`tabular-nums ${num(c.previous_comparison.difference) > 0 ? "text-negative" : "text-positive"}`}>{inr(c.previous_comparison.difference, { sign: true })} ({pct(c.previous_comparison.change_percent)})</span></div>
                  {c.previous_comparison.top_increases.slice(0, 2).map((x) => <p key={x.category} className="text-xs text-muted-foreground">{x.category}: {inr(x.a)} → {inr(x.b)} ({pct(x.change_percent)})</p>)}
                </>
              ) : <p className="text-muted-foreground">There is no earlier cycle to compare with.</p>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Recurring commitments</CardTitle></CardHeader>
            <CardContent className="space-y-1 text-sm">
              <p>{c.recurring.payments_in_cycle} recurring payment{c.recurring.payments_in_cycle === 1 ? "" : "s"} this cycle, {inr(c.recurring.paid_in_cycle)}</p>
              <p className="text-xs text-muted-foreground">{c.recurring.active_recurring_payments} active recurring payments, about {inr(c.recurring.estimated_monthly_total)}/month</p>
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle>Unusual activity</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          {c.unusual_activity.length === 0 ? <p className="text-muted-foreground">Nothing unusual was detected.</p> : c.unusual_activity.map((u, i) => <p key={i}>• {u.message}</p>)}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Goal progress</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {c.goals.length === 0 && <p className="text-sm text-muted-foreground">No goals were set.</p>}
            {c.goals.map((g) => (
              <div key={g.id} className="space-y-1.5">
                <div className="flex items-center justify-between text-sm"><span>{g.name} <span className="text-xs text-muted-foreground">({GOAL_TYPE_LABEL[g.goal_type]})</span></span><GoalStatusBadge status={g.status} reason={g.reason} /></div>
                <Progress value={g.progress_percent} tone={goalTone(g.status)} />
                <p className="text-xs text-muted-foreground">{inr(g.current_amount)} of {inr(g.target_amount)} · {g.progress_percent.toFixed(1)}%</p>
              </div>
            ))}
            <p className="text-[11px] text-muted-foreground">Goal progress as of when this summary was generated.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Budget status</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {c.budgets.length === 0 && <p className="text-sm text-muted-foreground">No category budgets were set.</p>}
            {c.budgets.map((b) => (
              <div key={b.category} className="space-y-1">
                <div className="flex justify-between text-sm"><span>{b.category}</span><span className="tabular-nums text-muted-foreground">{inr(b.spent)} / {inr(b.amount)}</span></div>
                <Progress value={b.percent_used} tone={b.status === "OVER_BUDGET" ? "negative" : b.percent_used >= 80 ? "warning" : "primary"} />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Key observations</CardTitle></CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1.5 pl-5 text-sm">{c.observations.map((o, i) => <li key={i}>{o.text}</li>)}</ul>
          {c.observations.length === 0 && <p className="text-sm text-muted-foreground">No observations for this cycle.</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Action items</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {open.length === 0 && <p className="text-sm text-muted-foreground">No open action items.</p>}
          {open.map((a) => <ActionRow key={a.id} a={a} onChange={bump} />)}
          {closed.length > 0 && <p className="pt-2 text-xs font-medium text-muted-foreground">Completed and dismissed</p>}
          {closed.map((a) => <ActionRow key={a.id} a={a} onChange={bump} />)}
        </CardContent>
      </Card>
    </div>
  );
}
