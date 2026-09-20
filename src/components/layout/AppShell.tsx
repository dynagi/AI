"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { RequireAuth, useAuth } from "@/components/providers/AuthProvider";
import { LedgerProvider, useLedger } from "@/components/providers/LedgerProvider";
import { cn } from "@/lib/utils";
import { Plant, Smile, Sprite } from "@/components/retro/Sprite";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: "🏠" },
  { href: "/chat", label: "Ask Penny", icon: "💬" },
  { href: "/transactions", label: "Transactions", icon: "📄" },
  { href: "/budgets", label: "Budgets", icon: "📁" },
  { href: "/goals", label: "Goals", icon: "🎯" },
  { href: "/insights", label: "Insights", icon: "📊" },
  { href: "/subscriptions", label: "Subscriptions", icon: "🗓️" },
  { href: "/comparisons", label: "Comparisons", icon: "📈" },
  { href: "/summaries", label: "Reports", icon: "📑" },
  { href: "/settings", label: "Settings", icon: "⚙️" },
];

const MENU = [
  { label: "File", href: "/settings" },
  { label: "Edit", href: "/transactions?add=1" },
  { label: "View", href: "/dashboard" },
  { label: "Tools", href: "/comparisons" },
  { label: "Help", href: "/chat" },
];

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(href + "/");
}

function LiveBadge() {
  const { live } = useLedger();
  const cfg = {
    live: { dot: "bg-[#16A34A] live-dot", text: "LIVE", title: "Connected to Supabase Realtime" },
    connecting: { dot: "bg-[#F5C400] live-dot", text: "CONNECTING", title: "Connecting to Supabase Realtime" },
    offline: { dot: "bg-[#7f7f7f]", text: "POLLING", title: "Realtime is not connected; refreshing every 15 seconds" },
  }[live];
  return (
    <span title={cfg.title} className="retro-sunken inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] font-bold">
      <span className={cn("h-2 w-2 border border-black", cfg.dot)} />
      {cfg.text}
    </span>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { me, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  const current = NAV.find((n) => isActive(pathname, n.href));

  const doSignOut = async () => {
    await signOut();
    router.replace("/login");
  };

  const navList = (
    <nav className="flex flex-col gap-1">
      {NAV.map(({ href, label, icon }) => (
        <Link
          key={href}
          href={href}
          onClick={() => setOpen(false)}
          className={cn(
            "flex items-center gap-3 border-2 px-2 py-2 text-[14px] font-semibold text-black",
            isActive(pathname, href) ? "border-black bg-[#B79AEF] shadow-[inset_2px_2px_0_#d9c9f7,inset_-2px_-2px_0_#8a68d8]" : "border-transparent hover:border-black hover:bg-white/60",
          )}
        >
          <span aria-hidden className="w-6 text-center text-lg">{icon}</span>
          {label}
        </Link>
      ))}
    </nav>
  );

  const dateStr = now ? now.toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short", year: "numeric" }) : "";
  const timeStr = now ? now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "";
  const name = (me?.display_name || me?.email?.split("@")[0] || "User").split(" ")[0];

  return (
    <div className="flex min-h-screen flex-col pb-12">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-1 px-3 pt-3 md:px-4">
        <Link href="/dashboard" className="flex items-center gap-3">
          <Sprite px={3} palette={{ k: "#000", p: "#9B72E8", w: "#fff" }} rows={[
            "..........kk",
            "......kk..kp",
            "......kp..kp",
            "..kk..kp..kp",
            "..kp..kp..kp",
            "..kp..kp..kp",
            "kkkkkkkkkkkk",
          ]} />
          <div>
            <p className="font-pixel text-3xl font-bold leading-none">FinPilot</p>
            <p className="text-[11px]">Your Money. Smarter.</p>
          </div>
        </Link>
        <button className="retro-bevel px-2 py-0.5 text-xs font-bold md:hidden" onClick={() => setOpen((v) => !v)} aria-label="Toggle menu">
          ☰ MENU
        </button>
        <div className="flex min-w-0 flex-1 items-center gap-1 border-b-2 border-black/60 pb-1">
          {MENU.map((m) => (
            <Link key={m.label} href={m.href} className="hidden px-2 py-0.5 text-[14px] hover:bg-[#B79AEF] sm:inline">{m.label}</Link>
          ))}
          <div className="ml-auto flex items-center gap-3 text-[13px]">
            <span className="hidden lg:inline" suppressHydrationWarning>{dateStr} &nbsp;|&nbsp; {timeStr}</span>
            <span className="hidden sm:inline"><LiveBadge /></span>
            <span className="retro-sunken flex items-center gap-2 py-0.5 pl-1 pr-2">
              <span aria-hidden className="text-lg">🧑</span>
              <span className="hidden font-bold sm:inline">{name}</span>
              <button className="retro-bevel px-1.5 text-[11px] font-bold" onClick={doSignOut} title="Sign out">Sign out</button>
            </span>
          </div>
        </div>
      </header>

      <div className="flex flex-1 gap-4 p-3 md:p-4">
        <aside className="hidden w-56 shrink-0 md:block">
          <div className="sticky top-3 flex min-h-[calc(100vh-9rem)] flex-col gap-4">
            <div className="border-2 border-black bg-mint-accent/40 p-2 shadow-[3px_3px_0_#000]">{navList}</div>
            <div className="mt-auto space-y-3">
              <Plant />
              <div className="retro-note flex items-center gap-2 p-3 text-xs">
                <p className="font-bold">Good<br />Money Habits<br />Better Tomorrows!</p>
                <Smile />
              </div>
            </div>
          </div>
        </aside>
        {open && (
          <div className="fixed inset-x-2 top-24 z-40 md:hidden">
            <div className="retro-window">
              <div className="retro-titlebar" data-tone="grey">
                <span className="font-pixel text-[13px] font-semibold uppercase">Navigation</span>
                <button className="retro-winbtn" onClick={() => setOpen(false)} aria-label="Close">×</button>
              </div>
              <div className="p-2">{navList}</div>
            </div>
          </div>
        )}
        <main className="min-w-0 flex-1">{children}</main>
      </div>

      <footer className="retro-taskbar fixed inset-x-0 bottom-0 z-30 flex h-10 items-center gap-2 px-2">
        <Link href="/dashboard" className="retro-bevel font-pixel px-3 py-1 text-sm font-bold">
          ⊞ Start
        </Link>
        <span className="retro-sunken max-w-[50%] flex-1 truncate px-2 py-0.5 text-xs font-semibold sm:max-w-[240px] sm:flex-none">
          📊 FinPilot.exe{current ? ` — ${current.label}` : ""}
        </span>
        <span className="hidden truncate text-[11px] lg:inline">
          {me?.demo_mode ? "Demo data · " : ""}FinPilot analyses your data; it does not give investment advice.
        </span>
        <span className="retro-sunken ml-auto px-2 py-0.5 text-xs font-bold">{timeStr || "--:--"}</span>
      </footer>
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
