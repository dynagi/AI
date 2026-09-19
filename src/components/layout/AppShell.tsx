"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRouter } from "next/navigation";
import { BarChart3, GitCompareArrows, LayoutDashboard, List, PiggyBank, Plug, Sparkles, Target } from "lucide-react";
import { RequireAuth, useAuth } from "@/components/providers/AuthProvider";
import { LedgerProvider, useLedger } from "@/components/providers/LedgerProvider";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chat", label: "Ask FinPilot", icon: Sparkles },
  { href: "/transactions", label: "Transactions", icon: List },
  { href: "/comparisons", label: "Comparisons", icon: GitCompareArrows },
  { href: "/goals", label: "Savings Goal", icon: Target },
  { href: "/budgets", label: "Budgets", icon: PiggyBank },
  { href: "/settings", label: "Data Sources", icon: Plug },
];

function LiveBadge() {
  const { live } = useLedger();
  const cfg = {
    live: { dot: "bg-positive live-dot", text: "Live", title: "Connected to Supabase Realtime" },
    connecting: { dot: "bg-warning live-dot", text: "Connecting", title: "Connecting to Supabase Realtime" },
    offline: { dot: "bg-muted-foreground", text: "Polling", title: "Realtime is not connected; refreshing every 15 seconds" },
  }[live];
  return (
    <span title={cfg.title} className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground">
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.text}
    </span>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { me, signOut } = useAuth();

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-border p-4 md:flex">
        <div className="mb-6 flex items-center gap-2 px-2 py-2">
          <BarChart3 className="h-5 w-5 text-primary" />
          <span className="text-lg font-semibold tracking-tight">FinPilot</span>
        </div>
        <nav className="flex-1 space-y-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                pathname === href ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="border-t border-border px-2 pt-3">
          <p className="truncate text-xs text-muted-foreground">{me?.email ?? "Signed in"}</p>
          <button
            className="mt-1 text-xs text-muted-foreground hover:text-foreground"
            onClick={async () => {
              await signOut();
              router.replace("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex items-center justify-between border-b border-border px-4 py-3 md:px-8">
          <nav className="flex gap-1 overflow-x-auto md:hidden">
            {NAV.map(({ href, label }) => (
              <Link key={href} href={href} className={cn("whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs", pathname === href ? "bg-primary/15 text-primary" : "text-muted-foreground")}>
                {label}
              </Link>
            ))}
          </nav>
          <div className="hidden text-xs text-muted-foreground md:block">Sandbox / demo data. FinPilot analyses your data; it does not give investment advice.</div>
          <LiveBadge />
        </header>
        <main className="p-4 md:p-8">{children}</main>
      </div>
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <LedgerProvider>
        <Shell>{children}</Shell>
      </LedgerProvider>
    </RequireAuth>
  );
}
