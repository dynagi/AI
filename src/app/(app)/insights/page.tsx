"use client";

import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useLedgerData } from "@/hooks/useLedgerData";
import type { BudgetRow, GoalAnalysis, GoalsCombined, Insight, Savings } from "@/lib/types";
import { dateShort, inr, inrRound, num, pct, type Money } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { GoalStatusBadge } from "@/components/goals/GoalBits";

interface Overview {
  account: { id: string; name: string } | null;
  trends: { cycle_id: string; label: string; status: string; income: Money; expenses: Money; savings: Money; savings_rate: number | null; top_category: string | null; change_vs_previous: Money | null; change_percent: number | null }[];
  unusual_activity: { type: string; category: string | null; message: string; evidence: Record<string, unknown> }[];
  recurring: { merchant: string; category: string; average_amount: Money; frequency: string; last_payment: string; next_expected_payment: string; confidence: Money; occurrences: number }[];
  upcoming_obligations: { within_days: number; total: Money; items: { merchant: string; amount: Money; expected_at: string }[] };
  goal_risks: GoalAnalysis[];
  goals_combined: GoalsCombined;
  budget_risks: BudgetRow[];
  insights: Insight[];
  savings: (Savings & { cycle: string }) | null;
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-foreground">{title}</CardTitle>{hint && <p className="text-xs text-muted-foreground">{hint}</p>}</CardHeader>
      <CardContent className="space-y-2 text-sm">{children}</CardContent>
    </Card>
  );
}

const empty = (t: string) => <p className="text-muted-foreground">{t}</p>;

export default function InsightsPage() {
  const { data: o, error, loading } = useLedgerData<Overview>("/insights/overview");
  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error && !o) return <p className="text-sm text-negative">{error}</p>;
  if (!o || !o.account) return <p className="text-sm text-muted-foreground">Connect an account or add transactions to see insights.</p>;

  const chart = o.trends.map((t) => ({ label: t.label.split(" – ")[0], Expenses: num(t.expenses), Savings: num(t.savings) }));

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Insights</h1>
        <p className="text-sm text-muted-foreground">Every insight here is computed from your transactions and shows the data behind it. Nothing appears without supporting records.</p>
      </div>

      <Section title="Spending trends" hint="Expenses and savings for your recent financial cycles">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chart}>
            <CartesianGrid vertical={false} stroke="hsl(222 16% 18%)" />
            <XAxis dataKey="label" tick={{ fill: "hsl(220 10% 70%)", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "hsl(220 10% 60%)", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => inr(v)} width={72} />
            <Tooltip contentStyle={{ background: "hsl(222 22% 10%)", border: "1px solid hsl(222 16% 22%)", borderRadius: 8, fontSize: 12 }} formatter={(v: number) => inr(v)} />
            <Bar dataKey="Expenses" fill="#6d86ff" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="Savings" fill="#4ade80" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
        <div className="divide-y divide-border">
          {[...o.trends].reverse().slice(0, 4).map((t) => (
            <div key={t.cycle_id} className="flex flex-wrap justify-between gap-2 py-2">
              <span>{t.label}{t.status === "ACTIVE" ? " (current)" : ""}</span>
              <span className="tabular-nums text-muted-foreground">
                {inr(t.expenses)} spent{t.top_category ? ` · top: ${t.top_category}` : ""}{t.change_vs_previous !== null ? ` · ${inr(t.change_vs_previous, { sign: true })} (${pct(t.change_percent)}) vs previous` : ""}
              </span>
            </div>
          ))}
        </div>
      </Section>

      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Unusual activity" hint="Compared with your own history">
          {o.unusual_activity.length === 0 && empty("Nothing unusual in the current cycle.")}
          {o.unusual_activity.map((u, i) => (
            <div key={i} className="rounded-md border border-border p-3">
              <p>{u.message}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {u.category ? <Link href={`/transactions?category=${encodeURIComponent(u.category)}`} className="text-primary">View {u.category} transactions →</Link> : <Link href="/transactions" className="text-primary">View transactions →</Link>}
              </p>
            </div>
          ))}
        </Section>

        <Section title="Savings observations">
          {o.savings ? (
            <>
              <p>{o.savings.message}</p>
              {o.savings.capacity_message && <p className="text-muted-foreground">{o.savings.capacity_message}</p>}
              <Link href="/savings" className="text-xs text-primary">Savings target details →</Link>
            </>
          ) : empty("No active cycle yet.")}
        </Section>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Goal risks" hint="Goals your current savings pace does not fully support">
          {o.goal_risks.length === 0 && empty("None of your active goals is at risk right now.")}
          {o.goal_risks.map((g) => (
            <div key={g.id} className="rounded-md border border-border p-3">
              <div className="flex items-center justify-between"><span className="font-medium">{g.name}</span><GoalStatusBadge status={g.status} /></div>
              <p className="mt-1 text-xs text-muted-foreground">{g.message}</p>
            </div>
          ))}
          <Link href="/goals" className="text-xs text-primary">All goals →</Link>
        </Section>

        <Section title="Budget risks" hint="Categories over or close to their budget this cycle">
          {o.budget_risks.length === 0 && empty("All category budgets are on track.")}
          {o.budget_risks.map((b) => (
            <div key={b.id} className="flex items-center justify-between rounded-md border border-border p-3">
              <span>{b.category}: {inr(b.spent)} of {inr(b.amount)} ({Math.round(b.percent_used)}%)</span>
              <Badge variant={b.status === "OVER_BUDGET" ? "negative" : "warning"}>{b.status === "OVER_BUDGET" ? "Over budget" : "At risk"}</Badge>
            </div>
          ))}
          <Link href="/budgets" className="text-xs text-primary">Budgets →</Link>
        </Section>
      </div>

      <Section title="Recurring payments" hint="Detected from at least three evenly spaced payments">
        {o.recurring.length === 0 && empty("No recurring payments detected yet.")}
        <div className="grid gap-x-8 sm:grid-cols-2">
          {o.recurring.map((r) => (
            <div key={r.merchant} className="flex justify-between border-b border-border py-2">
              <span>{r.merchant} <span className="text-xs text-muted-foreground">({r.frequency})</span></span>
              <span className="tabular-nums">{inr(r.average_amount)}</span>
            </div>
          ))}
        </div>
        {o.upcoming_obligations.items.length > 0 && (
          <p className="pt-2 text-xs text-muted-foreground">Next {o.upcoming_obligations.within_days} days: about {inr(o.upcoming_obligations.total)} expected across {o.upcoming_obligations.items.length} payments, the next on {dateShort(o.upcoming_obligations.items[0].expected_at)}.</p>
        )}
      </Section>

      <Section title="Observations" hint="Each one is backed by the figures shown">
        {o.insights.length === 0 && empty("No observations yet.")}
        {o.insights.map((i) => (
          <div key={i.id} className="rounded-md border border-border p-3">
            <div className="flex items-center gap-2"><p className="font-medium">{i.title}</p>{i.severity === "warning" && <Badge variant="warning">Notable</Badge>}</div>
            <p className="mt-0.5 text-muted-foreground">{i.message}</p>
          </div>
        ))}
        {o.goals_combined.active_goals > 0 && o.goals_combined.savings_pace_monthly !== null && (
          <p className="pt-1 text-xs text-muted-foreground">Savings pace: about {inrRound(o.goals_combined.savings_pace_monthly)} per month against {inrRound(o.goals_combined.total_required_monthly)} needed for your active goals.</p>
        )}
      </Section>
    </div>
  );
}
