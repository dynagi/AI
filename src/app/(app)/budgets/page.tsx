"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useLedgerData } from "@/hooks/useLedgerData";
import { useLedger } from "@/components/providers/LedgerProvider";
import { inr, type Money } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";

interface Resp {
  budgets: { id: string; category: string; amount: Money; spent: Money; remaining: Money; percent_used: number }[];
  categories: string[];
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

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Budgets</h1>
        <p className="text-sm text-muted-foreground">Category limits measured against your current financial cycle. These are separate from your savings target.</p>
      </div>

      <Card>
        <CardContent className="pt-5">
          <form onSubmit={save} className="flex flex-wrap items-end gap-3">
            <div className="w-48 space-y-1.5">
              <Label>Category</Label>
              <Select value={category} onChange={(e) => setCategory(e.target.value)}>
                {(data?.categories ?? ["Food"]).filter((c) => !["Salary", "Transfer"].includes(c)).map((c) => <option key={c}>{c}</option>)}
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
      {data && data.budgets.length === 0 && <p className="text-sm text-muted-foreground">No budgets yet.</p>}

      <div className="space-y-3">
        {(data?.budgets ?? []).map((b) => (
          <Card key={b.id}>
            <CardContent className="space-y-2 pt-5">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">{b.category}</p>
                <div className="flex items-center gap-3">
                  <p className="text-sm tabular-nums text-muted-foreground">{inr(b.spent)} / {inr(b.amount)}</p>
                  <button aria-label={`Delete ${b.category} budget`} className="text-muted-foreground hover:text-negative" onClick={() => remove(b.id)}><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>
              <Progress value={b.percent_used} tone={b.percent_used >= 100 ? "negative" : b.percent_used >= 80 ? "warning" : "primary"} />
              <p className="text-xs text-muted-foreground">{Math.round(b.percent_used)}% used · {Number(b.remaining) >= 0 ? `${inr(b.remaining)} remaining` : `${inr(Math.abs(Number(b.remaining)))} over budget`}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
