"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useLedger } from "@/components/providers/LedgerProvider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function SavingsTargetForm({ initial, cta = "Set target" }: { initial?: number; cta?: string }) {
  const { bump } = useLedger();
  const [value, setValue] = useState(initial ? String(initial) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/savings/target", { method: "PUT", json: { target_amount: Number(value) } });
      bump();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-2">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">₹</span>
          <Input className="pl-7" type="number" min={0} step="100" required placeholder="25000" value={value} onChange={(e) => setValue(e.target.value)} />
        </div>
        <Button type="submit" disabled={busy || !value}>{busy ? "Saving…" : cta}</Button>
      </div>
      {error && <p className="text-xs text-negative">{error}</p>}
    </form>
  );
}
