import Link from "next/link";
import { RetroWindow } from "@/components/retro/Window";

const STEPS = [
  { t: "Add your data", d: "Open Settings and click Connect Demo Bank to load sample transactions (sandbox data, not a real bank). You can also import a CSV or add a transaction by hand.", href: "/settings", cta: "Go to Settings" },
  { t: "Set a savings target", d: "On the Dashboard, tell FinPilot how much you want to save this cycle. FinPilot never picks a target for you.", href: "/dashboard", cta: "Go to Dashboard" },
  { t: "Read your Briefing and warnings", d: "The top of the Dashboard shows today's briefing and any upcoming payment that could cause trouble.", href: "/dashboard", cta: "Open Dashboard" },
  { t: "Ask Penny", d: "Penny is the assistant. Ask about spending, bills or goals in plain English. Every number she gives comes from your own data.", href: "/chat", cta: "Ask Penny" },
];

const PAGES = [
  { icon: "🏠", name: "Dashboard", href: "/dashboard", d: "Your money at a glance: balance, income, expenses, savings, alerts, the daily briefing, upcoming payments and the What-if tool." },
  { icon: "💬", name: "Ask Penny", href: "/chat", d: "Chat with the assistant. Ask questions like “How much did I spend this month?” or “Can I afford my upcoming payments?”." },
  { icon: "📄", name: "Transactions", href: "/transactions", d: "Every transaction in your account. Search, filter and add your own." },
  { icon: "📁", name: "Budgets", href: "/budgets", d: "Set a limit per category (for example Food) and see how much of it is used and committed." },
  { icon: "🎯", name: "Goals", href: "/goals", d: "Longer-term goals such as a laptop, a trip or an emergency fund, and whether your saving pace is on track." },
  { icon: "📊", name: "Insights", href: "/insights", d: "Automatic observations from your data, such as a category that jumped compared with your usual." },
  { icon: "🗓️", name: "Subscriptions", href: "/subscriptions", d: "Recurring payments FinPilot has detected: Netflix, rent, bills. A payment is only called recurring after 3 similar payments at even intervals." },
  { icon: "📈", name: "Comparisons", href: "/comparisons", d: "This cycle against the previous one, by category, so you can see what changed." },
  { icon: "📑", name: "Reports", href: "/summaries", d: "A monthly summary of each finished cycle, with action items." },
  { icon: "⚙️", name: "Settings", href: "/settings", d: "Connect a data source (Demo Bank, CSV import), see sync status and manage consent." },
];

const DASH = [
  ["Welcome bar", "Your name, the account, the current cycle and when the data was last updated."],
  ["Four stat cards", "Current Balance (money in the account now, not income), Monthly Income, Monthly Expenses and your Savings target."],
  ["Alerts", "Important things FinPilot noticed, for example spending above your usual. Dismiss them with the ×."],
  ["Today's Briefing", "A few short lines: cash-flow status, next payment, your spending streak and savings status. The Chill / Coach / Roast buttons change the voice only, never the numbers."],
  ["Upcoming Money Commitments", "Payments due soon, how much, and when. The coloured box says whether you have enough. Click View Details to see the step-by-step timeline."],
  ["What if…?", "Type something you might buy and how many days from now. FinPilot shows how it would change your status. Nothing is recorded or paid."],
  ["Spending overview and trend", "Where the money went by category, and how spending moved over recent cycles."],
  ["Recent transactions", "The latest entries in your account."],
  ["Calendar", "Days with activity are marked."],
  ["Demo Bank Simulator", "Demo only. Post fake salary, expenses and refunds to watch the whole app react. The cash-flow demo button sets up a shortfall example."],
];

const LEVELS = [
  ["🟢", "Safe", "Upcoming payments are covered and you stay above your safety buffer."],
  ["🟡", "Watch", "Covered, but your balance would drop below your safety buffer, leaving little room."],
  ["🟠", "At risk", "The payments could push you past your spending plan or make your savings target hard to reach."],
  ["🔴", "Shortfall", "Your balance would not be enough for an upcoming payment. Consider adding funds before the due date."],
];

const IDEAS = [
  ["Financial cycle", "A cycle runs from one salary to the next, not by calendar month. “This month” always means your current cycle."],
  ["Balance is not income", "The balance is the money in your account right now. Income is salary and other real earnings."],
  ["Expected income", "FinPilot expects your next salary about one cycle after the last one. If it arrives before a payment, that payment counts as covered."],
  ["Safety buffer", "A minimum balance you want to stay above. The default is ₹5,000."],
  ["Streak", "Days in a row where your non-recurring spending stayed at or under your usual daily amount. Rent and bills don't count against it."],
  ["Recurring payment", "A merchant with at least 3 payments, evenly spaced and with similar amounts."],
];

