"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Session } from "@supabase/supabase-js";
import { getSupabase } from "@/lib/supabase";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

interface AuthState {
  session: Session | null;
  userId: string | null;
  me: Me | null;
  loading: boolean;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthState>({ session: null, userId: null, me: null, loading: true, signOut: async () => {} });
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const sb = getSupabase();
    sb.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data } = sb.auth.onAuthStateChange((_evt, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!session) {
      setMe(null);
      return;
    }
    api<Me>("/me").then(setMe).catch(() => setMe(null));
  }, [session?.user.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const value = useMemo<AuthState>(
    () => ({ session, userId: session?.user.id ?? null, me, loading, signOut: async () => void (await getSupabase().auth.signOut()) }),
    [session, me, loading],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !session) router.replace("/login");
  }, [loading, session, router]);
  if (loading || !session) return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Loading…</div>;
  return <>{children}</>;
}
