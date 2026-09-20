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
  recurring_expenses: { total: Money; count: number; items?: { merchant: string; total: Money; count: number }[] };
  budget_usage?: { category: string; budget: Money; spent: Money; percent_used: number }[];
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
  capacity_message?: string;
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
  cashflow_risk?: CashflowRisk;
  upcoming_obligations?: { within_days: number; total: Money; items: { merchant: string; amount: Money; expected_at: string }[] };
  recent_transactions?: Txn[];
  goals?: GoalAnalysis[];
  goals_combined?: GoalsCombined;
  commitments?: Commitments;
  latest_summary?: { id: string; title: string; is_final: boolean } | null;
  open_action_count?: number;
}

export interface Me {
  id: string;
  email: string | null;
  display_name: string | null;
  demo_mode: boolean;
  timezone: string;
}

export type GoalStatus = "ON_TRACK" | "AT_RISK" | "BEHIND" | "COMPLETED" | "PAUSED" | null;

export interface GoalAnalysis {
  id: string;
  name: string;
  goal_type: "PURCHASE" | "EMERGENCY_FUND" | "TRAVEL" | "EDUCATION" | "CUSTOM";
  priority: "LOW" | "MEDIUM" | "HIGH";
  lifecycle: "ACTIVE" | "PAUSED" | "COMPLETED";
  target_amount: Money;
  current_amount: Money;
  remaining_amount: Money;
  progress_percent: number;
  target_date: string;
  days_remaining: number;
  required_monthly_contribution: Money;
  allocated_monthly_savings: Money | null;
  available_monthly_savings: Money | null;
  status: GoalStatus;
  reason: string | null;
  projected_completion_date: string | null;
  message: string;
}

export interface GoalsCombined {
  active_goals: number;
  total_required_monthly: Money;
  savings_pace_monthly: Money | null;
  unallocated_monthly_savings: Money | null;
  pace: { history_average: Money | null; history_cycles: number; current_projected: Money | null; effective: Money | null; basis: string };
}

export interface RecurringItem {
  merchant: string;
  amount: Money;
  occurrences: number;
  expected_at: string;
  category: string;
  frequency: string;
}

export interface Commitments {
  error?: string;
  message?: string;
  budget_basis?: "savings_target" | "category_budgets" | "none";
  budget_basis_explained?: string;
  monthly_budget?: Money | null;
  already_spent?: Money;
  upcoming_recurring_expected?: Money;
  upcoming_recurring_items?: RecurringItem[];
  committed_total?: Money;
  remaining_flexible_capacity?: Money | null;
  percent_of_budget_committed?: number | null;
  calculation?: string;
}

export interface BudgetRow {
  id: string;
  category: string;
  amount: Money;
  spent: Money;
  remaining: Money;
  percent_used: number;
  upcoming_recurring: Money;
  committed: Money;
  projected_spend: Money;
  status: "ON_TRACK" | "AT_RISK" | "OVER_BUDGET";
}

export interface SummaryRow {
  id: string;
  financial_cycle_id: string;
  title: string;
  period_start: string;
  period_end: string | null;
  income_total: Money;
  expense_total: Money;
  savings_total: Money;
  savings_rate: Money | null;
  top_category: string | null;
  previous_cycle_expenses: Money | null;
  expense_change: Money | null;
  is_final: boolean;
  generated_at: string;
  open_actions?: number;
}

export interface ActionItem {
  id: string;
  action_key: string;
  title: string;
  description: string;
  priority: "LOW" | "MEDIUM" | "HIGH";
  category: string | null;
  evidence: Record<string, unknown>;
  status: "OPEN" | "COMPLETED" | "DISMISSED";
}

export interface SummaryDetail extends SummaryRow {
  content: {
    overview: Record<string, Money | number | null>;
    top_categories: CategoryRow[];
    categories: CategoryRow[];
    previous_comparison: {
      previous_label: string;
      previous_expenses: Money;
      difference: Money;
      change_percent: number | null;
      top_increases: { category: string; a: Money; b: Money; change: Money; change_percent: number | null }[];
      top_decreases: { category: string; a: Money; b: Money; change: Money; change_percent: number | null }[];
    } | null;
    recurring: { paid_in_cycle: Money; payments_in_cycle: number; active_recurring_payments: number; estimated_monthly_total: Money };
    unusual_activity: { type: string; message: string; evidence: Record<string, unknown> }[];
    goals: GoalAnalysis[];
    budgets: { category: string; amount: Money; spent: Money; percent_used: number; status: string }[];
    observations: { type: string; text: string; evidence: Record<string, unknown> }[];
  };
  actions: ActionItem[];
}

export type RiskLevel = "SAFE" | "WATCH" | "AT_RISK" | "SHORTFALL";

export interface CashflowRisk {
  risk_level: RiskLevel;
  headline: string;
  warning_message: string;
  suggested_action: string | null;
  current_balance: Money;
  upcoming_amount: Money;
  expected_income: Money;
  projected_balance: Money;
  shortfall_amount: Money;
  safety_buffer: Money;
  covered_by_income: boolean;
  savings_impact: { status: string; at_risk: boolean; message: string };
  budget_impact: { status: string; at_risk: boolean; message: string };
  upcoming_payments: { merchant: string; amount: Money; due_at: string; due_label: string; days_remaining: number; priority: "high" | "medium" | "low" }[];
  timeline: { kind: "start" | "income" | "payment"; date_label: string; label: string; amount: Money; balance_after: Money; shortfall: boolean }[];
  horizon_days: number;
}
