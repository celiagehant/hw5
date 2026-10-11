# Campus Customs Multi-Agent Operations System — Harness

This document describes the system as it is implemented in the `Homework 5`
folder after Problem 9. It brings together the material written in Problems 2–8
and corrects anything that changed since.

**Contents**
1. [System overview](#1-system-overview)
2. [Database](#2-database)
3. [MCP server](#3-mcp-server)
4. [The five agents](#4-the-five-agents)
5. [Backend API](#5-backend-api)
6. [Dashboard](#6-dashboard)
7. [Safety and financial controls](#7-safety-and-financial-controls)
8. [Problem 9 test results](#8-problem-9-test-results)
9. [Running the system](#9-running-the-system)
10. [Appendix A — MCP Server — Initial Tools (Problem 3)](#appendix-a--mcp-server--initial-tools-problem-3)

---

## 1. System overview

```
 React dashboard (frontend/, Vite :5173)
        │  HTTP  (CORS: http://localhost:5173 and http://127.0.0.1:5173 only)
        ▼
 FastAPI backend (backend/main.py, uvicorn :8000)
   ├─ OperationsService: runs, approvals, reset, events      (backend/service.py)
   ├─ Orchestrator + TicketWorkflow: Boss-led agent team     (backend/orchestrator.py, workflow.py)
   │     5 PydanticAI agents · GPT-6 Luna via Portkey        (backend/boss.py … customer_service.py)
   ├─ Audit log → output/audit_trail.json (append-only)      (backend/audit.py)
   └─ MCP client (stdio) ───────────────┐                    (backend/mcp_client.py)
                                        ▼
 MCP server "campus-customs-ops" (mcp_server/server.py + operations.py)
        │  SQLite (read-only for agent tools; locked transactions for backend-only writes)
        ▼
 data/campus_customs_new.db  (working copy)   ← reset from →   data/campus_customs.db (original, read-only)
```

All shop facts reach the agents and the dashboard through the MCP server. The
backend opens the database directly in one place only: the reset, which copies
the original over the working file.

## 2. Database

### Locations and reset
- **Original:** `data/campus_customs.db`. It was extracted from `data.zip` in
  Problem 1 and is read-only on disk (`-r--r--r--`). Its SHA-256 is
  `23686a90…f360a`. Nothing writes to it:
  - the MCP server refuses to open it, even if `CAMPUS_CUSTOMS_DB` points at it
  - the reset opens it with `mode=ro` and checks its checksum before and after
- **Working copy:** `data/campus_customs_new.db`. All agents, MCP tools and
  backend routes use it.
- **Reset** (`POST /api/reset` with `{"confirm": "RESET"}`, or the dashboard's
  *Reset working database…* control):
  - It is refused while any agent run or approval is in progress.
  - SQLite's backup API copies every page of the original over the working
    copy. That restores every row and removes the system tables listed below.
  - It then checks integrity, row counts, the checking balance, ticket statuses
    and open invoices against the original.
  - It appends a `database_reset` event to the audit trail.
  - It never runs on server start-up.

### Baseline tables (the original nine)

| Table | Key | Fields | Why it matters to the agents |
|---|---|---|---|
| `desk` | none (one row) | `date_today`, `notes` | The shop's business date (2026-08-31). Every "overdue" and "due in N days" figure is counted from it, never from the computer's clock. |
| `inventory` | PK (`sku`, `size`) | `sku`, `name`, `size` (S, M, L, XL, OS), `qty`, `location` | The only source of stock levels; Inventory confirms availability and shortfalls here. |
| `pricing` | PK `sku` | `sku`, `unit_cost`, `list_price` | Accounting's source for margins, purchase cost and the lowest price a discount may reach. |
| `vendors` | PK `id` | `id`, `name`, `specialty`, `lead_days` | Restock supplier, chosen by specialty, and arrival timing. |
| `invoices` | PK `id`; FK `vendor_id` → `vendors.id` | `id`, `vendor_id`, `amount`, `due_date`, `status` (`open` or `paid`), `description` | What the shop owes. An open invoice blocks that vendor from shipping. |
| `leases` | PK `id` | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | Facilities' source for rent and due dates. |
| `cash_accounts` | PK `name` | `name` (`checking`), `balance`, `date` | The cash available. The payment tool checks it, and debits it, inside the payment transaction. |
| `payments` | PK `id` | `id`, `kind` (`invoice` or `rent`), `ref_id` (invoice or lease id), `amount`, `account`, `paid_at`, `approved_by` | The record of every executed payment, including who approved it. |
| `tickets` | PK `id`; FK `lease_id` → `leases.id`, `invoice_id` → `invoices.id`; `sku`/`size` match `inventory` | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status` (`open` or `resolved`), `notes`, `created_at` (with −04:00 offset) | The work queue. Each ticket's links show which other tables the job needs. |

Relationships: `tickets → invoices → vendors`, `tickets → leases`,
`tickets (sku, size) → inventory`, and `inventory.sku → pricing`. There is **no
table linking products to vendors**, so agents match a SKU to a vendor by its
`specialty` and say that this is a judgment, not a database fact. There is also
no purchase-order or payables table.

### System tables added by the MCP write tools

A reset removes these; they are recreated on the next write.

| Table | Key | Fields | Purpose |
|---|---|---|---|
| `ticket_runs` | PK `run_id`; FK `ticket_id` | `run_id`, `ticket_id`, `run_status`, `recorded_at` | The final workflow status of every agent run. |
| `action_proposals` | PK `id`; FK `run_id`, `ticket_id`, `payment_id` | `kind` (`pay_invoice`, `pay_rent`, `purchase_order`, `offer_discount`), `ref_table`, `ref_id`, `amount`, `payee`, `sku`, `size`, `quantity`, `discount_pct`, `description`, `blocked_reason`, `status` (`pending`, `executed`, `approved`, `declined`, `superseded`), `decided_at`, `decided_by`, `balance_after`, `result` | Proposals awaiting a human decision, each with a stable id. Purchase orders exist only here. |
| `approvals` | PK `id`; FK `proposal_id` | `approved_by`, `approved_amount`, `approved_payee`, `outcome` (`executed`, `approved`, `declined`, `refused`), `detail`, `created_at` | Every human approval or decline attempt, including refused ones. |
| trigger `cash_balance_never_negative` | — | `BEFORE UPDATE OF balance ON cash_accounts WHEN NEW.balance < 0 → ABORT` | The database itself refuses a negative balance. |

### Records involved in the three tickets (baseline)

| Ticket | Request | Linked records |
|---|---|---|
| 101 | `customer_order`: Tauhid Zaman wants 1 CC-TEE-WHITE, size S | Inventory S = 0 (M 5, L 3, XL 2). Invoice 501: $840 to Bulldog Print Co (vendor 1, apparel reprint, 5 days), due 2026-08-28, `open`. |
| 102 | `rent_notice`: Elm City Properties, rent due in 2 days | Lease 1: Chapel Street shop, $2,400, `next_due` 2026-09-02, no notes. |
| 103 | `price_override`: Yale AI Club wants 20 CC-HOOD-NAVY, size M, at a bulk discount | Inventory M = 8 (S 4, L 14, XL 6). Pricing: $22 cost, $58 list. |

Other baseline values: `checking` = $3,400.00, `payments` empty, vendors 2
(Elm City Gifts, mugs, 3 days) and 3 (QuickShip CT, courier, 1 day).

## 3. MCP server

### Starting and connecting
- `mcp_server/server.py` is a FastMCP 4 server named `campus-customs-ops`.
- **The backend** starts it as a stdio subprocess when uvicorn starts
  (`backend/mcp_client.py`), passing only `CAMPUS_CUSTOMS_DB=data/campus_customs_new.db`
  and no API keys. Because the server takes about 7 seconds to import FastMCP,
  the connection timeout is 60 seconds. One session is shared by every request
  and run.
- **Claude Code** connects through `Homework 5/.mcp.json`, which uses the same
  command and environment. The Problem 4 smoke tests in
  `output/mcp_smoke.json` used this route.
- **By hand:**
  - `.venv/bin/python mcp_server/server.py` for stdio
  - `--http` for http://127.0.0.1:8001/mcp
- **How tool results are structured:**
  - `database`: values copied from the tables
  - `computed`: arithmetic such as a shortfall or days until due
  - `notes`: gaps the agent must not fill in
- **Unknown or invalid input:** unknown ids return `found: false` with the
  valid values; invalid input returns an error.

### Tool reference (all 11 registered tools)

| Tool | Parameters | Purpose | Tables and fields | Used by | Access |
|---|---|---|---|---|---|
| `get_stock_and_pricing` | `sku`, `size?`, `qty_needed?` | Stock by size, shortfall, unit cost, list price, margin; a missing size is reported as unknown, not 0 | `inventory` (sku, name, size, qty, location); `pricing` (sku, unit_cost, list_price) | Inventory, Accounting | Read-only |
| `check_vendor_eligibility` | `vendor_id?` | Specialty, `lead_days`, invoices with days past due, `eligible_to_ship` (blocked by any open invoice), arrival date if eligible | `vendors`; `invoices`; `payments`; `desk` | Inventory, Accounting | Read-only |
| `get_rent_due_and_cash_position` | `lease_id`, `account="checking"` | A lease's rent, due date and recorded rent payments, next to cash and open invoices | `leases`; `cash_accounts`; `payments`; `invoices`; `vendors.name`; `desk` | Facilities | Read-only |
| `list_open_tickets` | — | Open tickets, oldest first | `tickets`; `desk` | Orchestrator (`--all`) | Read-only |
| `get_ticket_details` | `ticket_id` | One ticket in full, plus whether its linked inventory row, lease and invoice exist | `tickets`; `inventory`; `leases`; `invoices`; `vendors.name`; `desk` | Orchestrator, Boss, Customer Service | Read-only |
| `get_cash_and_obligations` | `account="checking"` | Cash next to every open invoice and each lease's next rent, with totals | `cash_accounts`; `invoices`; `vendors`; `leases`; `payments`; `desk` | Accounting; backend (`GET /api/cash/checking`) | Read-only |
| `list_tickets` | `status="all"` | Every ticket with its persisted status and latest run | `tickets`; `ticket_runs`; `desk` | Backend (`GET /api/tickets`) | Read-only |
| `list_action_proposals` | `ticket_id?`, `status?` | Proposals with stable ids (max 100) | `action_proposals` | Backend (`GET /api/proposals`) | Read-only |
| `record_run_outcome` | `run_id`, `ticket_id`, `run_status`, `proposals[]` | Stores a run's status and the Boss's payment, purchase-order and discount proposals after checking them against the database. Amounts must match exactly; order cost and discount value come from `pricing`; below-cost discounts are skipped. Identical pending proposals keep their id; the rest are superseded. | Reads `tickets`, `invoices`, `vendors`, `leases`, `pricing`, `inventory`. Writes `ticket_runs`, `action_proposals`, `tickets.status` | Orchestrator, after every run | **State-changing**, backend only |
| `approve_proposal` | `proposal_id`, `approved_by`, `confirm_amount`, `confirm_payee` | Processes one explicit human approval (details in §7) | Writes `cash_accounts`, `payments`, `invoices.status`, `leases.next_due`, `action_proposals`, `approvals`, `tickets.status` | Backend (`POST …/approve`) | **State-changing**, moves money |
| `decline_proposal` | `proposal_id`, `declined_by`, `reason?` | Records a human decision not to approve; nothing is paid, ordered or sent | Writes `action_proposals`, `approvals`, `tickets.status` | Backend (`POST …/decline`) | **State-changing**, no money |

**Why the first tools exist** (from Problem 3 and Problem 5):
- `get_stock_and_pricing` answers "can we fill it, how short are we, what does
  it cost" for tickets 101 and 103.
- `check_vendor_eligibility` applies the open-invoice rule to the current state,
  so eligibility is rechecked whenever it matters. Invoice 501 blocks
  ticket 101's vendor.
- `get_rent_due_and_cash_position` puts the landlord's claim (ticket 102) next
  to the lease record and the cash available.
- `get_ticket_details` and `list_open_tickets` let the system read tickets
  without hardcoding them.
- `get_cash_and_obligations` makes affordability account for every competing
  bill rather than one at a time.

## 4. The five agents

### Shared design
- **Framework and model:** every agent is a PydanticAI agent built by
  `backend/agent_base.py`. All five use one model configuration
  (`backend/config.py`): `gpt-6-luna` through Portkey's OpenAI-compatible
  endpoint, using the `PORTKEY_API_KEY` from `.env`. Every request sends the
  header `x-portkey-trace-id = <run>-t<ticket>-<n>-<agent>`, and Portkey
  reports the model as `gpt-6-luna-global`.
- **Input:** a `TaskRequest` containing the ticket, the shop date, the task,
  who asked and why, and the caller's findings.
- **Output:** a typed model from `backend/models.py`. The Boss returns
  `BossDecision`; Inventory, Accounting and Facilities return `SpecialistReport`;
  Customer Service returns `CustomerServiceReport`.
- **Checked before anything is passed on** (`backend/guards.py`):
  - every cited record must have come back from an MCP tool in this run
  - payment amounts must equal the database
  - discounts must stay above cost
  - customer drafts may not quote a discount figure or mention internal
    finances

  A failed check is sent back to the model as a retry.
- **Tool access is enforced twice:** each agent receives only its listed tools,
  and the MCP hook rejects any other call.

### Delegation

Delegation is a real call. An agent's delegation tool asks
`TicketWorkflow.delegate()` to check the limits, run the target agent, and
return its structured report. That report includes `consulted`: the specialists
the target itself asked.

| Agent | May delegate to |
|---|---|
| Boss | Inventory, Accounting, Facilities, Customer Service |
| Inventory | Accounting |
| Facilities | Accounting |
| Customer Service | Inventory |
| Accounting | nobody, so the delegation graph has no loops |

### The agents

| Agent | Code / prompt | Responsibilities and limits | Inputs → outputs | MCP tools |
|---|---|---|---|---|
| **Boss** (Operations Manager) | `backend/boss.py` / `prompts/boss.md` | Triages problem, urgency, records and expected outcome; delegates only where needed; passes findings between specialists; settles conflicts using database evidence; decides; lists everything needing human sign-off; explains the decision. Its decision is not authorization, and the backend sets the final status. | Ticket from the operator → `BossDecision` (problem, urgency, assigned agents, decision, proposed status, actions, blockers, outstanding items, evidence, operator summary, next step) | `get_ticket_details`; tool `delegate_to_specialist` |
| **Inventory** (Inventory Manager) | `backend/inventory.py` / `prompts/inventory.md` | Stock by SKU and size; shortfall; restock quantity (the shortfall by default); vendor by specialty; eligibility rechecked every run; arrival date only for an eligible vendor. Never invents quantities or dates. | Task from Boss or Customer Service → `SpecialistReport` (may propose `draft_purchase_order`) | `get_stock_and_pricing`, `check_vendor_eligibility`; tool `ask_accounting` |
| **Accounting** (Accounting Manager) | `backend/accounting.py` / `prompts/accounting.md` | Cash, invoices, aging from the shop date, affordability, margins. Prepares `pay_invoice`, `pay_rent` and `offer_discount`. Weighs obligations by due date (overdue or due within days compete for cash; next month's rent is a reported risk). For an unspecified discount it recommends one moderate percentage and never the above-cost maximum. Cannot pay; cash only flows out. | Task from Boss, Inventory or Facilities → `SpecialistReport` | `get_cash_and_obligations`, `check_vendor_eligibility`, `get_stock_and_pricing` |
| **Facilities** (Facilities Manager) | `backend/facilities.py` / `prompts/facilities.md` | Checks the landlord's claim against the lease, days until due, recorded rent payments and missing terms (no grace or penalty terms, so those go to a human). Passes on Accounting's `pay_rent` unchanged. Never contacts the landlord. | Task from Boss → `SpecialistReport` | `get_rent_due_and_cash_position`; tool `ask_accounting` |
| **Customer Service** (Customer Service Manager) | `backend/customer_service.py` / `prompts/customer_service.md` | Friendly draft replies using only verified facts. No unapproved dates, prices or discounts, and no internal finances. No sending tool exists. | Task from Boss → `CustomerServiceReport` (with `CustomerMessageDraft`, `is_draft = true`) | `get_ticket_details`; tool `ask_inventory` |

### How the Boss chooses specialists

The Boss prompt maps each need to one specialist:
- stock, restock and vendors → Inventory
- money, invoices, payments, discounts → Accounting
- lease and space → Facilities
- a reply to an outside requester → Customer Service, called last, with
  verified facts

It reads `consulted` so it does not ask the same specialist twice. In
Problem 9 it called Inventory, Accounting and Customer Service for 101;
Facilities and Accounting for 102; and Inventory, Accounting and Customer
Service for 103. Facilities was never called for a product ticket.

### Errors, incomplete information and blocked tickets
- **Missing records or input:** a specialist returns `needs_information` or
  `escalate` instead of guessing.
- **Refused or failed delegations:** limits, cycles and repeats are refused and
  returned to the caller as data. The Boss records the gap as a blocker.
- **Agent failures:** timeouts and API errors re-run the agent once. Other
  errors are logged as `agent_failed` or `run_failed`, and the run is reported
  as failed, never as success.
- **Blocked actions:** a purchase order to an ineligible vendor, a payment
  larger than cash, or a payment to an invoice that is not open is stored with
  status *blocked*. The backend re-checks it when a human approves.
- **Final status rules** (`TicketWorkflow.final_status`), applied by the
  backend:
  - a hard limit gives `limit_reached`, and no decision gives `failed`
  - the Boss's `escalated`, `blocked` and `needs_clarification` are kept
  - pending approvals give `awaiting_human_approval`
  - "resolved" with an outstanding specialist blocker becomes `escalated`
- **When a ticket resolves:** a ticket becomes `resolved` in the database only
  when either:
  - the run itself resolved it with nothing to approve, or
  - its latest run ended `awaiting_human_approval` or `blocked`, every proposal
    from that run has been decided, and at least one was carried out.

  Escalated tickets stay open for a human.

### Shared models (`backend/models.py`)

| Need | Models |
|---|---|
| Tickets and identifiers | `TicketContext`, `RecordRef` |
| Tasks and delegation | `TaskRequest`, `DelegationResult` |
| Findings and evidence | `Finding`, `Evidence` |
| Actions | `ProposedAction`, with the `ActionType` and `ActionStatus` enums |
| Human approval | `ApprovalRequirement` |
| Customer drafts | `CustomerMessageDraft` |
| Results and status | `SpecialistReport`, `CustomerServiceReport`, `BossDecision`, `AgentRunSummary`, `TicketRunResult`, `WorkflowStatus` |

`ProposedAction` refuses a payment without a target, amount and payee, and a
discount without `discount_pct`. It also forces `requires_human_approval` on
payments, purchase orders, discounts and messages.

## 5. Backend API

### Starting it
```bash
cd "Homework 5/backend"
source ../.venv/bin/activate
uvicorn main:app --reload --port 8000
```
Alternatively, from `Homework 5`: `.venv/bin/uvicorn backend.main:app --port 8000`.

It is ready when the log shows `Application startup complete`, after about
5–10 seconds while the MCP server starts. Use one worker only. Start-up never
resets or changes the database.

### Environment variables

| Variable | Purpose |
|---|---|
| `PORTKEY_API_KEY` | Required to run agents. Loaded from `Homework 5/.env` or the course `.env`. It is never logged, returned, or passed to the MCP server. |
| `CC_<LIMIT>` | Overrides any limit in §7, e.g. `CC_MAX_AGENT_CALLS_PER_TICKET=6`. |
| `CAMPUS_CUSTOMS_DB` | Set automatically to `data/campus_customs_new.db` for the MCP server. |
| `PYDANTIC_AI_NO_BANNER` | Set automatically. |

### Routes

All routes are under `http://localhost:8000`. Errors return
`{"ok": false, "error": <code>, "message": …}`, and interactive docs are at
`/docs`.

| Method and URL | What it does | Required input | Main result |
|---|---|---|---|
| `GET /api/health` | Liveness | — | `ok`, model, database, active runs |
| `GET /api/tickets` | All tickets with their persisted status (via `list_tickets`) | — | `shop_date`, `count`, `tickets[]` (id, subject, type, requester, `status`, `latest_run`, `active_run`) |
| `GET /api/tickets/{id}` | One ticket and its linked records (via `get_ticket_details`) | path id > 0 | Ticket row and links; 404 if unknown |
| `POST /api/tickets/{id}/run` | Starts the Boss-led team in the background | path id | 202 `{status: "started", run_id, run_url, events_url}`; 404 unknown; 409 if resolved, already running or resetting |
| `GET /api/runs` / `GET /api/runs/{run_id}` | Run state for this server session | run id | `state` (running, completed, failed), `workflow_status`, `stop_reason`, `error`, and the full `result` (decision, approvals, drafts, specialist reports, agent runs, recorded proposals, usage) |
| `GET /api/events` | Recent activity from `output/audit_trail.json` | Optional `ticket_id`, `run_id`, `after` (event id), `limit` 1–500 (default 100) | `events[]` (timestamp, run, ticket, agent, category, description, tool name, arguments and result, status or stop reason, error), `total_matching`, `next_after` |
| `GET /api/proposals` | Proposals (via `list_action_proposals`) | Optional `ticket_id`, `status` | `proposals[]` with id, kind, target, amount, payee, SKU, size, quantity, `discount_pct`, status, decision details |
| `POST /api/proposals/{id}/approve` | Human approval (via `approve_proposal`) | Body `approved_by`, `confirm_amount`, `confirm_payee` | `outcome` (executed or approved), `payment_id`, `balance_before`, `balance_after`, `message`, `resolved_ticket_ids`. 400, 404 or 409 with a code if refused |
| `POST /api/proposals/{id}/decline` | Human decline (via `decline_proposal`) | Body `declined_by`, `reason?` | `outcome: "declined"`, `message`, `resolved_ticket_ids`; 400, 404 or 409 if refused |
| `GET /api/cash/checking` | Current checking balance (via `get_cash_and_obligations`) | — | `account`, `balance`, `currency`, `balance_date`, `shop_date`; 404 if no account |
| `POST /api/reset` | Restores the working database | Body `{"confirm": "RESET"}` | `ok`, source, original checksum, integrity, row counts, balance, ticket statuses; 409 while work is in progress |

### How runs and events are exposed
- **Runs:** `POST /run` registers the run id and starts
  `orchestrator.run_ticket` as an asyncio task. The workflow is the same one
  used by the command line (`python -m backend.orchestrator --ticket N`).
- **Events:** every step is appended to the audit trail as it happens, so
  polling `GET /api/events?ticket_id=…&after=<last id>` shows progress live.
- **When a run finishes:** the orchestrator records its status and proposals
  through `record_run_outcome`. A recording failure is logged and returned, not
  hidden.
- **Restarts:** the active-run guard and finished run results live in memory,
  so a restart, or a `--reload` after a code edit, loses them and abandons a
  running workflow. Events, ticket statuses, proposals, approvals and payments
  are persisted.

## 6. Dashboard

### Starting it
```bash
cd "Homework 5/frontend"
npm run dev
```
Then open http://localhost:5173. The backend must already be running.

The base URL is set once, in `src/api/client.ts` (`VITE_API_BASE`, default
`http://localhost:8000`). The dashboard uses React 19, Vite 8 and TypeScript 7,
with no other runtime dependencies. The full design write-up is in
`output/design.md`.

### Major features
- **Masthead:**
  - "Campus Customs — Operations Desk" branding
  - a connection pill, shown as connected only after a real request succeeds
  - the operations status: *Agents idle*, *Workflow running*, *Attention
    required* or *Backend offline*
  - the business date
  - the **ledger**: the checking balance, flagged with "▼ was $X" when it
    changes
- **Ticket rail:** the three tickets as paper stubs, each marked *Open · not yet
  run*, *Agents working*, *Awaiting approval*, *Escalated*, *Blocked*, *Run
  failed* or *Resolved*. *Resolved* appears only when `tickets.status` is
  `resolved`.
- **Workspace:**
  - a brief with the database facts
  - a *Run the agent team* button, disabled with a reason when it can't run
  - a run status strip that separates how the run ended from the persisted
    ticket status
  - the approval panel
  - the Boss's recommendation, next step, blockers and items needing sign-off
  - agent contribution cards: outcome, findings, who asked whom, tools used
  - the customer draft, shown as a letter marked "Draft only"
- **Activity feed:** a chronological timeline from `/api/events`.
  - Each agent has a fixed monogram and color.
  - The event label comes from `event_type`: *Investigating*, *Tool call*,
    *Delegation*, *Handoff returned*, *Finding*, *Decision*, *Guardrail*,
    *Payment executed*, *Purchase approved*, *Discount approved*, *Declined by
    you* and others.
  - The MCP call is shown as code, and details expand on request.
- **Approval panel:** shown only for real proposals of the selected ticket.
  - Each card shows the kind (payment, purchase order or discount), amount or
    percentage, payee, target and description, and explains whether cash moves.
  - *Review and approve…* opens a confirmation box. It requires the operator's
    name and submits the exact amount and payee.
  - *Decline…* records a decline with an optional reason.
  - Results come only from the backend, refusals show the real error, and
    decided proposals move to History.
- **Reset:** a separated *Simulation* control with a confirmation dialog. It is
  disabled while a run is active.

### Refresh behaviour
- **During a run:** events (incremental, using `after`) and run status are
  polled every 2.5 seconds, slowing to 8 seconds while the backend is
  unreachable.
- **When a run finishes:** tickets, proposals, balance and events are reloaded
  once.
- **When idle:** only a health check runs, every 20 seconds. On reconnection
  the dashboard reloads everything by itself.
- **Balance:** re-read on load, after every approval or decline, after a
  finished run and after a reset. It is never calculated in the browser.

## 7. Safety and financial controls

### Human approval and execution
- **Agents cannot pay.** No agent has a write tool. The backend-only tools
  `approve_proposal`, `decline_proposal` and `record_run_outcome` are excluded
  from every agent's tool list and rejected by the MCP hook. An offline test
  checks this.
- **Every payment, purchase order and discount needs a named human.** Neither
  a recommendation nor the Boss's decision counts as approval. The approver may
  not be an agent name. The request must repeat the proposal's exact amount and
  payee, and proposals never change after they are stored; a revised proposal
  gets a new id.
- **`approve_proposal` checks everything inside one `BEGIN IMMEDIATE`
  transaction:**
  - the proposal is still `pending`
  - for an invoice: it is still `open` and the amount is unchanged
  - for rent: the lease rent is unchanged
  - for a purchase order: the vendor has no unpaid invoice
  - for a discount: the price stays above `unit_cost`

  **For a payment** it then:
  1. debits checking with `WHERE balance >= amount`
  2. inserts a `payments` row with the approver's name
  3. marks the invoice paid, or moves the lease's `next_due` on a month
  4. marks the proposal executed, with `balance_after`
  5. writes an `approvals` record

  **A purchase order or discount** is marked `approved`. It moves no cash and
  sends nothing.
- **The insufficient-cash guard:** the transaction checks the balance and uses a
  conditional debit, and the database trigger refuses any negative balance. A
  refused or failed payment changes nothing except the record of the attempt.
  The check is offline-tested: three simultaneous approvals produced exactly
  one payment, and a $500 payment against $160 was refused with the balance
  unchanged.
- **No duplicate execution:** a second approval returns 409 `not_pending`. Other
  pending proposals to pay the same target are superseded. A repeated identical
  proposal from a later run keeps its id instead of creating a duplicate.

### Audit trail (`output/audit_trail.json`)
- **Format:** one JSON array, written by `backend/audit.py`. Every event has the
  same 25 fields:
  - identity: id, timestamp, run, ticket, agent, depth, event type
  - task and reason; delegation target and result
  - tool name, short arguments, outcome and record ids
  - findings and recommendation
  - state change; stop reason, retry and error
  - model and Portkey trace id
  - usage
- **Event types:** `run_started`, `ticket_loaded`, `state_transition`,
  `agent_started` / `agent_completed` / `agent_retry` / `agent_failed`,
  `mcp_tool_call` / `mcp_tool_error`, `delegation_requested` /
  `delegation_completed` / `delegation_refused`, `guardrail_applied`,
  `limit_reached`, `run_completed` / `run_failed`, `proposals_recorded`,
  `payment_executed`, `purchase_approved`, `discount_approved`,
  `proposal_declined`, `approval_refused` and `database_reset`.
- **Append-only:**
  - each event takes an exclusive file lock and replaces the file atomically
    (temporary file, then `os.replace`)
  - a corrupt file is never overwritten
  - a reset never touches it
- **No secrets:** secret values are scrubbed, credential fields are redacted,
  and long text is shortened. A check after Problem 9 found no API key in the
  file.

### Limits (`backend/config.py`; override with `CC_<NAME>`)

| Control | Default | Enforcement |
|---|---|---|
| Agent calls per ticket | 8 | Further delegations are refused and the ticket ends `limit_reached` |
| Calls to one agent per ticket | 3 | Delegation refused |
| Delegation depth | 3 (Boss is 0) | Delegation refused |
| Circular delegation / repeats | not allowed | The graph has no loops plus a runtime chain check; a repeated task returns the cached result |
| Model requests per agent run | 8 | `UsageLimits(request_limit)` |
| Tool calls per agent run | 6 | `UsageLimits(tool_calls_limit)` |
| Tokens per ticket | 250,000 | `UsageLimits(total_tokens_limit)` set to the remaining budget |
| Retries | 2 inside a run; 1 re-run; 2 per HTTP request | Agent `retries`; the workflow; the OpenAI client |
| Timeouts | 90 s per model request; 240 s per agent run; 600 s per ticket | `AsyncOpenAI`/`ModelSettings`; `asyncio.wait_for`; checks before every call |
| Output size | 6,000 tokens per response; capped findings, actions and blockers | `ModelSettings(max_tokens)`; model field limits |
| Input and result size | ticket notes 1,000 characters; caller context 2,500; tool results 6,000; audit text 400 | Cut by the workflow, the MCP hook and the audit log |

### Nothing leaves the building

There are no tools to email or contact customers, contact vendors, submit
orders or move real money.
- Customer messages exist only as drafts with `is_draft = true`.
- Approved purchase orders are drafts that are never sent.
- An approved discount does not change the price list or notify anyone.
- The only financial effect anywhere is an approved payment recorded in the
  local working database.

## 8. Problem 9 test results

**Full evidence:**
- `output/problem9_run_notes.md`
- `output/desk_tickets.html` (Actual sections and the Cash tab)
- `output/resolved_tickets.json`
- `output/resolved_board.html` with `output/screenshots/`
- `output/problem9_runs/`
- `output/audit_trail.json`: 83 events from the reset at 17:42:03Z onward

### Fixes made before the run

Earlier runs showed that the tickets could not resolve legitimately. Ticket 103
ended blocked or escalated in all four of its earlier runs: f707c0ef250c,
5ca79e0165aa, e27759d68876 and db410c786e42.
1. **Discount decisions now have an approval route.** Before, an
   `offer_discount` action was never stored, so no human could act on it.
   Discounts are now stored as proposals and approved only if the price stays
   above unit cost. Accounting recommends one specific, moderate percentage.
2. **Human decline added.** Before, a proposal the operator would not approve
   stayed pending forever. Now there is the `decline_proposal` tool,
   `POST /api/proposals/{id}/decline`, and a Decline button.
3. **Accounting weighs obligations by due date.** Next month's rent no longer
   blocks a payment that is affordable now.

Offline tests after the fixes: 25 payment checks and 30 safeguard checks, all
passing.

### Run

| Step | Result |
|---|---|
| Reset | Done through the dashboard: `reset-35872609` at 2026-10-11T17:42:03Z. Checked by SQL: all tickets `open`, `checking` = **$3,400.00**, no payments, invoice 501 `open`, original checksum unchanged. |
| Ticket 101 | Run `de29a5509213`: Boss → Inventory → Accounting, then Boss → Customer Service. Ended `blocked`. Human approved #1 (pay invoice 501, $840, **payment 1**) and #2 (1-tee purchase order, $8, after the vendor recheck). **Resolved.** |
| Ticket 102 | Run `1fcc045db23e`: Boss → Facilities → Accounting. Ended `awaiting_human_approval`. Human approved #3 (rent $2,400, **payment 2**; next due 2026-10-02). **Resolved.** |
| Ticket 103 | Run `e407889e6757`: Boss → Inventory and Accounting in parallel, then Boss → Customer Service. Ended `awaiting_human_approval`. Human approved #5 (10% discount for 20 units, $116 below list) and #4 (12-hoodie purchase order, $264). Neither moved cash. **Resolved.** |
| Final statuses | 101, 102 and 103 all `resolved` in `GET /api/tickets` and in `tickets.status`. |

### Cash reconciliation

| | Outflow | Checking after |
|---|---:|---:|
| Opening (after reset) | — | $3,400.00 |
| 101 · payment 1 · invoice 501 | $840.00 | $2,560.00 |
| 101 · purchase order #2 approved (no cash) | $0.00 | $2,560.00 |
| 102 · payment 2 · rent, lease 1 | $2,400.00 | $160.00 |
| 103 · discount #5 and purchase order #4 approved (no cash) | $0.00 | $160.00 |
| **Closing** | **$3,240.00** | **$160.00** |

$3,400.00 − $3,240.00 = $160.00. This matches `SUM(payments.amount)` = 3240,
`cash_accounts.balance` = 160, `GET /api/cash/checking` = 160 and the dashboard
ledger. There was no discrepancy.

### Remaining limitations
- **Approvals were entered by Claude Code.** At your direction, I entered the
  approvals in the dashboard after reviewing each proposal. They are recorded as
  "Celia Gehant (entered by Claude Code)". The backend has no authentication;
  `approved_by` is whatever name is submitted.
- **Purchase-order commitments are not tracked.** The approved orders ($8 +
  $264 = $272) are not stored as payables, because the database has no table
  for them. They exceed the $160 left. When billed, payment would face the
  insufficient-cash check.
- **No agent checked ticket 103's order against cash.** Accounting was asked
  only about the discount, so no agent compared the $264 order with the $160
  balance. I approved it as a judgment, documented in the run notes.
- **Run order changes the outcomes.** The order 101 → 102 → 103 shaped what
  happened, for example the vendor was already eligible for 103. Other orders
  produce other, still guarded, outcomes.
- **Fixed business date.** The date stays 2026-08-31 and no revenue is
  modelled, so October's $2,400 rent cannot be covered by the $160 left.
- **Identical prompts can be cached.** Portkey may serve cached responses for
  identical prompts, for example rerunning a ticket right after a reset.
- **Restarts lose in-memory state.** Run results in memory are lost on
  restart. The three Problem 9 results were saved to `output/problem9_runs/`.

## 9. Running the system

1. **Install, once:** `python3 -m venv .venv`, then
   `.venv/bin/python -m pip install --prefer-binary -r requirements.txt`, then
   `npm install` in `frontend/`.
2. **Backend:** start it in Terminal 1 (§5). This also starts the MCP server.
3. **Dashboard:** start it in Terminal 2 (§6) and open http://localhost:5173.
4. **Optional checks:**
   - `.venv/bin/python tests/test_offline.py` (30 safeguard checks)
   - `.venv/bin/python tests/test_payments.py` (25 payment checks)
   - `.venv/bin/python -m backend.orchestrator --ticket 101` (one ticket,
     without the dashboard)

---

## Appendix A — MCP Server — Initial Tools (Problem 3)

This is the Problem 3 write-up of the first three tools, kept as written. Their parameters and behaviour are unchanged. Section 3 above lists all 11 tools as they are registered now.


The MCP server (`mcp_server/server.py`, registered as `campus-customs-ops`)
gives the agents three read-only tools, one for each piece of information the
three open tickets need. Every tool opens `data/campus_customs_new.db` in
read-only mode and never touches the original `data/campus_customs.db`.

Each tool keeps its results in separate groups:
- `database`: values copied unchanged from the tables.
- `computed`: plain arithmetic on those values, such as a shortfall, a margin or days until a due date.
- `notes`: missing or ambiguous data the agent must not fill in.

None of the tools makes a recommendation. Deciding whether to restock, pay or
discount is the agents' job after they read the results.

### A.1: `get_stock_and_pricing`

1. **Tool name:** `get_stock_and_pricing`
2. **Purpose:** Returns the units on hand for one SKU in every size, the stock for the requested size, and the SKU's unit cost and list price. It then calculates the shortfall against the quantity the ticket asks for and the margin per unit.
3. **Inputs:**
   - `sku` (required): the product code from the ticket, e.g. `CC-TEE-WHITE`.
   - `size` (optional): the size from the ticket, e.g. `S` or `M`.
   - `qty_needed` (optional): the number of units the ticket asks for. It must be a positive number, and it needs a size unless the SKU comes in only one size.
4. **Database tables and fields:**
   - `inventory`: `sku`, `name`, `size`, `qty`, `location`
   - `pricing`: `sku`, `unit_cost`, `list_price`
5. **Relevant tickets:**
   - **Ticket 101:** Tauhid Zaman needs 1 `CC-TEE-WHITE` in size S.
   - **Ticket 103:** the Yale AI Club wants 20 `CC-HOOD-NAVY` in size M at a bulk discount.
6. **Why this tool is appropriate:**
   - **Ticket 101:** It shows that `inventory.qty` for CC-TEE-WHITE size S is 0, a shortfall of 1, so the Inventory agent knows it must restock before the order can be filled.
   - **Ticket 103:** It shows only 8 hoodies in size M against 20 requested, and a $22 cost against a $58 list price. Accounting can then work out how deep a discount stays above cost, and Inventory knows 12 must be restocked.
7. **Output:**
   - From the database: `stock_by_size` (size, qty, location), `requested_size_stock`, `pricing` (`unit_cost`, `list_price`).
   - Computed: `shortfall`, `can_fill_from_stock`, `unit_margin`, `margin_pct_of_list_price`, `max_discount_pct_before_selling_below_cost`, and `revenue_at_list_price_for_qty_needed` and `cost_for_qty_needed` for the requested quantity.
   - If the SKU does not exist, the tool returns `found: false` with the list of known SKUs.
   - If the size does not exist, it says that stock for that size is unknown rather than reporting 0.

### A.2: `check_vendor_eligibility`

1. **Tool name:** `check_vendor_eligibility`
2. **Purpose:** For one vendor or all vendors, returns the specialty, the lead time and every invoice. It also says whether the vendor may ship new product: a vendor is blocked while it has an `open` invoice. For eligible vendors it gives the earliest arrival date if ordered today. Days past due and arrival dates are counted from the shop's date in `desk.date_today`, not the computer's clock.
3. **Inputs:**
   - `vendor_id` (optional): the vendor's `vendors.id`. If left out, the tool checks every vendor. A missing id returns `found: false` with the known vendor ids.
4. **Database tables and fields:**
   - `vendors`: `id`, `name`, `specialty`, `lead_days`
   - `invoices`: `id`, `vendor_id`, `amount`, `due_date`, `status`, `description`
   - `payments`: `id`, `kind`, `ref_id`, `amount`, `paid_at`, `approved_by`
   - `desk`: `date_today`
5. **Relevant tickets:**
   - **Ticket 101:** the tee in size S is out of stock, and the ticket's `invoice_id` is 501, an $840 Bulldog Print Co invoice for a rush reprint of that same tee.
   - **Ticket 103:** it applies to the hoodie restock as well.
6. **Why this tool is appropriate:**
   - **Ticket 101:** It shows that invoice 501 is `open` and 3 days past due, so Bulldog Print Co (vendor 1) is not eligible to ship. The Inventory agent can report that restocking the tee is blocked until a human approves paying invoice 501, instead of promising a delivery date.
7. **Output:**
   - From the database: `vendor_id`, `name`, `specialty`, `lead_days`, and each invoice's `invoice_id`, `amount`, `due_date`, `status`, `description` and any `payments_recorded`.
   - Computed: `days_past_due`, `open_unpaid_total`, `eligible_to_ship` (true or false), `eligibility_reason`, and `earliest_arrival_if_ordered_today`, which is null when the vendor is blocked.
   - If an invoice has an unknown status, or is marked `open` but already has a recorded payment, `eligible_to_ship` is null and a human must confirm.
   - The notes state two limits:
     - The database has no table linking products to vendors, so choosing a vendor for a SKU from its `specialty` is the agent's judgment.
     - `lead_days` are counted as calendar days, because the table does not say otherwise.

### A.3: `get_rent_due_and_cash_position`

1. **Tool name:** `get_rent_due_and_cash_position`
2. **Purpose:** Returns one lease's rent, landlord and next due date, alongside:
   - any rent payments already recorded
   - the cash balance
   - every open vendor invoice competing for that cash

   It then calculates the days until rent is due and the balance left after paying the rent, and after paying the rent plus the open invoices.
3. **Inputs:**
   - `lease_id` (required): the lease's `leases.id`, taken from the ticket's `lease_id`.
   - `account` (optional, default `checking`): the `cash_accounts.name` to check.

   A missing lease or account returns `found: false` with the valid ids or names.
4. **Database tables and fields:**
   - `leases`: `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`
   - `cash_accounts`: `name`, `balance`, `date`
   - `payments`: `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`
   - `invoices`: `id`, `vendor_id`, `amount`, `due_date`, `status`, `description`
   - `vendors`: `name`
   - `desk`: `date_today`
5. **Relevant ticket:** **Ticket 102:** Elm City Properties' rent notice for lease 1, the Chapel Street shop, says rent is due in 2 days.
6. **Why this tool is appropriate:** It shows the database facts behind the notice:
   - $2,400 rent is due 2026-09-02, 2 days after the shop date.
   - No rent payment has been recorded.
   - Checking holds $3,400.
   - Invoice 501 ($840) is also open.

   So Facilities and Accounting can see that rent is affordable on its own ($1,000 left), and that paying both obligations leaves only $160. They can then prepare a rent payment proposal for human approval.
7. **Output:**
   - From the database: the `lease` row, `rent_payments_recorded`, the `cash_account` row and `open_invoices`.
   - Computed: `days_until_rent_due`, `rent_due_status`, `cash_covers_rent`, `balance_after_rent`, `open_invoices_total`, `balance_after_rent_and_open_invoices`.
   - The notes flag three gaps:
     - The lease has no notes, so the database records no grace period, late fee or penalty terms, and those questions go to a human.
     - The `payments` table has no billing-period field.
     - A cash balance dated differently from the shop date is flagged.