const ASK = [
  "Do I have any upcoming payments?",
  "Will I have enough money for my subscriptions?",
  "How much have I spent this cycle?",
  "Where did I spend the most?",
  "What if I buy a ₹40,000 phone in 5 days?",
  "Am I on track with my savings target?",
];

export default function GuidePage() {
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <RetroWindow title="User Guide.exe" focused closable={false} bodyClassName="space-y-2 p-4">
        <h1 className="font-pixel text-2xl font-bold">Welcome to FinPilot 👋</h1>
        <p className="text-sm">
          FinPilot reads your own transactions, explains where your money goes and warns you <b>before</b> an upcoming payment can cause trouble.
          Your assistant is <b>Penny</b>. FinPilot only shows information and warnings. It never makes payments, cancels subscriptions or moves money, and it does not give investment advice.
        </p>
      </RetroWindow>

      <RetroWindow title="Start here: 4 steps" bodyClassName="p-3">
        <ol className="space-y-2">
          {STEPS.map((s, i) => (
            <li key={s.t} className="flex gap-3 border-2 border-black bg-white p-2 text-sm">
              <span className="font-pixel text-xl font-bold">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <p className="font-bold">{s.t}</p>
                <p>{s.d}</p>
              </div>
              <Link href={s.href} className="retro-bevel h-fit shrink-0 px-2 py-1 text-xs font-bold">{s.cta}</Link>
            </li>
          ))}
        </ol>
      </RetroWindow>

      <RetroWindow title="Which page is for what" bodyClassName="p-3">
        <ul className="grid gap-2 sm:grid-cols-2">
          {PAGES.map((p) => (
            <li key={p.name} className="border-2 border-black bg-white p-2 text-sm">
              <Link href={p.href} className="font-bold underline">{p.icon} {p.name}</Link>
              <p className="mt-0.5 text-xs">{p.d}</p>
            </li>
          ))}
        </ul>
      </RetroWindow>

      <RetroWindow title="Your Dashboard, section by section" bodyClassName="p-3">
        <dl className="space-y-1.5 text-sm">
          {DASH.map(([k, v]) => (
            <div key={k} className="border-2 border-black bg-white px-2 py-1.5">
              <dt className="font-bold">{k}</dt>
              <dd className="text-xs">{v}</dd>
            </div>
          ))}
        </dl>
      </RetroWindow>

      <RetroWindow title="Warning levels" bodyClassName="space-y-2 p-3">
        <ul className="space-y-1.5 text-sm">
          {LEVELS.map(([icon, name, d]) => (
            <li key={name} className="flex gap-2 border-2 border-black bg-white px-2 py-1.5">
              <span aria-hidden>{icon}</span>
              <span><b>{name}.</b> {d}</span>
            </li>
          ))}
        </ul>
        <p className="text-xs">Example: your balance is ₹1,000 and a ₹2,000 subscription is due in 5 days with no salary before then. That is a 🔴 Shortfall of ₹1,000. If your salary arrives first, the same payment shows as covered.</p>
      </RetroWindow>

      <RetroWindow title="Ask Penny: ideas" bodyClassName="p-3">
        <ul className="grid gap-1.5 text-sm sm:grid-cols-2">
          {ASK.map((q) => (
            <li key={q} className="border-2 border-black bg-[#e3d8fa] px-2 py-1.5">“{q}”</li>
          ))}
        </ul>
        <p className="mt-2 text-xs">Penny answers only from your data. If something is missing, she says so instead of guessing.</p>
      </RetroWindow>

      <RetroWindow title="Words used in FinPilot" bodyClassName="p-3">
        <dl className="space-y-1.5 text-sm">
          {IDEAS.map(([k, v]) => (
            <div key={k} className="border-2 border-black bg-white px-2 py-1.5">
              <dt className="font-bold">{k}</dt>
              <dd className="text-xs">{v}</dd>
            </div>
          ))}
        </dl>
      </RetroWindow>

      <RetroWindow title="Good to know" bodyClassName="space-y-1 p-3 text-xs">
        <p>• This is a demo using sandbox data. Please don't enter real bank passwords, PINs or OTPs. FinPilot never asks for them.</p>
        <p>• Everything updates live: add a transaction and the balance, warnings and briefing refresh without reloading.</p>
        <p>• Stuck? Ask Penny, or reopen this guide any time from the sidebar or Help menu.</p>
      </RetroWindow>
    </div>
  );
}
