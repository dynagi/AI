import {
  ArrowLeftRight, Car, CircleDollarSign, Film, GraduationCap, HeartPulse, Home, Landmark, Plane, Repeat, Shield,
  ShoppingBag, Sparkles, TrendingUp, Utensils, Wallet, Zap, type LucideIcon,
} from "lucide-react";
import type { Txn } from "@/lib/types";
import { dateShort, inr, num, signedInr, time } from "@/lib/format";
import { cn } from "@/lib/utils";

export const CATEGORY_ICONS: Record<string, LucideIcon> = {
  Food: Utensils, Shopping: ShoppingBag, Transport: Car, Housing: Home, Utilities: Zap, Healthcare: HeartPulse,
  Entertainment: Film, Education: GraduationCap, Travel: Plane, Subscriptions: Repeat, Insurance: Shield,
  "EMI/Loans": Landmark, "Personal Care": Sparkles, Salary: Wallet, Investment: TrendingUp, Transfer: ArrowLeftRight,
  Other: CircleDollarSign,
};

const TYPE_LABEL: Record<string, string> = {
  SALARY: "Salary", OTHER_INCOME: "Income", TRANSFER_IN: "Money received", TRANSFER_OUT: "Transfer out",
  EXPENSE: "", REFUND: "Refund", INTEREST: "Interest", OTHER: "Other",
};

export default function TxnRow({ t, showBalance = true, showDate = false }: { t: Txn; showBalance?: boolean; showDate?: boolean }) {
  const Icon = CATEGORY_ICONS[t.category] ?? CircleDollarSign;
  const credit = num(t.signed_amount) > 0;
  const label = TYPE_LABEL[t.transaction_type];
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-full", credit ? "bg-positive/15 text-positive" : "bg-secondary text-muted-foreground")}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{t.merchant || t.description}</p>
        <p className="truncate text-xs text-muted-foreground">
          {label ? `${label} · ` : ""}{t.category} · {showDate ? `${dateShort(t.timestamp)}, ` : ""}{time(t.timestamp)}
          {t.is_recurring ? " · recurring" : ""}
        </p>
      </div>
      <div className="text-right">
        <p className={cn("text-sm font-semibold tabular-nums", credit ? "text-positive" : "text-negative")}>{signedInr(t.signed_amount)}</p>
        {showBalance && t.balance_after !== null && <p className="text-xs text-muted-foreground tabular-nums">Balance {inr(t.balance_after)}</p>}
      </div>
    </div>
  );
}
