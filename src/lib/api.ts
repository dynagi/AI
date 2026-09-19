import { getSupabase } from "./supabase";

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

type Init = { method?: string; json?: unknown; form?: FormData };

export async function api<T>(path: string, init: Init = {}): Promise<T> {
  const { data } = await getSupabase().auth.getSession();
  const headers: Record<string, string> = {};
  if (data.session?.access_token) headers.Authorization = `Bearer ${data.session.access_token}`;
  let body: BodyInit | undefined;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  } else if (init.form) {
    body = init.form;
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method: init.method ?? (body ? "POST" : "GET"), headers, body });
  } catch {
    throw new ApiError("Can't reach the FinPilot server. Make sure the backend is running.", 0);
  }

  const text = await res.text();
  let parsed: any = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok) {
    let msg = "Something went wrong. Please try again.";
    const detail = parsed?.detail;
    if (typeof detail === "string") msg = detail;
    else if (Array.isArray(detail) && detail.length) msg = detail.map((d: any) => d.msg ?? String(d)).join("; ");
    throw new ApiError(msg, res.status);
  }
  return parsed as T;
}
