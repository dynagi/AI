import type { Money } from "./format";

export interface Account {
  id: string;
  name: string;
  source: string;
  currency: string;
  status: string;
  current_balance: Money;
  opening_balance: Money;
  last_synced_at: string | null;
}

export interface CategoryRow {
  category: string;
  total: Money;
  count?: number;
  percent?: number;
}

export interface LargestTxn {
  id: string;
  timestamp: string;
  merchant: string | null;
  description: string;
  amount: Money;
  category: string;
}

export interface CycleSummary {
  id: string;
  label: string;
  status: "ACTIVE" | "CLOSED";
  start_at: string;
  end_at: string | null;
  opening_balance: Money;
  carried_over_balance: Money;
  closing_balance: Money;
  income: Money;
  other_inflows: Money;
  refunds: Money;
  expenses: Money;
  net_spend: Money;
  savings: Money;
  savings_rate: number | null;
  savings_target: Money | null;
  transaction_count: number;
  categories: CategoryRow[];
  top_categories: CategoryRow[];
  recurring_expenses: { total: Money; count: number };
  largest_transactions: LargestTxn[];
}

export interface Savings {
  status: "NO_TARGET" | "INSUFFICIENT_DATA" | "ON_TRACK" | "AT_RISK";
  reason: string | null;
  target: Money | null;
  income: Money;
  other_inflows: Money;
  expenses: Money;
  refunds: Money;
  net_spend: Money;
  planned_spend_limit: Money | null;
  remaining_spend_capacity: Money | null;
  estimated_savings: Money;
  required_more_savings: Money | null;
  projected_spend: Money;
  projected_savings: Money;
  projection_basis: string;
  message: string;
  needs_target?: boolean;
  cycle_id?: string;
  cycle?: string;
}

export interface Txn {
  id: string;
  account_id: string;
  timestamp: string;
  description: string;
  merchant: string | null;
  amount: Money;
  signed_amount: Money;
  transaction_type: string;
  category: string;
  source: string;
  balance_after: Money;
  is_recurring: boolean;
  financial_cycle_id: string | null;
}

export interface Alert {
  id: string;
  alert_type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
  evidence: Record<string, unknown>;
}

export interface Insight {
  id: string;
  insight_type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string;
  evidence: Record<string, unknown>;
}

export interface ProgressVsPrevious {
  current: Money;
  previous: Money;
  remaining: Money;
  exceeded_by: Money;
  percent_of_previous: number | null;
  difference: Money;
  change_percent: number | null;
  message: string;
}

export interface Dashboard {
  account: Account | null;
  as_of?: string;
  cycle?: CycleSummary | null;
  previous_cycle?: CycleSummary | null;
  progress_vs_previous?: ProgressVsPrevious | null;
  savings?: Savings | null;
  spending_progress?: { spent: Money; net_spend: Money; planned_spend_limit: Money | null; percent_of_limit: number | null } | null;
  insights?: Insight[];
  alerts?: Alert[];
  unread_alert_count?: number;
  budgets?: { id: string; category: string; amount: Money; spent: Money; remaining: Money; percent_used: number }[];
  recurring?: { count: number; monthly_total: Money };
  upcoming_obligations?: { within_days: number; total: Money; items: { merchant: string; amount: Money; expected_at: string }[] };
  recent_transactions?: Txn[];
}

export interface Me {
  id: string;
  email: string | null;
  display_name: string | null;
  demo_mode: boolean;
  timezone: string;
}
