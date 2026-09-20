# FinPilot

An AI-powered personal-finance **decision-support** agent that behaves like a bank-account intelligence system, not a static monthly dashboard. It tracks a real ledger (balance after every transaction), salary-to-salary **financial cycles**, savings targets, recurring payments and unusual spending, and answers questions through a tool-using agent whose every number comes from the database.

It analyses *your own data*. It does not give investment advice.

## Contents
1. [Architecture](#architecture) · 2. [Core accounting rules](#core-accounting-rules) · 3. [Setup](#setup) · 4. [Demo Bank Simulator](#demo-bank-simulator) · 5. [AI agent](#ai-agent) · 6. [Realtime](#realtime) · 7. [Data sources / AA](#data-sources-and-the-aa-sandbox) · 8. [Testing](#testing) · 9. [Security](#security) · 10. [Limits](#known-limits)

## Architecture

```
Next.js + TS + Tailwind + shadcn-style UI + Recharts        (src/)
        │  Supabase Auth (JWT)          ▲  Supabase Realtime (postgres_changes)
        ▼                               │
FastAPI (Python, Pydantic)                                   (backend/app)
  Data Provider ─► Transaction Normalizer ─► Transaction Service (ingest) ─► Supabase PostgreSQL ─► AI Agent
  (Demo Bank | AA sandbox | Manual | CSV)     ledger + cycle engine, recurring, alerts, insights
        │
        └─ LangGraph agent + 25 data tools (backend/app/agent)  ─►  configurable LLM (Gemini default)
```

* **Source of truth: Supabase PostgreSQL.** Schema and seed are plain SQL in `supabase/`. There is no Prisma and no second database.
* **One door into the ledger.** Bank feed, Demo Bank Simulator, manual entry and CSV all become a `RawTransaction`, go through the same normalizer and `ingest()` (`backend/app/services/ingest.py`), and produce identical rows. The agent never knows where a transaction came from.
* **Deterministic finance, LLM only for language.** Balances, cycles, savings maths, alerts and comparisons are plain code over exact `Decimal`s. The LLM can only call read-only tools bound to the signed-in user.
* Money uses `numeric(14,2)` in Postgres and `Decimal` in Python (not floats). I did not use pandas: exact decimal arithmetic matters more than dataframes here.

```
supabase/migrations/001…020_*.sql   schema, goals, summaries, realtime publication, RLS
supabase/seed/demo_*.sql            demo user, account, cycles + targets, 236 transactions, goals, budgets, summaries
backend/app/ledger/engine.py        pure ledger + cycle engine (no DB, fully unit-tested)
backend/app/services/               ingest, ledger_service, alerts, insights, savings, comparison, dashboard, …
backend/app/providers/              FinancialDataProvider interface + demo_bank, aa_sandbox, manual, csv
backend/app/agent/                  LangGraph graph, 25 tools, prompt, LLM factory
backend/tests/                      142 tests (engine, goals, real-Postgres scenarios, RLS, API, agent, CSV)
src/                                Next.js app
```

## Core accounting rules

| Concept | Rule |
|---|---|
| `amount` | Always a positive magnitude. Direction comes from `transaction_type`; `signed_amount` is `+`/`-` (UI shows `+₹1,000` / `-₹160`). |
| Types | `SALARY, OTHER_INCOME, TRANSFER_IN, TRANSFER_OUT, EXPENSE, REFUND, INTEREST, OTHER` |
| Balance | Every transaction stores `balance_after`. The account keeps `opening_balance` (money already there) and `current_balance`. **Neither is ever income.** |
| Income | `SALARY + OTHER_INCOME + INTEREST`. Money from people (`TRANSFER_IN`) raises the balance but is reported as **other inflows**, never salary. |
| Financial cycle | A `SALARY` transaction starts a new cycle **at its exact timestamp** (not midnight, not the calendar month). The previous cycle is closed, never deleted. |
| Cycle balances | `opening_balance` = balance right after the salary; `carried_over_balance` = balance right before it (never income). |
| Dashboard | Current balance, and *current cycle* income / expenses / savings. Historical cycles stay in the database and feed comparisons. |
| Savings target | Chosen by the **user** per cycle (`monthly_savings_targets`). Never invented, never silently carried over. |
| Savings status | `planned spend limit = income − target`. `AT_RISK` if net spend already exceeds it, or if projected spend does (projection assumes the rest of the cycle looks like your last ≤3 cycles). Otherwise `ON_TRACK`. |
| Back-dated data | CSV/manual rows with older timestamps are slotted into the correct cycle and all later balances are recomputed (the ledger is rebuilt deterministically inside a row-locked transaction). |

## Setup

Prerequisites: Node 18+, Python 3.11+, a Supabase project (free tier is fine).

### 1. Database (Supabase)

Apply the migrations, then the seed, to your Supabase project. Pick one:

**A. SQL editor.** Run every file in `supabase/migrations/` in numeric order (001 → 020), then the seed files in this order: `demo_user`, `demo_account`, `demo_cycles`, `demo_transactions`, `demo_goals`, `demo_budgets`, `demo_summaries`. (All migrations are idempotent, so re-running them on a database created by an earlier version is safe.)

**B. From your machine (no CLI needed).**
```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # macOS/Linux: .venv/bin/pip
cp .env.example .env                              # then fill in SUPABASE_URL and SUPABASE_DB_PASSWORD (see below)
.venv/Scripts/python -m scripts.apply_sql all     # migrations + seed, in dependency order
```

**C. Supabase CLI (local).** `supabase start && supabase db reset` applies migrations and `supabase/config.toml` runs the seed in order.

Enable Realtime for the tables (already done by migration 015 via the `supabase_realtime` publication). Seed login: `demo@finpilot.test` / `FinPilot-Demo-2026`.

> `demo_user.sql` inserts into `auth.users`. That is fine in the SQL editor / CLI. If you would rather not seed an auth user, skip it, register through the app instead, then click **Connect Demo Bank**: it loads the *same* dataset for your user.

### 2. Backend
```bash
cd backend
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```
Environment (`backend/.env`, template in `backend/.env.example`):

| Variable | What |
|---|---|
| `SUPABASE_URL` | `https://<ref>.supabase.co` (Project Settings → API). Used to find your database and to verify login tokens (via the project's JWKS). |
| `SUPABASE_DB_PASSWORD` | Your Supabase database password (Project Settings → Database; reset it there if forgotten). No connection string needed: the backend builds it from the URL. Special characters are fine. |
| `SUPABASE_REGION` | Optional, e.g. `ap-south-1`. Only if the direct host does not resolve on your network (IPv4-only); enables the Supabase pooler as a fallback. |
| `DATABASE_URL` | Optional full override of the three values above. |
| `SUPABASE_JWT_SECRET` | Only for legacy HS256 projects. |
| `LLM_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL` | Chat agent. Default `gemini` / `gemini-flash-latest`. `openai` and `anthropic` also work (install `langchain-openai` / `langchain-anthropic`). |
| `DEMO_MODE` | `true` enables the Demo Bank Simulator endpoints. |
| `SETU_*` | Leave blank unless you have Setu sandbox credentials. |

### 3. Frontend
```bash
cp .env.local.example .env.local     # set NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL
npm install
npm run dev                          # http://localhost:3000
```
Only public values (URL + anon key) reach the browser. The anon key can only *read the signed-in user's own rows* (RLS); every write goes through FastAPI.

## Demo Bank Simulator

Dashboard → **Demo Bank Simulator** (visible when `DEMO_MODE=true`). Each button posts a simulated bank event to `POST /demo/transactions`, which runs the same pipeline as a real feed: insert → recompute balance → assign cycle → update account → alerts/insights → Realtime push.

```json
POST /demo/transactions
{ "type": "EXPENSE", "amount": 160, "merchant": "Swiggy", "timestamp": "2026-09-30T11:35:00+05:30" }
```
`timestamp` is optional. Deterministic demo clock: salary defaults to **30 Sep 2026 11:27:04 IST**; other events land 8 minutes after the latest entry (so the first expense is 11:35 AM).

**Judge script** (seeded demo user starts at ₹35,000 in cycle 31 Aug → 30 Sep, ₹42,500 spent):

1. *Credit Salary ₹1,00,000* → balance ₹1,35,000 · income ₹1,00,000 · expenses ₹0 · "New financial cycle started"
2. *Add Expense ₹160* → balance ₹1,34,840 · expenses ₹160 (Swiggy, 11:35 AM)
3. *Receive ₹1,000 (Rahul)* → balance ₹1,35,840 · income still ₹1,00,000 · "Other inflows ₹1,000"
4. Set the savings target ₹25,000 (the dashboard asks; FinPilot never picks it)
5. *Add Large Expense ₹6,000* → "⚠️ High spending detected" · progress card "You can spend ₹36,340 more before reaching last cycle's total"
6. *Savings-risk demo: ₹70,000 expense* → "⚠️ Savings goal at risk". This is real arithmetic (₹76,000 spent vs a ₹75,000 limit), not a canned alert. A ₹6,000 spend alone is honestly *on track* against a ₹75,000 limit.
7. **Comparisons** page shows the untouched ₹42,500 previous cycle. *Reset simulator events* removes only rows flagged `metadata.simulated` and rebuilds; seeded/imported data is never touched.


## Goals, budgets, summaries (the "decision-support" layer)

Three different things, deliberately kept apart:

| | What it is | Where |
|---|---|---|
| **Savings target** | How much of *this cycle's* income you want to keep (`monthly_savings_targets`). Drives the spending limit `income - target`. | `/savings` |
| **Budgets** | Per-category caps for the cycle. Status `ON_TRACK / AT_RISK / OVER_BUDGET`, plus committed and projected spend. | `/budgets` |
| **Goals** | Long-term goals: `PURCHASE, EMERGENCY_FUND, TRAVEL, EDUCATION, CUSTOM`, with contributions. | `/goals` |

* **Goal maths** (`backend/app/services/goals.py`, pure and unit-tested): required monthly contribution = remaining / months left. The monthly savings pace is the *lower* of your recent average (last <= 3 closed cycles) and this cycle's projected savings, so a spending spike now immediately affects your goals. Goals share that pace by priority, then date. Status: `ON_TRACK / AT_RISK (covers >= 70%) / BEHIND / COMPLETED`. A contribution raises the goal's saved amount only; it is never an expense.
* **"How much of my budget is committed?"** `committed = already spent + recurring payments still expected before the cycle ends`, against the monthly limit (`income - savings target`, else the sum of category budgets). Already-spent and expected are always shown separately with the calculation.
* **Monthly summaries** are stored per cycle (`monthly_summaries`) and generated automatically when a cycle closes (and on demand). Each has key observations and action items (`monthly_summary_actions`) built from real numbers, e.g. *"Review the ₹1,900 increase in shopping expenses compared with the previous cycle"*. Completed or dismissed items are never deleted or overwritten when a summary is regenerated. Pages: `/summaries`, `/summaries/<id>`.
* **Insights** (`/insights`) shows trends, unusual activity, recurring payments, goal risks and budget risks, each with the data behind it. Categories with no transactions never appear.

Demo clock: after the demo salary (30 Sep 2026 11:27:04 IST) the simulator posts events at 11:35, 11:40, 12:05, then every 30 minutes, so the scripted demo reads Swiggy 11:35 AM, Rahul 11:40 AM, Amazon 12:05 PM (balance ₹1,33,340, expenses ₹2,660).

Regenerating seed data: `python -m scripts.generate_seed` then `python -m scripts.generate_summaries_seed` (the second runs the real summary service against a scratch Postgres and writes `demo_summaries.sql`).

## AI agent

`POST /chat` → LangGraph loop (`agent → tools → agent`) over 25 read-only tools: `get_current_balance, get_current_cycle, get_current_cycle_summary, get_transaction_history, get_transactions_between_dates, get_category_breakdown, compare_cycles, compare_categories, get_previous_cycle_total, get_remaining_before_previous_cycle, get_recurring_payments, get_upcoming_obligations, get_budget_status, get_budget_commitments, get_financial_goals, get_goal_progress, get_goal_projection, get_savings_target, get_savings_progress, get_recent_large_transactions, get_unusual_transactions, get_monthly_summary, get_monthly_trends, get_daily_spending, get_monthly_action_items`.

* Tools take **no user id**; they are bound to the JWT user when built. Cycle ids the model passes are ownership-checked.
* Tool output carries exact values plus `*_inr` display strings, and the system prompt forbids stating any number that did not come from a tool, giving investment advice, or moralising.
* If a tool has nothing, it says so ("no previous cycle", "target not set") and the agent must say that instead of guessing.
* If the LLM is unavailable the user gets a friendly message and the question is still saved; the dashboard, alerts and comparisons do not depend on the LLM.

## Realtime

Migration 015 publishes `transactions, financial_accounts, financial_cycles, agent_alerts, financial_insights` with `REPLICA IDENTITY FULL`. The browser (`LedgerProvider`) subscribes with the user's JWT, so RLS applies to Realtime too. An event only means "something changed": pages refetch the numbers from the backend, so the frontend never calculates money. If Realtime is not connected, the header shows **Polling** and the UI refreshes every 15 s; the simulator/manual actions also refresh instantly.

## Data sources and the AA sandbox

* **Connect Demo Bank** shows a consent screen (data requested, purpose, date range, frequency, approve/reject), clearly labelled *Demo / Sandbox*, then imports the sandbox history through the normal pipeline. FinPilot never asks for bank passwords, PINs or OTPs.
* **Add transaction / Import CSV** use the same `ingest()`. CSV columns: `date|timestamp, description, amount` plus optional `merchant, type, category, source, currency`. Types may be exact (`SALARY`…) or loose (`income/expense/transfer`). Ambiguous transfer direction is **rejected, not guessed**. Re-importing the same file never duplicates rows.
* **AA sandbox (Setu)**: `backend/app/providers/aa_sandbox.py` implements the same `FinancialDataProvider` interface, reads `SETU_*` from the environment, and is inert until configured (it never silently falls back to mock data). Its request/response mapping is a best-effort skeleton that must be verified against Setu's current sandbox API; production AA access needs separate onboarding/certification.
* Statement (PDF) upload is not implemented.

## Testing

```bash
cd backend
# Integration tests need a PostgreSQL server you can create databases on:
export TEST_ADMIN_DSN=postgresql://postgres:postgres@localhost:54322/postgres   # e.g. `supabase start`
.venv/Scripts/python -m pytest -q          # 142 tests; DB tests are skipped if no server is reachable
cd .. && npm run typecheck && npm run build
```
The suite builds a template database (Supabase stub + all migrations + seed) once and clones it per test. It covers: opening balance is not income; salary raises balance and opens a cycle at its exact timestamp; before/after-salary expense assignment; transfer-in is not salary; historical cycles unchanged; back-dated rows; previous-cycle comparison; savings target and at-risk logic; RLS with real `authenticated`/`anon` roles; cross-user isolation over HTTP and through agent tools; CSV parsing; consent flow; and the full spec scenario.

## Security

* Supabase Auth JWT verified on every request (HS256 secret or JWKS); `alg=none`/unknown algorithms rejected. The user id comes only from the verified token.
* Postgres RLS on all 14 tables (`user_id = auth.uid()`); browsers get `SELECT` only, and `INSERT/UPDATE/DELETE` is revoked from `anon`/`authenticated`. The backend uses a privileged connection, so its queries are scoped by user id in code (tested).
* Secrets only in env files (git-ignored). Logs never include financial payloads or credentials. In-memory per-user rate limiting on chat, CSV and simulator (per-process; use a gateway/Redis if you scale out).

## Known limits

* Supabase Auth, Realtime and the hosted Postgres were **not exercised against a live Supabase project** during development (no Docker). Everything else was tested against a real PostgreSQL 18 with a Supabase-compatible stub, plus a browser run of the full demo flow using a stand-in auth endpoint. Expect to spend a few minutes on first-run Supabase configuration (JWT settings, Realtime).
* The AA sandbox adapter is untested against Setu. Statement import is not built.
* `shadcn/ui` components are hand-authored in shadcn's style (`src/components/ui`), not generated by its CLI.
