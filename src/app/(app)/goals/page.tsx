"use client";

import { useEffect, useState } from "react";
import { Pause, Play, Plus, CheckCircle2, Pencil } from "lucide-react";
import { api } from "@/lib/api";
import { useLedgerData } from "@/hooks/useLedgerData";
import { useLedger } from "@/components/providers/LedgerProvider";
import type { GoalAnalysis, GoalsCombined } from "@/lib/types";
import { dateLong, inr, inrRound, num } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { GOAL_TYPE_LABEL, GoalStatusBadge, goalTone } from "@/components/goals/GoalBits";

interface Resp {
  goals: GoalAnalysis[];
  combined: GoalsCombined;
  goal_types: string[];
  priorities: string[];
}

function GoalCard({ g, onChange }: { g: GoalAnalysis; onChange: () => void }) {
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [edit, setEdit] = useState({ name: g.name, target_amount: String(num(g.target_amount)), target_date: g.target_date.slice(0, 10), priority: g.priority });

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      onChange();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const contribute = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await api(`/goals/${g.id}/contributions`, { json: { amount: Number(amount) } });
      setAmount("");
    });
  };
  const setStatus = (status: string) => run(() => api(`/goals/${g.id}`, { method: "PATCH", json: { status } }));
  const save = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await api(`/goals/${g.id}`, { method: "PATCH", json: { name: edit.name, target_amount: Number(edit.target_amount), target_date: edit.target_date, priority: edit.priority } });
      setEditing(false);
    });
  };

  const active = g.lifecycle === "ACTIVE";
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <p className="text-xs uppercase tracking-wider text-muted-foreground">{GOAL_TYPE_LABEL[g.goal_type]} · {g.priority.toLowerCase()} priority</p>
          <h3 className="mt-0.5 text-lg font-semibold">{g.name}</h3>
        </div>
        <GoalStatusBadge status={g.status} reason={g.reason} />
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-baseline justify-between">
          <span className="text-2xl font-semibold tabular-nums">{inr(g.current_amount)}</span>
          <span className="text-sm text-muted-foreground">of {inr(g.target_amount)} · {g.progress_percent.toFixed(1)}%</span>
        </div>
        <Progress value={g.progress_percent} tone={goalTone(g.status)} />

        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div><dt className="text-xs text-muted-foreground">Remaining</dt><dd className="tabular-nums">{inr(g.remaining_amount)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Target date</dt><dd>{dateLong(g.target_date)}{g.days_remaining > 0 ? ` · ${g.days_remaining} days left` : " · date passed"}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Needs per month</dt><dd className="tabular-nums">{inrRound(g.required_monthly_contribution)}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Available for this goal</dt><dd className="tabular-nums">{g.available_monthly_savings !== null ? inrRound(g.available_monthly_savings) : "n/a"}</dd></div>
          <div className="col-span-2"><dt className="text-xs text-muted-foreground">Projected completion</dt><dd>{g.projected_completion_date ? dateLong(g.projected_completion_date) : "Not enough data to project"}</dd></div>
        </dl>

        <p className={`rounded-md border p-3 text-xs ${g.status === "BEHIND" || g.status === "AT_RISK" ? "border-warning/40 bg-warning/10" : "border-border bg-secondary/40"}`}>{g.message}</p>

        {g.lifecycle !== "COMPLETED" && (
          <form onSubmit={contribute} className="flex gap-2">
            <div className="relative flex-1">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">₹</span>
              <Input className="pl-7" type="number" min="1" step="1" required placeholder="Add contribution" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
            <Button type="submit" size="sm" className="h-10" disabled={busy || !amount}><Plus className="h-4 w-4" /> Add</Button>
          </form>
        )}

        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={() => setEditing((v) => !v)}><Pencil className="h-3.5 w-3.5" /> Edit</Button>
          {active && <Button size="sm" variant="ghost" disabled={busy} onClick={() => setStatus("PAUSED")}><Pause className="h-3.5 w-3.5" /> Pause</Button>}
          {g.lifecycle === "PAUSED" && <Button size="sm" variant="ghost" disabled={busy} onClick={() => setStatus("ACTIVE")}><Play className="h-3.5 w-3.5" /> Resume</Button>}
          {g.lifecycle !== "COMPLETED" && <Button size="sm" variant="ghost" disabled={busy} onClick={() => setStatus("COMPLETED")}><CheckCircle2 className="h-3.5 w-3.5" /> Complete</Button>}
          {g.lifecycle === "COMPLETED" && g.status !== "COMPLETED" && <Button size="sm" variant="ghost" disabled={busy} onClick={() => setStatus("ACTIVE")}>Reopen</Button>}
        </div>

        {editing && (
          <form onSubmit={save} className="grid gap-2 rounded-md border border-border p-3 sm:grid-cols-2">
            <div className="space-y-1 sm:col-span-2"><Label>Name</Label><Input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} required /></div>
            <div className="space-y-1"><Label>Target (₹)</Label><Input type="number" min="1" value={edit.target_amount} onChange={(e) => setEdit({ ...edit, target_amount: e.target.value })} required /></div>
            <div className="space-y-1"><Label>Target date</Label><Input type="date" value={edit.target_date} onChange={(e) => setEdit({ ...edit, target_date: e.target.value })} required /></div>
            <div className="space-y-1"><Label>Priority</Label>
              <Select value={edit.priority} onChange={(e) => setEdit({ ...edit, priority: e.target.value as GoalAnalysis["priority"] })}>
                {["HIGH", "MEDIUM", "LOW"].map((p) => <option key={p}>{p}</option>)}
              </Select>
            </div>
            <div className="flex items-end"><Button type="submit" size="sm" disabled={busy}>Save changes</Button></div>
          </form>
        )}
        {err && <p className="text-xs text-negative">{err}</p>}
      </CardContent>
    </Card>
  );
}

