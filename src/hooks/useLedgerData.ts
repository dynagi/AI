"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useLedger } from "@/components/providers/LedgerProvider";

/**
 * GETs `path` from the FinPilot API and refetches it whenever the ledger changes (Realtime event or local action),
 * so the screen updates with no page refresh. Stale data stays on screen while a refetch is in flight.
 */
export function useLedgerData<T>(path: string | null) {
  const { version } = useLedger();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (!path) return;
    const mine = ++seq.current;
    try {
      const res = await api<T>(path);
      if (mine === seq.current) {
        setData(res);
        setError(null);
      }
    } catch (e) {
      if (mine === seq.current) setError((e as Error).message);
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    void load();
  }, [load, version]);

  return { data, error, loading, reload: load };
}
