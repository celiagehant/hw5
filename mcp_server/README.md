# Campus Customs Operations MCP Server

## What it does

`server.py` is a FastMCP server, registered as `campus-customs-ops`, and it is
the data layer of the Campus Customs multi-agent operations system. The five
agents (Boss, Inventory, Accounting, Facilities and Customer Service) run in the
FastAPI backend and call this server's tools to read shop records. The React
dashboard shows their results to the human operator.

## Why the agents go through it

The agents never write SQL or open the database themselves. They can only call
the tools listed below, so every fact an agent uses comes from a fixed, reviewed
query against real table and field names. Each result keeps three things apart:
- `database`: values copied unchanged from the tables.
- `computed`: plain arithmetic on those values.
- `notes`: gaps or ambiguities that an agent must report rather than fill in.

All the agent-facing tools are read-only: the database is opened in SQLite `mode=ro`, so
they cannot change records even by mistake. Days past due and days until due are
counted from the shop's business date in `desk.date_today`, not from the
computer's clock.

## Database

- **Working copy:** `../data/campus_customs_new.db`. The server reads only this file, and it fails with an error if the file is missing instead of creating an empty one. `../.mcp.json` names it through the `CAMPUS_CUSTOMS_DB` environment variable; the path is relative to the Homework 5 folder.
- **Original:** `../data/campus_customs.db`. It is never opened: the server's `connect()` refuses that path. The file is also read-only on disk. It stays untouched as the clean reference and the source for resetting the working copy, so a bad run or a test payment can always be undone by copying it again.

## Tools

Eleven tools are registered. Eight are **read-only**. Three are
**state-changing** and reserved for the FastAPI backend: `record_run_outcome`,
`approve_proposal` and `decline_proposal`. The backend gives each agent only the tools listed against
it below (`backend/deps.py`), and also blocks any other call in its MCP hook, so
no agent can record proposals, approve or decline them, or move money.

| Tool | Purpose | Inputs | Tables used | Used by | Access |
|---|---|---|---|---|---|
| `get_stock_and_pricing` | Stock on hand for one SKU by size, the shortfall against a requested quantity, and unit cost, list price and margin. Used for tickets 101 and 103. | `sku` (required), `size` (optional), `qty_needed` (optional, a positive number; needs a size unless the SKU has only one) | `inventory`, `pricing` | Inventory, Accounting | Read-only |
| `check_vendor_eligibility` | For each vendor: specialty, `lead_days`, invoices with days past due, and whether it may ship. A vendor with an `open` invoice is blocked. Also the earliest arrival date if ordered today. Used for ticket 101, where invoice 501 blocks Bulldog Print Co, and for restocking in ticket 103. | `vendor_id` (optional; leave out to check every vendor) | `vendors`, `invoices`, `payments`, `desk` | Inventory, Accounting | Read-only |
| `get_rent_due_and_cash_position` | A lease's rent and next due date, rent payments already recorded, the cash balance and the open invoices competing for that cash. Used for ticket 102. | `lease_id` (required), `account` (optional, default `checking`) | `leases`, `cash_accounts`, `payments`, `invoices`, `vendors`, `desk` | Facilities | Read-only |
| `list_open_tickets` | Tickets whose status is "open", oldest first. | none | `tickets`, `desk` | The orchestrator (`--all`) | Read-only |
| `get_ticket_details` | One ticket in full, plus whether its linked inventory row, lease and invoice exist, with their ids. It does not return stock, cash or rent amounts. | `ticket_id` (required) | `tickets`, `inventory`, `leases`, `invoices`, `vendors`, `desk` | The orchestrator, Boss, Customer Service | Read-only |
| `get_cash_and_obligations` | The cash balance next to every open invoice (with days past due), each lease's next rent (with days until due) and recent payments, with totals and the balance left after all of them. | `account` (optional, default `checking`) | `cash_accounts`, `invoices`, `vendors`, `leases`, `payments`, `desk` | Accounting | Read-only |
| `list_tickets` | Every ticket with its persisted status (`open` or `resolved`) and its latest recorded run. | `status` (`all`, `open` or `resolved`; default `all`) | `tickets`, `ticket_runs`, `desk` | FastAPI backend (dashboard) | Read-only |
| `list_action_proposals` | Payment, purchase-order and discount proposals with stable ids, newest first (max 100). | `ticket_id`, `status` (optional: pending, executed, approved, declined, superseded) | `action_proposals` | FastAPI backend (dashboard) | Read-only |
| `record_run_outcome` | Records a finished run's status and its proposals (`pay_invoice`, `pay_rent`, `purchase_order`, `offer_discount`). Payment amounts must match the database exactly. Purchase-order cost comes from `pricing`, and a discount's dollar value is computed from `pricing`; a discount at or below cost is skipped. An identical pending proposal keeps its id; others are superseded. It resolves the ticket only when nothing is left to approve. | `run_id`, `ticket_id`, `run_status`, `proposals` (each: `kind`, `ref_id`, `amount`, `payee`, `sku`, `size`, `quantity`, `discount_pct`, `description`, `blocked_reason`) | Reads `tickets`, `invoices`, `vendors`, `leases`, `pricing`, `inventory`; writes `ticket_runs`, `action_proposals`, `tickets.status` | Orchestrator, after every run | **State-changing**, backend only |
| `approve_proposal` | One explicit human approval, which must repeat the exact amount and payee. Re-checked in one locked transaction. A payment debits checking (never below zero), records a `payments` row, and marks the invoice paid or moves the rent due date on a month. A purchase order is approved only if the vendor owes nothing. A discount is approved only if the price stays above unit cost. Neither moves cash, and nothing is ever sent. | `proposal_id`, `approved_by`, `confirm_amount`, `confirm_payee` | Writes `cash_accounts`, `payments`, `invoices`, `leases`, `action_proposals`, `approvals`, `tickets` | FastAPI backend (`POST /api/proposals/{id}/approve`) only | **State-changing**, moves money |
| `decline_proposal` | One explicit human decision not to approve a pending proposal. It marks the proposal `declined` and records the decision; nothing is paid, ordered or sent. A ticket can still resolve once its other proposals are carried out. | `proposal_id`, `declined_by`, `reason` (optional) | Writes `action_proposals`, `approvals`, `tickets` | FastAPI backend (`POST /api/proposals/{id}/decline`) only | **State-changing**, no money |

Unknown ids, SKUs or accounts return `found: false` with the valid values.
Invalid inputs return an error message. `approve_proposal` returns
`ok: false` with a `code` (`not_found`, `mismatch`, `not_pending`,
`insufficient_funds`, `not_payable`, `vendor_ineligible`, `below_cost`,
`invalid_approver`, `database_rejected`) and changes nothing except the record
of the attempt.

The write tools add three tables to the working copy: `ticket_runs`,
`action_proposals` and `approvals`. They also add a trigger that refuses a
negative cash balance. A reset restores the baseline and removes them, and they
are recreated on the next write.

## Run

From the `Homework 5` folder, using its `.venv`:

```bash
.venv/bin/python mcp_server/server.py          # stdio
.venv/bin/python mcp_server/server.py --http   # http://127.0.0.1:8001/mcp
```
