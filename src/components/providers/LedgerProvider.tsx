"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { getSupabase } from "@/lib/supabase";
import { useAuth } from "./AuthProvider";

export type LiveStatus = "connecting" | "live" | "offline";

interface LedgerState {
  /** Increments whenever the ledger changes (a Realtime event, or a local action calling bump()). Pages refetch on change. */
  version: number;
  bump: () => void;
  live: LiveStatus;
}

const Ctx = createContext<LedgerState>({ version: 0, bump: () => {}, live: "connecting" });
export const useLedger = () => useContext(Ctx);

// Supabase Realtime: the browser subscribes (with the user's own JWT, so RLS applies) to changes on the ledger tables.
// The event only signals "something changed"; the numbers themselves are always re-read from the backend.
const TABLES = [
  "transactions", "financial_accounts", "financial_cycles", "agent_alerts", "financial_insights",
  "financial_goals", "goal_contributions", "monthly_summaries", "monthly_summary_actions",
];

export function LedgerProvider({ children }: { children: React.ReactNode }) {
  const { userId } = useAuth();
  const [version, setVersion] = useState(0);
  const [live, setLive] = useState<LiveStatus>("connecting");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const bump = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setVersion((v) => v + 1), 200); // coalesce bursts (one action touches several tables)
  }, []);

  useEffect(() => {
    if (!userId) return;
    const sb = getSupabase();
    let channel = sb.channel(`ledger:${userId}`);
    for (const table of TABLES) {
      channel = channel.on("postgres_changes", { event: "*", schema: "public", table, filter: `user_id=eq.${userId}` }, bump);
    }
    channel.subscribe((status) => {
      if (status === "SUBSCRIBED") setLive("live");
      else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") setLive("offline");
    });
    return () => {
      void sb.removeChannel(channel);
    };
  }, [userId, bump]);

  // If Realtime is not connected (not enabled, or offline), fall back to gentle polling so the UI still converges.
  useEffect(() => {
    if (live === "live") return;
    const id = setInterval(() => setVersion((v) => v + 1), 15000);
    return () => clearInterval(id);
  }, [live]);

  const value = useMemo(() => ({ version, bump, live }), [version, bump, live]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
