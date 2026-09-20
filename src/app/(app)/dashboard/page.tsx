"use client";

import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";
import { useLedgerData } from "@/hooks/useLedgerData";
import type { Dashboard } from "@/lib/types";
import { dateShort, dateTime, inr, inrRound, num, pct } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import StatCard from "@/components/dashboard/StatCard";
import AlertsPanel from "@/components/dashboard/AlertsPanel";
import UpcomingCommitments from "@/components/dashboard/UpcomingCommitments";
import BriefingCard from "@/components/dashboard/BriefingCard";
import WhatIfCard from "@/components/dashboard/WhatIfCard";
import SimulatorPanel from "@/components/dashboard/SimulatorPanel";
import SavingsTargetForm from "@/components/dashboard/SavingsTargetForm";
import { RetroWindow } from "@/components/retro/Window";
import { RetroCalendar } from "@/components/retro/Calendar";
import { Cash, Coins, Doc, Piggy, Siren } from "@/components/retro/Sprite";
import { AskWindow, ProgressWindow, QuickActions, RecentTransactions, SpendingOverview, SpendingTrend } from "@/components/retro/DashboardWindows";
import { dayKey } from "@/lib/format";
import { GoalStatusBadge, goalTone } from "@/components/goals/GoalBits";

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

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const firstName = (me?.display_name || me?.email?.split("@")[0] || "there").split(" ")[0];
  const expensesPct = pv?.percent_of_previous ?? null;
  const incomeNow = num(cycle?.income);
  const savingsPctIncome = incomeNow > 0 ? Math.round((num(cycle?.savings) / incomeNow) * 100) : null;
  const txnDays = (d.recent_transactions ?? []).map((t) => dayKey(t.timestamp));

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-4">
          <RetroWindow title="Welcome.exe" focused closable={false} bodyClassName="p-4">
            <div className="flex flex-wrap items-center gap-4">
              <span aria-hidden className="text-5xl">📎</span>
              <div className="min-w-[200px] flex-1">
                <h1 className="font-pixel text-2xl font-bold sm:text-3xl">{greeting}, {firstName}!</h1>
                <p className="text-sm">Take control today for a better tomorrow.</p>
                <p className="mt-1 text-[11px]">
                  {account.name}
                  {account.source === "demo" && " · Demo / Sandbox"}
                  {account.status !== "ACTIVE" && " · Disconnected (history still available)"}
                  {cycle && ` · Cycle ${cycle.label}`}
                  {d.as_of && ` · As of ${dateTime(d.as_of)}`}
                </p>
              </div>
              <div className="retro-note w-full p-3 text-sm sm:w-auto sm:max-w-[240px]">Small steps today, bigger dreams tomorrow.</div>
            </div>
          </RetroWindow>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 2xl:grid-cols-4">
            <StatCard
              icon={<Cash />}
              label="Current Balance"
              value={inr(account.current_balance)}
              sub={
                cycle && num(cycle.carried_over_balance) > 0
                  ? <p>Money in the account now (not income). Cycle opened at {inr(cycle.opening_balance)}: {inr(cycle.carried_over_balance)} already there + {inr(cycle.income)} income.</p>
                  : <p>Money in the account right now. Not income.</p>
              }
            />
            <StatCard
              icon={<Coins />}
              label="Monthly Income"
              value={inr(cycle?.income)}
              tone="positive"
              sub={<><p>Salary &amp; other income</p>{otherInflows > 0 && <p>Other inflows: {inr(otherInflows)} (not salary)</p>}</>}
            />
            <StatCard
              icon={<Doc />}
              label="Monthly Expenses"
              value={inr(cycle?.expenses)}
              tone={pv && num(pv.exceeded_by) > 0 ? "negative" : "default"}
              sub={expensesPct !== null ? <p>{expensesPct.toFixed(0)}% of last cycle{num(cycle?.refunds) > 0 ? ` · ${inr(cycle?.refunds)} refunded` : ""}</p> : <p>Resets to ₹0 at each salary</p>}
            />
            <StatCard
              icon={<Piggy />}
              label="Savings"
              value={savings?.target !== null && savings?.target !== undefined ? inr(savings.target) : "Not set"}
              sub={<div className="flex flex-wrap items-center gap-2">{statusBadge(savings?.status)}{savingsPctIncome !== null && <span>{savingsPctIncome}% of income</span>}</div>}
            />
          </div>

          {(d.alerts ?? []).filter((a) => !a.is_read).length > 0 && (
            <div className="flex items-start gap-3">
              <div className="hidden pt-2 sm:block"><Siren /></div>
              <div className="min-w-0 flex-1"><AlertsPanel alerts={d.alerts ?? []} /></div>
            </div>
          )}

          <BriefingCard />

          {d.cashflow_risk && <UpcomingCommitments risk={d.cashflow_risk} />}

          <WhatIfCard />

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <SpendingOverview categories={cycle?.categories ?? []} />
            <SpendingTrend />
          </div>

          <RecentTransactions txns={d.recent_transactions ?? []} />
        </div>

        <aside className="min-w-0 space-y-4">
          <RetroWindow title="Calendar"><RetroCalendar marks={txnDays} /></RetroWindow>
          <AskWindow />
          <QuickActions />
          <ProgressWindow
            percent={expensesPct}
            message={pv ? pv.message : "Spend progress appears once you have a previous cycle to compare with."}
          />
        </aside>
      </div>

      <div className="space-y-4">
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
                  <p className="text-xs text-muted-foreground">{savings?.capacity_message}</p>
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
        {/* Goals */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Goals</CardTitle>
            <Link href="/goals" className="text-xs text-primary">All goals →</Link>
          </CardHeader>
          <CardContent className="space-y-3">
            {(d.goals ?? []).length === 0 && <p className="text-sm text-muted-foreground">No goals yet. Create a purchase goal or an emergency fund.</p>}
            {(d.goals ?? []).filter((g) => g.lifecycle !== "COMPLETED").slice(0, 3).map((g) => (
              <div key={g.id} className="space-y-1.5">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{g.name}</span>
                  <GoalStatusBadge status={g.status} reason={g.reason} />
                </div>
                <Progress value={g.progress_percent} tone={goalTone(g.status)} />
                <p className="text-xs text-muted-foreground">
                  {inr(g.current_amount)} of {inr(g.target_amount)} · {g.progress_percent.toFixed(1)}% · needs {inrRound(g.required_monthly_contribution)}/month
                </p>
              </div>
            ))}
            {d.goals_combined && d.goals_combined.savings_pace_monthly !== null && d.goals_combined.active_goals > 0 && (
              <p className="border-t border-border pt-2 text-xs text-muted-foreground">
                Your savings pace is about {inrRound(d.goals_combined.savings_pace_monthly)}/month; active goals need {inrRound(d.goals_combined.total_required_monthly)}/month.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Budget commitment */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Budget commitment</CardTitle>
            <Link href="/budgets" className="text-xs text-primary">Budgets →</Link>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {d.commitments && !d.commitments.error && d.commitments.monthly_budget != null ? (
              <>
                <div className="flex justify-between"><span className="text-muted-foreground">Monthly budget</span><span className="tabular-nums">{inr(d.commitments.monthly_budget)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Already spent</span><span className="tabular-nums">{inr(d.commitments.already_spent)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Expected recurring</span><span className="tabular-nums">{inr(d.commitments.upcoming_recurring_expected)}</span></div>
                <div className="flex justify-between font-medium"><span>Committed</span><span className="tabular-nums">{inr(d.commitments.committed_total)}</span></div>
                <Progress value={d.commitments.percent_of_budget_committed ?? 0} tone={(d.commitments.percent_of_budget_committed ?? 0) > 100 ? "negative" : (d.commitments.percent_of_budget_committed ?? 0) > 80 ? "warning" : "primary"} />
                <p className="text-xs text-muted-foreground">{inr(d.commitments.remaining_flexible_capacity)} flexible capacity remains.</p>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">Set a savings target or category budgets to see how much of your budget is committed.</p>
            )}
          </CardContent>
        </Card>

        {/* Upcoming obligations + summary */}
        <Card>
          <CardHeader><CardTitle>Upcoming obligations</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            {(d.upcoming_obligations?.items ?? []).length === 0 && <p className="text-xs text-muted-foreground">No recurring payments are expected in the next 30 days.</p>}
            {(d.upcoming_obligations?.items ?? []).slice(0, 5).map((i) => (
              <div key={i.merchant} className="flex justify-between"><span>{i.merchant} <span className="text-xs text-muted-foreground">{dateShort(i.expected_at)}</span></span><span className="tabular-nums">{inr(i.amount)}</span></div>
            ))}
            {d.latest_summary && (
              <div className="border-t border-border pt-2 text-xs">
                <Link href={`/summaries/${d.latest_summary.id}`} className="text-primary">Latest summary: {d.latest_summary.title.replace("Financial summary: ", "")} →</Link>
                {(d.open_action_count ?? 0) > 0 && <p className="mt-1 text-muted-foreground">{d.open_action_count} open action item{d.open_action_count === 1 ? "" : "s"}</p>}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

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
            <Link href="/chat" className="inline-block text-xs text-primary">Ask Penny about this →</Link>
          </CardContent>
        </Card>
        {me?.demo_mode && <SimulatorPanel accountId={account.id} needsTarget={Boolean(savings?.needs_target)} />}
      </div>

        <RetroWindow title="Recurring Commitments">
          <div className="space-y-1 text-sm">
            {d.recurring && d.recurring.count > 0 ? (
              <>
                <p>{d.recurring.count} recurring payments, about <span className="font-bold">{inr(d.recurring.monthly_total)}</span>/month</p>
                {d.upcoming_obligations && d.upcoming_obligations.items.length > 0 && (
                  <p className="text-xs">Next 30 days: {inr(d.upcoming_obligations.total)} expected across {d.upcoming_obligations.items.length} payment(s)</p>
                )}
              </>
            ) : (
              <p className="text-xs">No recurring payments detected yet (needs at least 3 evenly spaced payments).</p>
            )}
          </div>
        </RetroWindow>
      </div>
    </div>
  );
}
