"use client";

import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";
import { useLedgerData } from "@/hooks/useLedgerData";
import type { Dashboard } from "@/lib/types";
import { dateTime, inr, inrRound, num, pct } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import StatCard from "@/components/dashboard/StatCard";
import AlertsPanel from "@/components/dashboard/AlertsPanel";
import SimulatorPanel from "@/components/dashboard/SimulatorPanel";
import SavingsTargetForm from "@/components/dashboard/SavingsTargetForm";
import CategoryBars from "@/components/charts/CategoryBars";
import TxnRow from "@/components/transactions/TxnRow";

function statusBadge(status?: string) {
  if (status === "ON_TRACK") return <Badge variant="positive">On track</Badge>;
  if (status === "AT_RISK") return <Badge variant="negative">At risk</Badge>;
  if (status === "NO_TARGET") return <Badge variant="outline">No target set</Badge>;
  return <Badge variant="outline">Not enough data</Badge>;
}

export default function DashboardPage() {
  const { me } = useAuth();
  const { data: d, error, loading } = useLedgerData<Dashboard>("/dashboard");

  if (loading) return <p className="text-sm text-muted-foreground">Loading your financial picture…</p>;
  if (error && !d) return <p className="text-sm text-negative">{error}</p>;
  if (!d) return null;

  if (!d.account) {
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <h1 className="text-xl font-semibold">Welcome to FinPilot</h1>
        <Card className="p-6">
          <p className="mb-4 text-sm text-muted-foreground">Connect a financial account to automatically import transactions, or add your own.</p>
          <div className="flex flex-wrap gap-2">
            <Button asChild><Link href="/settings">Connect Demo Bank</Link></Button>
            <Button asChild variant="secondary"><Link href="/transactions">Add a transaction</Link></Button>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">Demo / Sandbox: no real banking data. FinPilot never asks for bank passwords, PINs or OTPs.</p>
        </Card>
      </div>
    );
  }

  const { account, cycle, previous_cycle: prev, savings, spending_progress: sp, progress_vs_previous: pv } = d;
  const otherInflows = num(cycle?.other_inflows);
  const limitPct = sp?.percent_of_limit ?? null;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            {account.name}
            {account.source === "demo" && " · Demo / Sandbox"}
            {account.status !== "ACTIVE" && " · Disconnected (history still available)"}
            {cycle && ` · Cycle ${cycle.label}`}
          </p>
        </div>
        {d.as_of && <p className="text-xs text-muted-foreground">As of {dateTime(d.as_of)}</p>}
      </div>

      <AlertsPanel alerts={d.alerts ?? []} />

      {/* Top cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          big
          label="Current balance"
          value={inr(account.current_balance)}
          sub={
            cycle && num(cycle.carried_over_balance) > 0 ? (
              <p>Money in the account now (not income). This cycle opened at {inr(cycle.opening_balance)}: {inr(cycle.carried_over_balance)} already there + {inr(cycle.income)} income.</p>
            ) : (
              <p>Money in the account right now. Not income.</p>
            )
          }
        />
        <StatCard
          label="Current cycle income"
          value={inr(cycle?.income)}
          tone="positive"
          sub={
            <>
              <p>Salary &amp; other income only</p>
              {otherInflows > 0 && <p className="text-foreground/80">Other inflows: {inr(otherInflows)} (from people/accounts, not salary)</p>}
            </>
          }
        />
        <StatCard
          label="Current cycle expenses"
          value={inr(cycle?.expenses)}
          tone={pv && num(pv.exceeded_by) > 0 ? "negative" : "default"}
          sub={num(cycle?.refunds) > 0 ? <p>{inr(cycle?.refunds)} refunded</p> : <p>Resets to ₹0 at each salary; history is kept</p>}
        />
        <StatCard
          label="Savings target"
          value={savings?.target !== null && savings?.target !== undefined ? inr(savings.target) : "Not set"}
          sub={<div className="flex items-center gap-2">{statusBadge(savings?.status)}</div>}
        />
      </div>

      {!cycle && (
        <Card className="p-5 text-sm text-muted-foreground">
          No financial cycle yet. A cycle starts when a salary is credited. Use the Demo Bank Simulator below, or add a salary transaction.
        </Card>
      )}

      {cycle && savings?.needs_target && (
        <Card className="border-primary/40 bg-primary/5 p-5">
          <p className="text-sm font-medium">How much do you want to save this cycle?</p>
          <p className="mb-3 mt-0.5 text-xs text-muted-foreground">FinPilot never picks a target for you. Set one to track your spending against it.</p>
          <div className="max-w-sm"><SavingsTargetForm /></div>
        </Card>
      )}

      {cycle && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* Spending progress */}
          <Card>
            <CardHeader><CardTitle>Spending progress</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-baseline justify-between">
                <span className="text-2xl font-semibold tabular-nums">{inr(sp?.net_spend ?? cycle.expenses)}</span>
                {sp?.planned_spend_limit != null && <span className="text-xs text-muted-foreground">of {inr(sp.planned_spend_limit)} planned</span>}
              </div>
              {limitPct !== null ? (
                <>
                  <Progress value={limitPct} tone={limitPct > 100 ? "negative" : limitPct > 80 ? "warning" : "primary"} />
                  <p className="text-xs text-muted-foreground">
                    {savings?.remaining_spend_capacity != null && num(savings.remaining_spend_capacity) >= 0
                      ? `${inr(savings.remaining_spend_capacity)} of spending capacity left this cycle`
                      : `Over the planned spending by ${inr(Math.abs(num(savings?.remaining_spend_capacity)))}`}
                  </p>
                </>
              ) : (
                <p className="text-xs text-muted-foreground">Set a savings target to see how much you can spend this cycle.</p>
              )}
            </CardContent>
          </Card>

          {/* Savings goal */}
          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle>Savings goal</CardTitle>
              {statusBadge(savings?.status)}
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {savings && savings.target != null ? (
                <>
                  <div className="flex justify-between"><span className="text-muted-foreground">Target</span><span className="tabular-nums">{inr(savings.target)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Estimated savings now</span><span className="tabular-nums">{inr(savings.estimated_savings)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Projected savings</span><span className="tabular-nums">{inrRound(savings.projected_savings)}</span></div>
                  <p className={`pt-1 text-xs ${savings.status === "AT_RISK" ? "text-negative" : "text-muted-foreground"}`}>{savings.message}</p>
                  <Link href="/goals" className="text-xs text-primary">Details &amp; change target →</Link>
                </>
              ) : (
                <p className="text-xs text-muted-foreground">No target set for this cycle.</p>
              )}
            </CardContent>
          </Card>

          {/* Previous cycle comparison */}
          <Card>
            <CardHeader><CardTitle>Progress vs previous cycle</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {pv && prev ? (
                <>
                  <div className="flex justify-between"><span className="text-muted-foreground">Previous ({prev.label})</span><span className="tabular-nums">{inr(pv.previous)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Current</span><span className="tabular-nums">{inr(pv.current)}</span></div>
                  <Progress value={pv.percent_of_previous ?? 0} tone={num(pv.exceeded_by) > 0 ? "negative" : (pv.percent_of_previous ?? 0) > 80 ? "warning" : "primary"} />
                  <p className={`text-xs ${num(pv.exceeded_by) > 0 ? "text-negative" : "text-muted-foreground"}`}>{pv.message}</p>
                  <p className="text-xs text-muted-foreground">Difference {inr(pv.difference, { sign: true })} ({pct(pv.change_percent)})</p>
                  <Link href="/comparisons" className="text-xs text-primary">Full comparison →</Link>
                </>
              ) : (
                <p className="text-xs text-muted-foreground">There is no previous cycle to compare with yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>AI insights</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {(d.insights ?? []).length === 0 && <p className="text-sm text-muted-foreground">No insights yet. They appear once there is transaction data to base them on.</p>}
            {(d.insights ?? []).map((i) => (
              <div key={i.id} className="rounded-md border border-border p-3">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium">{i.title}</p>
                  {i.severity === "warning" && <Badge variant="warning">Notable</Badge>}
                </div>
                <p className="mt-0.5 text-sm text-muted-foreground">{i.message}</p>
              </div>
            ))}
            <Link href="/chat" className="inline-block text-xs text-primary">Ask FinPilot about this →</Link>
          </CardContent>
        </Card>
        {me?.demo_mode && <SimulatorPanel accountId={account.id} />}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Recent transactions</CardTitle>
            <Link href="/transactions" className="text-xs text-primary">View all →</Link>
          </CardHeader>
          <CardContent className="divide-y divide-border">
            {(d.recent_transactions ?? []).length === 0 && <p className="py-4 text-sm text-muted-foreground">No transactions yet.</p>}
            {(d.recent_transactions ?? []).slice(0, 8).map((t) => <TxnRow key={t.id} t={t} showDate />)}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Spending by category (this cycle)</CardTitle></CardHeader>
            <CardContent><CategoryBars data={cycle?.categories ?? []} /></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Recurring commitments</CardTitle></CardHeader>
            <CardContent className="space-y-1 text-sm">
              {d.recurring && d.recurring.count > 0 ? (
                <>
                  <p>{d.recurring.count} recurring payments, about <span className="font-medium">{inr(d.recurring.monthly_total)}</span>/month</p>
                  {d.upcoming_obligations && d.upcoming_obligations.items.length > 0 && (
                    <p className="text-xs text-muted-foreground">Next 30 days: {inr(d.upcoming_obligations.total)} expected across {d.upcoming_obligations.items.length} payment(s)</p>
                  )}
                </>
              ) : (
                <p className="text-xs text-muted-foreground">No recurring payments detected yet (needs at least 3 evenly spaced payments).</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
