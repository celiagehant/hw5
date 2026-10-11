# Campus Customs — Operations Desk: Design

The dashboard lives in `frontend/` and uses React 19, Vite 8 and TypeScript 7.
It has no UI framework, no icon library and no state library. Its only runtime
dependencies are `react` and `react-dom`.

It talks to the FastAPI backend at `http://localhost:8000` through a single
client, `src/api/client.ts`. The base URL can be overridden with
`VITE_API_BASE`.

The assignment named three routes generically. The dashboard uses the real
routes from Problem 7:

| Named in the assignment | Actual route used |
|---|---|
| `GET /tickets` | `GET /api/tickets` |
| `GET /events` | `GET /api/events` |
| `GET /cash-balance` | `GET /api/cash/checking` |

It also uses `POST /api/tickets/{id}/run`, `GET /api/runs/{id}`,
`GET /api/tickets/{id}`, `GET /api/proposals`,
`POST /api/proposals/{id}/approve`, `POST /api/proposals/{id}/decline`,
`POST /api/reset` and `GET /api/health`.

## 1. Design concept

The desk should feel like a quiet, well-run office in a Yale building: a deep
blue masthead, ivory paper on the desk, and serif headings like a college
publication. Crisp sans-serif type carries the operational data.

The operator should feel informed and in charge. The agents do the legwork and
report back, and the human signs off. Nothing on screen pretends to more
certainty than the backend has given:
- A run that has finished is never shown as a ticket that is resolved.
- A payment is never shown as made until the backend says so.

## 2. Layout

The desktop composition is three columns under a sticky masthead:

```
┌─────────────────────────── Masthead ───────────────────────────┐
│ CC crest · Campus Customs / Operations Desk │ connection · ops │ Ledger: $ │
├───────────┬────────────────────────────────┬───────────────────┤
│ Ticket    │ Active workspace               │ Agent activity    │
│ rail      │  brief · run control · status  │ (live timeline)   │
│ (stubs)   │  approvals · decision          │                   │
│           │  contributions · draft         │                   │
│ Simulation│                                │                   │
└───────────┴────────────────────────────────┴───────────────────┘
```

- **Masthead** (`Header.tsx`):
  - The crest and the "Campus Customs / Operations Desk" title.
  - A connection pill.
  - The overall operations status: *Agents idle*, *Workflow running · n*,
    *Attention required · n*, *Backend offline* or *Connecting…*.
  - The business date from the database.
  - The **ledger**: the checking balance, set in large serif numerals and
    always visible.
- **Ticket rail** (`TicketRail.tsx`): the three real tickets from
  `/api/tickets`, drawn as paper stubs. Below them, a clearly separated
  *Simulation* area holds the reset. The rail stays fixed while the workspace
  scrolls, so the other tickets are always in view.
- **Workspace** (`Workspace.tsx`), from top to bottom:
  1. The ticket brief.
  2. The run control.
  3. The run status strip.
  4. The approval panel, placed above the decision so a pending approval is
     never below the fold.
  5. The Boss's decision.
  6. The agent contributions.
  7. The customer reply draft.
- **Activity feed** (`ActivityFeed.tsx`): a fixed right-hand column with its
  own scroll.
- **Responsive behaviour:**
  - Below 1320 px, the feed moves under the workspace.
  - Below 900 px, everything is one column: the masthead stacks, the ledger
    moves under the title, and the ticket stubs become a horizontal row you can
    swipe.
  - At 375 px wide, the page has no horizontal overflow.

## 3. Color and typography

| Role | Value | Use |
|---|---|---|
| Yale blue | `#00356b` (deep `#00264d`) | Masthead, primary buttons, headings, the Boss's color, decision rule |
| Yale tint | `#e9eff7` | Running states, confirmation box, "next step" band |
| Ivory | `#f6f2e9` / rail `#efe9dc` | Desk background |
| Paper and white | `#fffdf8` / `#ffffff` | Stubs, panels, feed |
| Red (restrained) | `#a1232b` on `#fbefee` | Pending-approval rule, blocked or failed states, errors, offline banner, reset dialog |
| Amber | `#8a5600` on `#fcf3e2` | Awaiting approval, escalated, guardrails |
| Green | `#2c6a43` on `#ecf5ee` | Resolved, completed findings, executed payments |
| Ink and muted | `#1c2631`, `#5c6776`, `#636b77` | Body text, metadata, timestamps |

Typography:
- **Cormorant Garamond** (serif) is used for the masthead title, ticket
  subjects, section titles, the Boss's recommendation pull-quote, proposal
  amounts, the ledger and the customer letter.
- **Inter** carries all operational data.
- A system monospace font is used for ticket numbers (`No. 101`), run ids, tool
  calls and record ids.
- Both web fonts load from Google Fonts with installed fallbacks (Iowan Old
  Style, Charter or Georgia; the system sans-serif), so the page still reads
  well offline.
