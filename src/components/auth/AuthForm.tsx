"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getSupabase, supabaseConfigured } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";

const DEMO = { email: "demo@finpilot.test", password: "FinPilot-Demo-2026" };

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const sb = getSupabase();
    if (mode === "login") {
      const { error } = await sb.auth.signInWithPassword({ email, password });
      if (error) setError(error.message);
      else router.replace("/dashboard");
    } else {
      const { data, error } = await sb.auth.signUp({ email, password, options: { data: { display_name: name } } });
      if (error) setError(error.message);
      else if (!data.session) setNotice("Check your email to confirm your account, then sign in.");
      else router.replace("/dashboard");
    }
    setBusy(false);
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mb-2 inline-flex items-center gap-2">
            <span aria-hidden className="text-2xl">💾</span>
            <h1 className="font-pixel text-3xl font-bold">FinPilot.exe</h1>
          </div>
          <p className="text-sm">Your money, explained from your own data.</p>
        </div>
        {!supabaseConfigured && (
          <p className="mb-4 retro-note p-3 text-xs">
            Supabase is not configured. Copy <code>.env.local.example</code> to <code>.env.local</code> and set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
          </p>
        )}
        <Card>
          <div className="retro-titlebar"><span className="font-pixel text-[13px] font-semibold uppercase">{mode === "login" ? "Sign in" : "Create account"}</span></div>
          <form onSubmit={submit} className="space-y-4 p-5">
            {mode === "register" && (
              <div className="space-y-1.5">
                <Label>Name</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Email</Label>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
            </div>
            <div className="space-y-1.5">
              <Label>Password</Label>
              <Input type="password" minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete={mode === "login" ? "current-password" : "new-password"} />
            </div>
            {error && <p className="text-sm text-[#e00000]">{error}</p>}
            {notice && <p className="text-sm text-[#15803d]">{notice}</p>}
            <Button className="w-full" disabled={busy} type="submit">
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </Button>
            {mode === "login" && (
              <Button type="button" variant="secondary" className="w-full" onClick={() => { setEmail(DEMO.email); setPassword(DEMO.password); }}>
                Fill demo account
              </Button>
            )}
          </form>
        </Card>
        <p className="mt-4 text-center text-sm">
          {mode === "login" ? (
            <>New here? <Link href="/register" className="font-bold underline">Create an account</Link></>
          ) : (
            <>Already registered? <Link href="/login" className="font-bold underline">Sign in</Link></>
          )}
        </p>
      </div>
    </main>
  );
}
