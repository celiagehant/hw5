# Campus Customs — Multi-Agent Operations Desk (Homework 5)

Five PydanticAI agents (Boss, Inventory, Accounting, Facilities, Customer
Service) work the shop's operations tickets.
- All five use **GPT-6 Luna** through Portkey.
- They read shop data only through an **MCP server** (`mcp_server/`) backed by
  `data/campus_customs_new.db`.
- A **FastAPI backend** (`backend/`) runs the team and handles human approvals.
- A **React dashboard** (`frontend/`) is the operator's desk.

Agents can only *propose* payments, purchase orders and discounts. A human
approves each one, and money moves only inside the local working database.

The full system description is in `output/harness.md`, and the design notes
are in `output/design.md`.

## Layout

```
.mcp.json              MCP connection for Claude Code (relative paths; run from this folder)
requirements.txt       Python dependencies
.env.example           copy to .env and add PORTKEY_API_KEY
AI_prompts.md          prompts used to build the project
data/                  campus_customs.db (original, never modified) + campus_customs_new.db (working copy)
mcp_server/            server.py (FastMCP, 11 tools), operations.py, README.md
backend/               main.py (FastAPI), models.py, agents, prompts/ (boss, inventory, accounting, facilities, customer_service)
frontend/              React + Vite + TypeScript dashboard
tests/                 offline safety checks (no model calls)
output/                harness.md, mcp_smoke.json, desk_tickets.html, design.md, resolved_tickets.json,
                       resolved_board.html (+ screenshots/), audit_trail.json, problem9 run notes and results
```

## 1. One-time setup

From this folder (macOS or Linux, with Python 3.12+ and Node 20+):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --prefer-binary -r requirements.txt
cd frontend && npm install && cd ..
cp .env.example .env        # then put your PORTKEY_API_KEY in .env
```

The backend loads `.env` from this folder. If that file isn't there, it uses
the one in the parent folder.

## 2. Copy the original database to the working copy (clean start)

`data/campus_customs.db` is the untouched original. Everything else works on
`data/campus_customs_new.db`. To create a fresh working copy:

```bash
cp data/campus_customs.db data/campus_customs_new.db
chmod 644 data/campus_customs_new.db
```

The `chmod` matters: the original is kept read-only, and `cp` would otherwise
copy that permission. Once the backend is running, use the reset in step 6
instead.

## 3. Start the MCP server

You normally don't start it yourself. The backend launches it over stdio when
it starts, and Claude Code launches it from `.mcp.json` when a session is
opened in this folder. To run it on its own:

```bash
.venv/bin/python mcp_server/server.py          # stdio
.venv/bin/python mcp_server/server.py --http   # http://127.0.0.1:8001/mcp
```

## 4. Start the FastAPI backend (terminal 1)

```bash
cd backend
source ../.venv/bin/activate
uvicorn main:app --reload --port 8000
```

Wait for `Application startup complete`, which takes about 5–10 seconds while
the MCP server starts. The API is at http://localhost:8000, with interactive
docs at http://localhost:8000/docs.

## 5. Start the React board (terminal 2)

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. The header should show **Connected ·
localhost:8000** and the checking balance.

## 6. Reset the database before a full three-ticket run

Any one of these restores the working copy from the original. Each refuses to
run while an agent run or approval is in progress, and none touches the
original database or the audit trail:

- **On the board:** *Simulation → Reset working database…*, then confirm.
- **From a terminal:**
  ```bash
  curl -X POST http://localhost:8000/api/reset -H 'Content-Type: application/json' -d '{"confirm":"RESET"}'
  ```

After the reset, checking is $3,400.00 and tickets 101, 102 and 103 are open.
Run each ticket from the board, then approve or decline its proposals in the
approval panel.

## Checks

```bash
.venv/bin/python tests/test_offline.py     # guards, delegation limits, audit log
.venv/bin/python tests/test_payments.py    # approvals, payments, cash floor, concurrency
```

## Safety notes

- `.env` is git-ignored, and no key is stored in code, logs or the audit trail.
- There is no tool for email, vendor contact or real payments. Customer replies
  are drafts, and purchase orders are approved drafts that are never sent.
- `output/audit_trail.json` is append-only and keeps every past run, including
  across resets.