- Small uppercase, letter-spaced "kicker" labels (*Ticket desk*, *Your decision
  is needed*) give a magazine-like hierarchy.

I checked text contrast against WCAG AA:
- muted text on ivory: 5.1:1
- faint labels on white: 5.4:1
- red on its tint: 6.7:1
- white on Yale blue: 12.2:1

## 4. Agent activity

- **Agent identity:** each agent has a fixed monogram and accent color
  (`lib/agents.ts`). The color appears on the monogram square and as the left
  rule of each event card.

  | Agent | Monogram | Color |
  |---|---|---|
  | Boss | BO | Yale blue |
  | Inventory | IN | teal |
  | Accounting | AC | plum |
  | Facilities | FA | ochre |
  | Customer Service | CS | olive |
  | Human operator | OP, shown as *You* | ink |
  | Orchestrator (events without an agent) | DK, shown as *Desk* | gray |

  Hovering a monogram shows the agent's role.
- **Event type:** the kind label, icon and color come only from the backend's
  `event_type` (and `agent`), never from parsing text.
  - *Investigating* (`agent_started`), *Tool call*, *Delegation*, *Handoff
    returned*, *Guardrail*, *Run finished*, *Payment executed* and so on each
    have their own label and icon.
  - `agent_completed` is shown as **Decision** when the agent is the Boss, and
    **Finding** otherwise.
  - Tones: blue for progress, green for completed or successful, amber for
    attention, red for errors and refusals.
- **Delegations** show both monograms with an arrow. A returned handoff points
  from the delegate back to the caller, for example *Facilities → Boss*.
- **Tool calls** show the exact MCP call as code, such as
  `get_rent_due_and_cash_position(lease_id=1, account=checking)`, with its
  outcome.
- **Compact by default:** descriptions are clamped to three lines. A *Details*
  button expands the event's findings, recommendation, returned record ids,
  error, and agent role, model, Portkey trace id and run id. Missing optional
  fields are simply not shown.
- **Live behaviour:**
  - While a run is active, the feed polls `/api/events` every 2.5 seconds,
    using `after=<last event id>` so only new events are fetched. Events are
    merged by `event_id` (no duplicates) and kept in timestamp order.
  - New events fade in. The list follows new events unless you have scrolled
    up. A *Working…* line and a *Live* pill show the run is in progress.
  - Polling stops when no run is active; a 20-second health check remains.
- **History:** the feed shows the current run by default. *Show N earlier
  events from past runs* reveals the rest of the ticket's audit history,
  divided by run.

## 5. Ticket states

Each stub has a colored left edge and a status pill, and the same state appears
in the brief:

| State | Shown when | Look |
|---|---|---|
| Open · not yet run | Status open, no recorded run | Neutral edge and pill |
| Agents working | The backend reports an active run | Blue edge, pulsing dot, a moving line along the bottom of the stub |
| Awaiting approval / Escalated / Needs clarification | The last recorded run ended that way and the ticket is open | Amber edge and pill |
| Blocked | The last run ended blocked | Red edge and pill |
| Run failed / Stopped at a limit | The run failed or hit a limit | Red edge and pill |
| Resolved | **Only** when the persisted `tickets.status` is `resolved` | Green edge and check |

The run status strip always gives two separate facts:
1. How the run ended, for example *Run finished: Escalated to a human*.
2. The persisted ticket status, either *"The ticket is still open in the
   database — the run finishing does not resolve it"* or *"The database
   confirms this ticket is resolved."*

A run whose details are no longer held by the backend (after a restart) is
labelled as such, and its summaries are rebuilt from the audit trail.

## 6. Cash and approvals

**The ledger** in the masthead:
- It shows `GET /api/cash/checking`, formatted with `Intl.NumberFormat` in the
  account's own currency, with the account name and balance date.
- It is re-read on load, after every approval (successful or not), after a
  finished run and after a reset. The dashboard never calculates a balance.
- When a new value differs from the last one fetched, the figure flashes softly
  and the footnote shows *▼ was $3,400.00* (both values from the backend) for a
  few seconds.
- While the backend is offline, the footnote reads *Last known value · backend
  offline*.

**The approval panel** appears only when the selected ticket has real
proposals from `/api/proposals`; no ticket gets an approval button by default.
- **Pending proposals** sit under a red rule: *Your decision is needed*.
- **Each proposal card shows** fields that exist in the data:
  - the kind badge: *Payment · vendor invoice*, *Payment · rent*, *Purchase
    order* or *Price decision · discount* (the last two use a lighter, outlined
    badge because they move no cash)
  - proposal id, amount, payee, target (`Invoice #501`, `Lease #1`,
    `Vendor #1`), and SKU, size and quantity for an order
  - the description and any `blocked_reason` flagged by the agents