export default function GoalsPage() {
  const { bump } = useLedger();
  const { data, error, loading } = useLedgerData<Resp>("/goals");
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("new") === "1") setShow(true);
  }, []);
  const [form, setForm] = useState({ name: "", goal_type: "PURCHASE", target_amount: "", current_amount: "0", target_date: "", priority: "MEDIUM" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api("/goals", { json: { ...form, target_amount: Number(form.target_amount), current_amount: Number(form.current_amount || 0) } });
      setForm({ ...form, name: "", target_amount: "", current_amount: "0" });
      setShow(false);
      bump();
    } catch (e2) {
      setErr((e2 as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error && !data) return <p className="text-sm text-negative">{error}</p>;
  const goals = data?.goals ?? [];
  const c = data?.combined;
  const groups = ["PURCHASE", "EMERGENCY_FUND", "TRAVEL", "EDUCATION", "CUSTOM"].map((t) => ({ t, items: goals.filter((g) => g.goal_type === t) })).filter((x) => x.items.length);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Financial goals</h1>
          <p className="text-sm text-muted-foreground">Long-term goals tracked against your real savings pace. Cash-flow analysis only, not investment advice.</p>
        </div>
        <Button onClick={() => setShow((v) => !v)}><Plus className="h-4 w-4" /> Create goal</Button>
      </div>

      {c && c.active_goals > 0 && (
        <Card className="p-4 text-sm">
          <p>
            Your active goals together need about <span className="font-semibold">{inrRound(c.total_required_monthly)}</span> per month.
            {c.savings_pace_monthly === null
              ? " There is not enough cycle history yet to estimate your monthly savings."
              : num(c.savings_pace_monthly) <= 0
                ? <> Your current cycle is projected to end {inrRound(Math.abs(num(c.savings_pace_monthly)))} short of its income, so nothing is available for goals at this pace.</>
                : <> Based on your recent cycles you are saving about <span className="font-semibold">{inrRound(c.savings_pace_monthly)}</span> per month
                  {num(c.savings_pace_monthly) >= num(c.total_required_monthly) ? ", which covers all of them." : ", which does not cover all of them, so higher-priority goals are funded first."}</>}
          </p>
          {c.pace.basis === "history_and_current_cycle" && c.pace.current_projected !== null && (
            <p className="mt-1 text-xs text-muted-foreground">
              Pace uses the lower of your recent average ({inrRound(c.pace.history_average)}) and this cycle's projected savings ({inrRound(c.pace.current_projected)}), so a spending spike now affects your goals.
            </p>
          )}
        </Card>
      )}

      {show && (
        <Card>
          <CardContent className="pt-5">
            <form onSubmit={create} className="grid gap-3 sm:grid-cols-6">
              <div className="space-y-1.5 sm:col-span-3"><Label>Goal name</Label><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="New laptop" /></div>
              <div className="space-y-1.5 sm:col-span-3"><Label>Type</Label>
                <Select value={form.goal_type} onChange={(e) => setForm({ ...form, goal_type: e.target.value })}>
                  {(data?.goal_types ?? []).map((t) => <option key={t} value={t}>{GOAL_TYPE_LABEL[t]}</option>)}
                </Select>
              </div>
              <div className="space-y-1.5 sm:col-span-2"><Label>Target amount (₹)</Label><Input type="number" min="1" required value={form.target_amount} onChange={(e) => setForm({ ...form, target_amount: e.target.value })} /></div>
              <div className="space-y-1.5 sm:col-span-2"><Label>Already saved (₹)</Label><Input type="number" min="0" value={form.current_amount} onChange={(e) => setForm({ ...form, current_amount: e.target.value })} /></div>
              <div className="space-y-1.5 sm:col-span-2"><Label>Target date</Label><Input type="date" required value={form.target_date} onChange={(e) => setForm({ ...form, target_date: e.target.value })} /></div>
              <div className="space-y-1.5 sm:col-span-2"><Label>Priority</Label>
                <Select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>{["HIGH", "MEDIUM", "LOW"].map((p) => <option key={p}>{p}</option>)}</Select>
              </div>
              <div className="flex items-end sm:col-span-4">{err && <p className="mr-3 text-sm text-negative">{err}</p>}<Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create goal"}</Button></div>
            </form>
          </CardContent>
        </Card>
      )}

      {goals.length === 0 && <p className="text-sm text-muted-foreground">No goals yet. Create a purchase goal, an emergency fund or anything else you are saving for.</p>}

      {groups.map(({ t, items }) => (
        <section key={t} className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground">{GOAL_TYPE_LABEL[t]}{items.length > 1 ? " goals" : " goal"}</h2>
          <div className="grid gap-4 md:grid-cols-2">{items.map((g) => <GoalCard key={g.id} g={g} onChange={bump} />)}</div>
        </section>
      ))}
    </div>
  );
}
