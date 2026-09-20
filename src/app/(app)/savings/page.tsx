"use client";

import { useLedgerData } from "@/hooks/useLedgerData";
import type { Savings } from "@/lib/types";
import { inr, inrRound, num, type Money } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import SavingsTargetForm from "@/components/dashboard/SavingsTargetForm";

interface Resp {
  current: Savings | null;
  history: { cycle_id: string; label: string; income: Money; expenses: Money; savings: Money; target: Money | null; met: boolean | null }[];
}

function Line({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border py-2.5 last:border-0">
      <div>
        <p className="text-sm">{label}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      <p className="text-sm font-medium tabular-nums">{value}</p>
    </div>
  );
}

export default function SavingsTargetPage() {
  const { data, error, loading } = useLedgerData<Resp>("/savings");
  const s = data?.current;

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error && !data) return <p className="text-sm text-negative">{error}</p>;

  const tone = s?.status === "AT_RISK" ? "negative" : "positive";
  const limitPct = s?.planned_spend_limit ? (num(s.net_spend) / num(s.planned_spend_limit)) * 100 : 0;

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Monthly savings target</h1>
        <p className="text-sm text-muted-foreground">How much of this cycle's income you want to keep. Long-term goals like a laptop or an emergency fund live on the Goals page.</p>
      </div>

      {!s ? (
        <Card className="p-5 text-sm text-muted-foreground">There is no active financial cycle yet. A cycle starts when a salary is credited.</Card>
      ) : (
        <>
          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle>{s.cycle ? `Cycle ${s.cycle}` : "Current cycle"}</CardTitle>
              {s.status === "ON_TRACK" && <Badge variant="positive">On track</Badge>}
              {s.status === "AT_RISK" && <Badge variant="negative">At risk</Badge>}
              {s.status === "NO_TARGET" && <Badge variant="outline">No target set</Badge>}
              {s.status === "INSUFFICIENT_DATA" && <Badge variant="outline">Not enough data</Badge>}
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="mb-2 text-sm font-medium">{s.target === null ? "How much do you want to save this cycle?" : "Update your target"}</p>
                <div className="max-w-sm"><SavingsTargetForm key={String(s.target)} initial={s.target !== null ? num(s.target) : undefined} cta={s.target === null ? "Set target" : "Update target"} /></div>
              </div>

              <p className={`rounded-md border p-3 text-sm ${s.status === "AT_RISK" ? "border-negative/40 bg-negative/10" : "border-border bg-secondary/40"}`}>
                {s.status === "AT_RISK" && "⚠️ Savings goal at risk. "}{s.message}{s.capacity_message ? ` ${s.capacity_message}` : ""}
              </p>

              {s.target !== null && s.planned_spend_limit !== null && (
                <div>
                  <div className="mb-1.5 flex justify-between text-xs text-muted-foreground">
                    <span>Spent {inr(s.net_spend)}</span><span>Planned limit {inr(s.planned_spend_limit)}</span>
                  </div>
                  <Progress value={limitPct} tone={limitPct > 100 ? "negative" : limitPct > 80 ? "warning" : tone} />
                </div>
              )}

              <div>
                <Line label="Savings target" value={s.target !== null ? inr(s.target) : "Not set"} />
                <Line label="Cycle income" value={inr(s.income)} hint="Salary and other income; excludes the balance already in the account" />
                <Line label="Other inflows" value={inr(s.other_inflows)} hint="Money from other people; not counted as income" />
                <Line label="Expenses so far" value={inr(s.expenses)} hint={num(s.refunds) > 0 ? `${inr(s.refunds)} refunded` : undefined} />
                <Line label="Remaining spending capacity" value={s.remaining_spend_capacity !== null ? inr(s.remaining_spend_capacity) : "n/a"} hint="Planned limit minus spending so far (income − target − spent)" />
                <Line label="Estimated savings right now" value={inr(s.estimated_savings)} hint="Income minus spending so far" />
                <Line
                  label="Projected savings by cycle end"
                  value={inrRound(s.projected_savings)}
                  hint={s.projection_basis === "recent_cycles" ? "Assumes the rest of the cycle looks like your recent cycles" : "Not enough history to project; based on spending so far"}
                />
                <Line label="Still needed to reach the target" value={s.required_more_savings !== null ? inr(s.required_more_savings) : "n/a"} hint="0 means the target is currently met" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Previous cycles</CardTitle></CardHeader>
            <CardContent>
              {data!.history.length === 0 ? <p className="text-sm text-muted-foreground">No closed cycles yet.</p> : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-xs text-muted-foreground">
                      <th className="pb-2 text-left font-medium">Cycle</th><th className="pb-2 text-right font-medium">Expenses</th>
                      <th className="pb-2 text-right font-medium">Saved</th><th className="pb-2 text-right font-medium">Target</th><th className="pb-2 text-right font-medium" />
                    </tr>
                  </thead>
                  <tbody>
                    {data!.history.map((h) => (
                      <tr key={h.cycle_id} className="border-b border-border last:border-0">
                        <td className="py-2.5">{h.label}</td>
                        <td className="py-2.5 text-right tabular-nums">{inr(h.expenses)}</td>
                        <td className="py-2.5 text-right tabular-nums">{inr(h.savings)}</td>
                        <td className="py-2.5 text-right tabular-nums">{h.target !== null ? inr(h.target) : "not set"}</td>
                        <td className="py-2.5 text-right">{h.met === null ? null : h.met ? <Badge variant="positive">Met</Badge> : <Badge variant="negative">Missed</Badge>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
