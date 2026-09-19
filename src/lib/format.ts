// Display formatting only. Every financial number comes from the backend; nothing is calculated here.

export type Money = number | string | null | undefined;

export const num = (v: Money): number => (v === null || v === undefined || v === "" ? 0 : Number(v));

const TZ = "Asia/Kolkata";

export function inr(v: Money, opts: { sign?: boolean } = {}): string {
  const n = num(v);
  const abs = Math.abs(n);
  const frac = Math.round(abs * 100) % 100 !== 0;
  const body = new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: frac ? 2 : 0,
    maximumFractionDigits: frac ? 2 : 0,
  }).format(abs);
  if (n < 0) return `-${body}`;
  return opts.sign && n > 0 ? `+${body}` : body;
}

/** +₹1,000 / -₹160 from a signed amount supplied by the ledger (transactions.signed_amount). */
export const signedInr = (v: Money) => inr(v, { sign: true });

export function time(ts: string): string {
  return new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: TZ })
    .format(new Date(ts))
    .toUpperCase();
}

export function dateLong(ts: string): string {
  return new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: TZ }).format(new Date(ts));
}

export function dateShort(ts: string): string {
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: TZ }).format(new Date(ts));
}

export function dateTime(ts: string): string {
  return `${dateLong(ts)}, ${time(ts)}`;
}

export function dayKey(ts: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date(ts)); // YYYY-MM-DD
}

export function dayLabel(ts: string): string {
  const today = dayKey(new Date().toISOString());
  const yesterday = dayKey(new Date(Date.now() - 86400000).toISOString());
  const k = dayKey(ts);
  if (k === today) return "Today";
  if (k === yesterday) return "Yesterday";
  return dateLong(ts);
}

export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return "n/a";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

/** Whole-rupee display for estimates and projections (they are not exact ledger amounts). */
export const inrRound = (v: Money): string => inr(Math.round(num(v)));
