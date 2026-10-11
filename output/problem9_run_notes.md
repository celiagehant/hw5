# Problem 9 — Run notes

## Pre-run fixes

These were made before the reset. Earlier runs, all still in
`output/audit_trail.json`, showed that tickets could not reach a legitimate
resolved state:

| Run | Ticket | Ended | What it showed |
|---|---|---|---|
| f707c0ef250c | 103 | blocked | |
| 5ca79e0165aa | 103 | escalated | |
| e27759d68876 | 103 | escalated | |
| db410c786e42 | 103 | escalated | |
| 5e1a099d9022 | 101 | escalated | Accounting counted next month's rent against today's cash |
| 0e4255e39a65 | 101 | escalated | Same as above |

Three causes, and the fix for each:

1. **No route for a discount decision.** The Boss's `offer_discount` action was
   never stored as an approvable proposal, and Accounting was told never to pick
   a percentage, so ticket 103 always escalated with nothing a human could act
   on.
   - `record_run_outcome` now stores `offer_discount` proposals, priced from
     `pricing`.
   - `approve_proposal` approves a discount only if the price stays above unit
     cost. No cash moves.
   - Accounting now recommends one specific, moderate percentage for a human to
     decide.
2. **No way to decline.** A proposal the operator would not approve stayed
   pending forever and blocked resolution. Added the `decline_proposal` MCP tool
   and `POST /api/proposals/{id}/decline`, and a Decline button on the
   dashboard.
3. **Next month's rent counted as due now.** After this month's rent is paid,
   Accounting counted October's rent (due in 32 days) as competing with today's
   bills, and escalated. Its prompt now weighs obligations by due date and
   reports later ones as a risk.

The offline tests pass after the fixes: 25 payment checks and 30 safeguard
checks.

## Reset (step 1)

- **How:** the dashboard's *Reset working database…* control, which calls
  `POST /api/reset`, confirmed in its dialog.
- **Reset event:** `database_reset`, run id `reset-35872609`, at
  **2026-10-11T17:42:03.315Z**. Outcome `ok`.
- **Restored from:** `data/campus_customs.db`, which is read-only (`-r--r--r--`)
  with SHA-256 `23686a90…f360a`, unchanged.
- **Checked by SQL on `data/campus_customs_new.db`** after the reset:
  - tickets 101, 102 and 103 are all `open`
  - `cash_accounts`: `checking` balance **3400.0**, dated 2026-08-31
  - `payments`: 0 rows
  - invoice 501: $840.00, `open`
  - lease 1: $2,400, `next_due` 2026-09-02
  - no `ticket_runs`, `action_proposals` or `approvals` tables
- **Opening balance:** account `checking`, **$3,400.00**.
- **Audit trail:** it held 327 events after the reset event. No earlier events
  were removed.

## Ticket runs (step 2)

All three were run through the dashboard at http://localhost:5173, against the
backend at http://localhost:8000. You started both with the documented
commands (`uvicorn main:app --reload --port 8000` in `backend/`, and
`npm run dev` in `frontend/`), and the MCP server is launched by the backend.

Each ticket was selected on the board and started with **Run the agent team**.
I approved proposals in the dashboard's approval panel, after reviewing each
one, as instructed in the Problem 9 prompt. The approver name recorded is
**"Celia Gehant (entered by Claude Code)"**, so the records show who actually
clicked.

| Ticket | Run id | Run ended | Proposals and human decisions | Resolved |
|---|---|---|---|---|
| 101 | `de29a5509213` (17:42:32–17:43:45Z) | `blocked`: invoice 501 blocks the vendor | #1 `pay_invoice` $840 to Bulldog Print Co: **approved and executed** 17:44:22Z, payment 1. #2 `purchase_order` 1 × CC-TEE-WHITE S, $8: **approved** 17:44:43Z after the invoice was paid. No cash moved. | 17:44:43Z |
| 102 | `1fcc045db23e` (17:45:29–17:46:01Z) | `awaiting_human_approval` | #3 `pay_rent` $2,400 to Elm City Properties: **approved and executed** 17:46:16Z, payment 2. | 17:46:16Z |
| 103 | `e407889e6757` (17:46:43–17:47:18Z) | `awaiting_human_approval` | #5 `offer_discount` 10% on 20 × CC-HOOD-NAVY, $116 below list: **approved** 17:48:00Z. #4 `purchase_order` 12 × CC-HOOD-NAVY M, $264: **approved** 17:48:13Z. Neither moved cash. | 17:48:13Z |

Each resolution was checked in both places:
- **Backend:** `GET /api/tickets` returned `resolved` for each ticket.
- **Database:** `SELECT id, status FROM tickets` returned `resolved` for each.

The full run results, saved from `GET /api/runs/{id}`, are in
`output/problem9_runs/`. Screenshots are in `output/screenshots/`.

### Operator review notes
- **#1 ($840 invoice 501):** the amount matches the invoice, which was 3 days
  overdue. Checking went from $3,400 to $2,560, which still covered the $2,400
  rent due Sept 2. Approved.
- **#2 ($8 purchase order):** submitted only after #1, so the backend's recheck
  found the vendor eligible. Approved.
- **#3 ($2,400 rent):** the amount matches lease 1, and rent was due in 2 days.
  Checking went from $2,560 to $160. Approved.
- **#5 (10% discount):** each hoodie at $52.20 keeps $30.20 margin per unit, and
  this was Accounting's single recommendation. Approved.
- **#4 ($264 purchase order):** a **judgment call**. Approving moves no cash, but
  it commits the shop to a future $264 vendor bill while checking holds $160.
  I approved it because the 12 units fill a request the club has already made
  (20 × $52.20 = $1,044). Any later payment of that bill would still face the
  insufficient-cash check. No agent compared this order's cost with remaining
  cash, because Accounting was only asked about the discount. That gap is
  recorded under "Remaining limitations" in the harness.

## Cash reconciliation (checked against the database)

| Step | Ticket | Transaction | Outflow | Checking after |
|---|---|---|---:|---:|
| Opening, after reset 17:42:03Z | — | — | — | $3,400.00 |
| Payment 1 | 101 | Invoice 501 to Bulldog Print Co (proposal #1) | $840.00 | $2,560.00 |
| — | 101 | Purchase order #2, 1 tee for $8, approved; no cash moves on approval | $0.00 | $2,560.00 |
| Payment 2 | 102 | Rent for lease 1, due 2026-09-02, to Elm City Properties (proposal #3) | $2,400.00 | $160.00 |
| — | 103 | Discount #5 and purchase order #4 approved; neither moves cash | $0.00 | $160.00 |
| **Closing** | | **Total outflows** | **$3,240.00** | **$160.00** |

- **Arithmetic:** $3,400.00 − $3,240.00 = **$160.00**.
- **Database checks:** `SUM(payments.amount)` = 3240.0, and
  `cash_accounts.balance` for `checking` = 160.0. Invoice 501 is `paid`, and
  lease 1's `next_due` is 2026-10-02.
- **Dashboard:** the ledger shows $160.00 and `GET /api/cash/checking` returns
  160.0. There is no discrepancy.
- **Commitments not yet in cash:** the approved purchase orders, $8 and $264
  ($272 in total), will become vendor bills. The database has no table for
  purchase orders or future payables, so they do not appear in
  `cash_accounts` or `payments`.