- **A plain-language explanation** tells payments and orders apart. A payment
  *"pays $840.00 from checking"*; a purchase order *"records an approved draft
  purchase order. No cash moves and nothing is sent to the vendor."*
- **Deliberate approval.** *Review and approve…* opens an inline confirmation
  box showing payee, amount, target and, for payments, the current checking
  balance. The operator must type their name (remembered locally) before the
  button becomes active: *Authorize payment of $840.00* or *Approve purchase
  order*. The request repeats the proposal's exact amount and payee, which the
  backend checks. Buttons are disabled while submitting, so there is no double
  submission.
- **Results come only from the backend.**
  - **Success:** a green notice quotes the backend's message, the balance
    before and after as reported by the backend, and any ticket that became
    resolved. The proposal moves to *History* as *Paid* or *Approved*, so it
    cannot be approved again unknowingly.
  - **Refusal:** the real code and message are shown, e.g. *Not approved —
    Insufficient funds* or *Not approved — Network*, together with "Nothing was
    paid". The balance is re-read and stays unchanged.
- **Explicit Decline.** Each card also has *Decline…*, which opens a red
  confirmation box asking for the operator's name and an optional reason and
  calls `POST /api/proposals/{id}/decline`. The proposal moves to *History* as
  *Declined*; nothing is paid, ordered or sent.
- **Discount decisions** (added in Problem 9) appear as *Price decision ·
  discount* cards. They show the percentage (e.g. *10% off*), the requester, the
  quantity and SKU, and the dollar value below list. The text explains that
  approving records a price decision only: no cash moves, the price list is
  unchanged and nothing is sent.

## 7. Interaction and accessibility

- **Loading and error states:**

  | Situation | What the operator sees |
  |---|---|
  | Starting up | *Connecting…* |
  | Loading tickets or activity | A spinner with *Loading tickets…* / *Loading activity…* |
  | Starting a run | *Starting…* on the run button, then *Run <id> started.* or the backend's error |
  | Run active, no events yet | *The run has started; waiting for the first agent event…* |
  | No activity since a reset | An empty-feed message saying so |
  | Failed request | An inline notice with **Retry** |
  | Backend offline | A red banner with **Retry now**, the masthead shows *Backend offline*, and polling slows to every 8 seconds. When the backend returns, the desk reconnects and reloads by itself. |

- **"Connected" is earned:** it is shown only after a real request succeeds.
  Requests time out after 15 seconds.
- **Confirmation steps:**
  - Approvals use the inline confirmation box described in section 6.
  - The reset sits apart in the rail's *Simulation* area. It opens a modal
    explaining what will be cleared and what is kept, has Cancel focused first,
    closes with Escape, and is disabled while a run is active. Nothing resets on
    page load.
- **The run button explains itself:** when disabled, it says why (*already
  working*, *resolved — reset to run again*, or *backend not connected*).
- **Keyboard and screen readers:**
  - Every control is a native `<button>` or `<input>` with a visible focus ring.
  - Ticket stubs carry `aria-current`, and expanders carry `aria-expanded`.
  - The dialog has `role="dialog"` and `aria-modal`.
  - The feed and toasts are `aria-live="polite"`, and agent monograms have
    accessible labels.
  - A *Skip to workspace* link is provided.
- **Motion is purposeful only:** pulsing dots and moving lines for active work,
  a short fade-in for new events and dialogs, and the ledger flash.
  `prefers-reduced-motion` turns them all off.

## 8. Creative decisions

- **Tickets as paper stubs.** Each ticket has a serial number in monospace
  (`No. 101`), a dashed tear line and a colored edge. The rail reads like a
  spike of real work orders, not rows in a table.
- **The ledger.** The balance is set like a figure in an account book, in serif
  numerals at the top right. Its *"▼ was $3,400.00"* footnote makes every
  payment's effect visible without inventing a transaction history.
- **The crest.** A small "CC" shield in ivory on Yale blue gives the desk an
  institutional identity without using a university mark.
- **The Boss's decision as a pull-quote.** The recommendation is set in serif
  behind a blue rule, like an editor's note. The operator summary follows,
  then a highlighted *Next step* band and lists of blockers and items needing
  sign-off.
- **A team roster.** Five monogram chips light up for agents that took part;
  the others are marked *not called*. Each contribution card shows the agent's
  outcome, findings, blockers, who asked them, whom they asked and which MCP
  tools they used. This makes it visible that the Boss delegates selectively.
- **A customer draft set as a letter.** It shows To and Subject, a serif body,
  *Confirm before sending* questions and a *Draft only — the system cannot send
  email* stamp.
- **Calm by default, red by exception.** Red appears only where a human must
  act or something failed: the approval rule, blocked tickets, refusals and the
  offline banner. A glance at the desk shows where attention is needed.
