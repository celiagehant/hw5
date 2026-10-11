# Homework 5 — AI Prompts

A record of the prompts used for Homework 5.

## Problem 1 — Vibe coder prompts and project setup

Based on HW #4 (Campus Customs application), we are going to make a working multi-agent operations system with an MCP Server, FastAPI backend and React dashboard (I will go step by step telling you when to do it). 
1. Database setup and integrity
The Homework 5 folder contains the database required for this assignment.

* Make a copy of campus_customs_new_db and use the new database copy for all operations performed by the MCP server and FastAPI backend.
* Never modify, overwrite, delete, or reset the original `Campus Customs DB`. It must remain available as a clean reference and reset source.


2. Five-agent team
I will explain the assignment now. You will implement five distinct agents:
Agent 1: Boss / Operations Manager
Responsibilities:

* Read and interpret each incoming operations ticket.
* Determine the problem, urgency, relevant records, and expected outcome.
* Assign the ticket to the appropriate specialist agent or agents.
* Coordinate multi-step workflows when a ticket requires collaboration.
* Evaluate specialist findings and resolve conflicting recommendations.
* Make the final operational decision about the proposed course of action.
* Identify actions that require human approval before execution.
* Track ticket status, blockers, outstanding approvals, and completion.
* Provide the human operator with a concise explanation of the decision and its supporting evidence.

The Boss must not bypass specialist findings, database constraints, human approval requirements, or financial safeguards.
The Boss's operational decision is not equivalent to authorization to execute a restricted financial action.
Agent 2: Inventory Manager
Responsibilities:

* Check inventory by product SKU and size.
* Determine available stock using the actual database records.
* Identify shortages and compare available stock with the ticket's requirements.
* Determine whether replenishment is necessary.
* Identify eligible vendors and calculate expected replenishment timing using the lead times recorded in the vendors table.
* Check whether a vendor has an open, unpaid invoice that prevents new shipments.
* Recommend a restocking quantity and vendor when sufficient information exists.
* Coordinate with Accounting when a purchase order or payment may be needed.

Never invent inventory quantities, SKUs, sizes, vendor lead times, supplier availability, or delivery dates.
If the data is incomplete or no eligible vendor exists, report the limitation rather than fabricating a solution.
Agent 3: Accounting Manager
Responsibilities:

* Review the shop's available cash, invoices, outstanding liabilities, and relevant financial records.
* Identify overdue invoices using the current date in the shop's local timezone.
* Calculate invoice aging, payment amounts, and relevant margins when the necessary data exists.
* Evaluate the financial implications of proposed purchases and restocking decisions.
* Prepare payment proposals and purchase orders for human review.
* Check whether a proposed payment is affordable.
* Explain the impact of a proposed payment on the available cash balance.
* Coordinate with Inventory when unpaid invoices affect vendor eligibility.

Mandatory financial controls:

* No payment may be executed without explicit human approval.
* The Accounting agent may prepare and recommend a payment but cannot authorize its own payment.
* The payment tool must independently validate the approval and the available cash balance immediately before execution.
* If available cash is insufficient, the payment tool must refuse the transaction.
* The system must never permit a negative cash balance.
* Use database transactions and appropriate locking or equivalent safeguards to prevent concurrent payments from spending the same funds.
* A rejected or failed payment must not reduce cash or mark an invoice as paid.
* Never fabricate financial records or assume that an invoice has been paid without confirmation from the database.

Cash only flows out in this assignment. Do not model revenue, sales receipts, or other incoming cash flows. Do not introduce deposits or other transactions that increase cash unless explicitly required by the official assignment.
If margin calculations require sales or cost information that is not present in the database, explain which information is missing rather than inventing values.
Agent 4: Facilities Manager
Responsibilities:

* Handle operational issues involving the physical shop space.
* Review lease terms, rent amounts, due dates, payment status, and related records available in the database.
* Identify overdue rent or other facilities-related obligations.
* Assess upcoming deadlines and operational risks.
* Prepare recommendations, notices, or payment proposals for human review when appropriate.
* Coordinate with Accounting if a facilities obligation requires a financial action.
* Escalate missing lease information or ambiguous contractual terms to the human operator.

Use the actual database records and documented lease terms. Do not invent rental amounts, contract provisions, penalties, or deadlines.
Agent 5: Customer Service Manager
Responsibilities:

* Draft customer communications based on the ticket and verified information from the database or other authorized agents.
* Explain inventory availability, expected fulfillment timing, or operational issues only when supported by reliable information.
* Ask for clarification or flag uncertainty when the necessary information is unavailable.
* Provide polished, professional, customer-friendly messages for human review.
* Coordinate with the Boss and Inventory agent when customer requests depend on inventory or supplier information.

All customer communications must remain drafts. The system must not send emails, contact customers, or communicate externally.
Vendor eligibility
Vendor lead times must come from the existing vendors table.
A vendor must not ship new product while it has an open, unpaid invoice. Before approving or executing a replenishment workflow, verify the vendor's eligibility against the current database state.
Do not assume that a vendor is eligible simply because an agent previously identified it as a suitable supplier. Recheck eligibility when it matters.
Human payment approval
Every payment requires explicit human approval.
A recommendation, a Boss decision, or an agent's internal confirmation does not constitute human approval.
Payments must remain pending until an authorized human approves them. The payment execution tool must reject missing, invalid, revoked, or otherwise ineligible approvals.
Approval must be associated with the specific proposed payment, including its amount, payee or invoice, and other relevant identifying details. If the proposal changes after approval, require approval of the revised proposal.
Cash sufficiency
The payment tool must refuse any payment that exceeds the available cash balance.
Check the latest balance at execution time, not merely when the proposal is created. Prevent concurrent transactions from causing the balance to become negative.
Never simulate a successful payment if the database rejects it.
No real-world external actions
This assignment is a controlled simulation:

* Do not email or otherwise contact customers.
* Do not contact vendors or call them.
* Do not submit actual purchase orders to vendors.
* Do not make actual bank transfers or external payments.
* Keep customer communications, purchase orders, and other external-facing documents as drafts.
* The only simulated financial execution is an explicitly approved payment recorded in the local working database.

6. Model configuration: GPT-6 Luna through Portkey only
This is a mandatory requirement for every AI agent.
All five agents—the Boss, Inventory, Accounting, Facilities, and Customer Service agents—must use GPT-6 Luna through Portkey.

* Use Portkey as the model gateway for every agent invocation.
* Centralize the provider and model configuration so the five agents use the same approved model configuration.
* Follow the model identifier and configuration supported by the existing Portkey setup and the assignment environment.
* Store API keys and credentials in environment variables or the project's existing secure configuration mechanism. Never hardcode secrets or expose them in the frontend, logs, screenshots, or repository.

## Problem 2 — Study the Campus Customs database

Open data/campus_customs.db and look through every table and its fields. Study the three open tickets so you can see how they link to other tables. Start output/harness.md. For each table, list the fields and one short line on why that table matters for the agents.

## Problem 3 — Build the MCP server

Problem 3 
Create the MCP server for the Campus Customs multi-agent operations system using FastMCP `mcp/server/` 
The server must:

* Use `data/campus_customs_new.db` as its database.
* Never invent, infer as fact, or fabricate database records, quantities, dates, financial values, or business rules.

2. Select the three tools
Review all three open tickets in the database and select the three tools that would be most useful for addressing them.
Choose the tools based on the actual information required to resolve those tickets. Do not create generic tools merely to cover broad categories.
For each tool:

* Give it a clear, descriptive name.
* Provide a concise description explaining exactly what it retrieves or does and when an agent should use it.
* Define explicit input parameters and validate them where applicable.
* Query the actual database using verified table and field names.
* Return the relevant records and identifiers needed for follow-up operations.
* Handle missing or ambiguous data without making up answers.

Prefer focused, read-only tools that retrieve the information needed for the current tickets. 

3. Update `output/harness.md`
Preserve the existing information from Problem 2 and add a section titled MCP Server — Initial Tools.
Document each of the three tools separately. For every tool, include:

1. Tool name: The exact registered MCP tool name.
2. Purpose: What information the tool retrieves or what permitted operation it performs.
3. Inputs: Each parameter and what it identifies.
4. Database tables and fields: The exact tables and fields read.
5. Relevant ticket: The actual ticket identifier and its specific requirement.
6. Why this tool is appropriate: One concrete sentence explaining how the returned information helps resolve that ticket.
7. Output: The key fields or records returned to the agent.

Avoid vague explanations such as "reads inventory" or "gets financial information." Explain the connection between the actual ticket, the database records retrieved, and the decision an agent can make using the result.
Distinguish between information retrieved directly from the database and any recommendation an agent may subsequently generate.
5. Create `mcp_server/README.md`
Create a concise README explaining:

* What the MCP server does in the Campus Customs architecture.
* Why the agents will use it as their controlled interface to database information.
* Which database file it uses and why the original database must remain untouched.
* The purpose and inputs of each of the three implemented tools.

## Problem 4 — Add the MCP server to the vibe coder and test each tool

Problem 4 — Connect the MCP Server and Run Smoke Tests
1. Configure the MCP connection
Create `.mcp.json` at the project root using the connection format supported by the Vibe Coder environment and the existing FastMCP server.

* Use the actual server entry point, working directory, and startup command.
* Include the required environment configuration without hardcoding API keys or other secrets.
* Ensure the server uses `data/campus_customs_new.db`, not the original database.
* Use the appropriate transport and configuration syntax for the implemented FastMCP server.
* Do not invent configuration fields or assume that an unsupported configuration format will work.

2. Connect and verify tool discovery
Use the Vibe Coder's actual MCP integration to connect to the server.
Confirm that:

* The connection succeeds.
* The server exposes exactly the three tools implemented in Problem 3.
* The registered tool names match `output/harness.md` and `mcp/server/README.md`.
* Each tool's description and input schema are available to the Vibe Coder.

If connection or discovery fails, investigate and correct the underlying issue rather than fabricating a successful result.
3. Execute a smoke test for every tool
Invoke each of the three MCP tools through the Vibe Coder using a clear, relevant natural-language prompt.
Choose prompts that exercise each tool's actual purpose and use valid inputs grounded in the three open tickets and the database schema.
For each tool, capture:

* The exact prompt submitted to the Vibe Coder.
* The exact registered MCP tool name.
* The actual tool arguments, if available.
* The actual tool output returned by the MCP server.
* The outcome: passed or failed.
* A brief explanation of what the result verifies.

Do not simulate a tool call by writing an expected result manually. Do not use hardcoded values in place of actual tool output. If a tool fails, record the failure accurately and fix it before claiming that the smoke test passed.
4. Save the smoke-test evidence
Create `output/mcp_smoke.json` using valid JSON.
Use a clear structure containing:

* Test execution timestamp.
* MCP server identifier.
* Database filename used.
* One test entry for each of the three tools.
* The exact prompt submitted.
* Tool name and arguments.
* Actual tool output.
* Pass/fail status.
* Validation notes explaining how the result was checked against the working database.

Do not include passwords, API keys, access tokens, or other secrets in the evidence.
If a test fails, preserve an accurate record of the failure and its outcome. Do not mark a failed test as passed simply because the configuration was corrected afterward; rerun the test and record the successful execution separately.

continue

*Follow-up — what was lacking after the first prompt:* the MCP server could not be connected and smoke-tested yet, because the Claude Code session had to be reopened in the Homework 5 folder before it would load `.mcp.json`.

## Problem 5 — Build the agent team and grow the MCP tools

Problem 5 — Implement the Campus Customs Multi-Agent Team
1. Implement the five agents
Create one agent implementation file for each agent under `backend/` and one corresponding prompt file per agent under `backend/prompts/`.
Use the responsibilities I gave for every agent under Problem 1.
3. PydanticAI implementation and typed models
Use PydanticAI for all five agents.
Create `backend/models.py` for shared Pydantic models and typed inputs and outputs, including appropriate structures for:

* Ticket context and identifiers.
* Agent task requests and delegation results.
* Specialist findings and supporting evidence.
* Recommendations and proposed actions.
* Human approval requirements.
* Customer-message drafts.
* Agent execution results and workflow status.

Use the actual database fields and existing project conventions when defining data models. Avoid duplicating the database schema unnecessarily.
Where appropriate, use enums or constrained fields for workflow states, agent identifiers, and action types. Validate model outputs before passing them between agents.
Each agent should return structured results containing relevant findings, supporting record identifiers, recommended actions, blockers, and the next step.
Do not rely exclusively on free-text responses for critical workflow decisions.
4. Agent prompts
In each file that you created in step 1 of this problem:

* `backend/prompts/boss.md`
* `backend/prompts/inventory.md`
* `backend/prompts/accounting.md`
* `backend/prompts/facilities.md`
* `backend/prompts/customer_service.md`

define:

* The agent's role and responsibilities.
* The information it should request through MCP.
* Its permitted actions and limitations.
* The conditions under which it should delegate work or request assistance.
* Its required structured output.
* The business rules it must follow.
* The conditions under which it should stop and escalate to the Boss or human operator.

Prompts should be distinct and specific to each agent. Do not simply copy the same generic instructions into all five files.
Keep critical safeguards enforced in backend logic and MCP tools, not only in natural-language prompts.
5. Full agent connectivity and delegation
Implement actual programmatic delegation so that the agents can coordinate through a controlled workflow.
For example, a replenishment ticket may require:

1. The Boss assigns the ticket to Inventory.
2. Inventory retrieves stock and vendor information through MCP.
3. Inventory requests Accounting's assessment if an unpaid invoice or payment is relevant.
4. Accounting retrieves the necessary financial records through MCP and returns its findings.
5. Inventory combines those findings into a replenishment recommendation.
6. The Boss reviews the evidence and determines the next operational step.

This is an example workflow; use the actual tickets and records to determine which agents should collaborate.
Requirements:

* Each agent must have access only to the tools and delegation capabilities necessary for its responsibilities.
* Define explicit task inputs, structured results, and delegation rules.
* Prevent circular delegation, uncontrolled agent loops, repeated execution, and duplicate financial actions.
* Apply configurable limits on delegation depth, total agent calls, retries, and execution time.
* Record why a task was delegated and what result was returned.
* Escalate unresolved conflicts, missing information, and exhausted limits to the Boss or human operator.

Do not implement five disconnected agents that only describe what other agents should do. Delegation must actually invoke the relevant agent and return its result.
6. MCP tools and shop data
All shop facts must come through the existing MCP server backed by `data/campus_customs_new.db`.

* Reuse the three tools from Problem 3 and verify their current implementations.
* Identify the additional data access required by the five agents and the actual open tickets.
* Add only the additional MCP tools needed to support those requirements.
* Use verified database tables, fields, and relationships.
* Keep tools focused, typed, documented, and read-only unless a specific state-changing operation is explicitly required.
* Do not hardcode business records, stock levels, invoice values, or vendor details into agent prompts.
* Do not add direct database queries to agent implementations or create an alternative backend shop-data tool layer that bypasses MCP.

If an agent needs information that no existing MCP tool can provide, add the required capability to the MCP server and update its documentation.
8. Business safeguards
Apply the business rules established in Problem 1 and add 

explicit, configurable controls to keep model use predictable:

* Maximum agent calls per ticket.
* Maximum delegation depth.
* Maximum retries per failed operation.
* Maximum tool calls per agent run.
* Appropriate model request timeouts.
* Maximum lengths for ticket context and tool results.
* Concise specialist outputs and bounded audit payloads.
* Early stopping when a ticket is resolved, blocked, or requires human intervention.

Use model settings and usage tracking supported by the installed PydanticAI and Portkey versions. Do not invent unsupported configuration options.
When a limit is reached, stop safely, record the reason, and return a clear status rather than repeatedly invoking agents.

9. Persistent audit trail
Create `output/audit_trail.json` as a persistent, append-only audit log.
Record each meaningful agent-loop step, including:

* Timestamp.
* Run and ticket identifiers.
* Agent name.
* Step or event type.
* Task received and delegation reason, where applicable.
* MCP tool name and concise arguments.
* Tool outcome and relevant returned record identifiers.
* Structured findings and recommendation.
* Delegation target and result.
* Workflow state transition.
* Stop reason, retry, or error.
* Model identifier and Portkey trace identifier when available.

Record enough information to reconstruct the workflow without logging entire private conversations or unnecessary sensitive data.
Requirements:

* Append new events; never erase prior runs when starting another run.
* Use valid JSON and a consistent event schema.
* Prevent concurrent agent executions from corrupting the audit file.
* Preserve previous valid records if an execution fails.
* Do not log credentials, passwords, access tokens, or other secrets.
* Ensure failures are logged, not silently swallowed.

If appropriate, implement a reusable audit utility under `backend/` so every agent and orchestration step uses the same logging mechanism.
10. Update `output/harness.md`
Preserve the existing content and add or update the following sections. Include the safety guardrails defined in step 8.
For each of the five agents, document:

* Name and purpose.
* Implementation file.
* Prompt file.
* Responsibilities and limitations.
* Expected inputs and outputs.
* Delegation relationships.
* MCP tools it can use.

MCP tool reference
List every MCP tool currently implemented, including tools added in this problem.
For each tool, include:

* Exact registered tool name.
* Purpose and parameters.
* Tables and fields read or modified.
* Which tickets or agent workflows need it.
* Why the tool is appropriate.
* Whether it is read-only or state-changing.

12. Update `mcp/server/README.md`
Preserve the existing documentation and update the tool list to match the actual registered MCP tools after this problem.
For every tool, document its purpose, inputs, and database tables used. Explain which agents use it and whether it is read-only or state-changing.
Do not list tools that have not been implemented, and do not omit tools that are registered.

## Problem 6 — Plan the three tickets

Problem 6 
1. HTML page structure
Create `output/desk_tickets.html` as a self-contained HTML document that works when opened locally in a browser.
Include 5 tabs:

1. One tab for each of the three actual open tickets.
2. Cash.
3. Reflection.

Use the actual ticket identifiers or concise ticket descriptions as the first three tab labels.
The Cash, and Reflection tabs are placeholders for later problems. Leave them blank.
The tabs must work without requiring a backend, a running server, or an external JavaScript framework. Use simple embedded HTML, CSS, and JavaScript.
Make the page readable, visually organized, and easy to update after the agents have been run. Use a clear distinction between expected behavior and actual observed behavior.
2. Ticket tabs: expected section only
Each ticket tab must include the following sections.
A. Ticket summary

* Actual ticket identifier.
* Concise summary of the request.
* Relevant known facts from the database.
* Any important missing information or uncertainty.

B. Expected agent workflow
Write your own reasoned prediction of how the team should resolve the ticket.
Explain:

1. Who the Boss should call first and why. Identify the most appropriate first specialist based on the ticket's primary problem and explain the reasoning.
2. Expected delegations. List each delegation you expect, including the originating agent, receiving agent, purpose, and expected result.
3. Why each delegation is necessary. Explain how the receiving agent's findings help resolve the ticket.
4. Expected decision. Describe the likely recommendation or next step, based on the available facts. Do not claim certainty where the database does not provide enough information.
5. Expected blockers or human intervention. Identify any payment approvals, missing data, vendor restrictions, or other conditions that may prevent immediate completion.

Do not assign every ticket to every specialist. Delegate only when the ticket requires that agent's expertise or when the findings of another agent are necessary to proceed.
Do not present a proposed workflow as though it were an actual agent execution.
This text should be in the Expected section, in later problems we will add a section for Actual behavior.

## Problem 7 — Backend routes

Problem 7 — Build the FastAPI Backend
Build the backend for the Campus Customs multi-agent operations system:
1. Implement the FastAPI application
Create `backend/main.py`, use FastAPI and add routes to the following capabilities:
A. Retrieve the three tickets and their status
Create an endpoint that returns the three actual tickets identified in the earlier homework, including each ticket's ID and whether it is `open` or `resolved`.

* Read the tickets and their status from the appropriate source in the existing system.
* Do not hardcode ticket contents or invent ticket IDs.
* Ensure that a ticket's status reflects the actual persisted state of the system.
* Return a predictable JSON structure that the dashboard can render.

B. Run the agent team on a ticket
Create an endpoint that accepts a ticket ID and starts the existing Boss-led agent workflow for that ticket.

* Validate that the ticket exists and return an appropriate HTTP error for an invalid ID.
* Invoke the existing agent team and delegation workflow rather than implementing a separate workflow in the route.
* Preserve the Boss's responsibility for deciding which specialists to delegate to and why. Do not automatically call every specialist for every ticket.
* Use the existing Pydantic models and MCP tools.
* Keep agent execution bounded by the existing loop, delegation, tool-call, and timeout limits.
* Ensure that agent events are available while the workflow is running, so the dashboard can refresh and display progress.
* Prevent accidental duplicate runs for the same ticket if a run is already active, unless the official assignment explicitly requires another behavior.
* Return a run identifier and a clear status, such as `started`, so the front end can track the run.

Do not fabricate a successful result if an agent or tool fails. Record and expose the failure appropriately.
C. Retrieve recent agent events
Create an endpoint that returns recent agent activity for the dashboard.
Each event should include, where applicable:

* Timestamp and run ID.
* Ticket ID and agent name.
* Event type, such as agent started, delegation, tool call, finding, decision, error, or completion.
* A concise description of what the agent said or concluded.
* The MCP tool name and relevant arguments/results when a tool was used.
* The event's status or stop reason.

Use the existing append-only audit trail and/or a suitable in-memory event stream, depending on the architecture already implemented. Keep the source of events consistent with the existing audit system.
The dashboard must be able to refresh this endpoint during a run and see newly recorded events. If events are stored in memory, document the implications of restarting the server. Never expose API keys, passwords, secrets, or unnecessary sensitive information in event responses.
Support sensible filtering by ticket ID and/or run ID if appropriate. Avoid returning an unlimited event history in a single request.
D. Approve a payment or purchase
Create an endpoint that processes an explicit human approval for an existing payment or purchase proposal.
Critical financial safety requirements:

* Agents may prepare payment or purchase proposals, but must not execute payments themselves.
* A proposal must have a stable identifier and sufficient information to identify exactly what is being approved.
* The backend must verify that the proposal exists, is eligible for approval, and has not already been executed.
* Approval must be an explicit action submitted through this endpoint by a human; an agent recommendation or the Boss's decision is not human approval.
* Before executing a payment, independently verify the current checking balance and ensure sufficient cash is available.
* Never allow a payment to produce a negative checking balance.
* Record the approval, execution result, and resulting balance in the appropriate persistent records and audit trail.
* Reject duplicate approvals or executions safely.
* Return clear success or failure responses without claiming a payment was completed when it was not.

Keep the business logic in a dedicated function or service if needed, rather than putting all validation directly in the route.
Distinguish approving a purchase order from paying an invoice. Approving a purchase must not deduct cash unless the approved operation explicitly represents an actual payment. Follow the existing database model and the official assignment's expected behavior.
Do not send real payments, contact vendors, send emails, or make external purchases. All operations must remain within the assignment's local simulation.
E. Retrieve the current checking balance
Create an endpoint that returns the current checking balance from the relevant cash account records from cash_accounts.

* Read the current persisted balance; do not hardcode it.
* Use the actual schema and identify the correct checking account from the existing data.
* Ensure that approved payments are reflected in subsequent balance requests.
* Return a clear error if the account cannot be identified or the balance cannot be retrieved.

All shop facts must continue to flow through the existing MCP architecture where required by the assignment. Do not introduce a parallel agent-facing tool layer that bypasses MCP.
F. Reset the working database
Create an endpoint that resets the working database to its original baseline values so the three tickets can be tested repeatedly.

* Restore `data/campus_customs_new.db` from the verified original database or another reliable baseline mechanism.
* Never modify the original source database.
* Ensure the database is not being reset while a workflow or payment is actively executing. Reject the reset or handle it safely if work is in progress.
* Ensure database connections are properly closed or managed during reset.
* Clear or reset ticket status, payment execution state, and other simulated operational state as appropriate to the baseline.
* Preserve the append-only audit history in `output/audit_trail.json`; do not erase past runs. Record the reset as an event.
* Make the reset operation explicit and safe. Do not trigger it automatically when the server starts.

Return a clear response indicating whether the reset succeeded.

uvicorn main:app --reload --port 8000

*Follow-up — what was lacking after the first prompt:* the backend could not be started with the course's command (`uvicorn main:app --reload --port 8000` from `backend/`), because `main.py` only worked as a package import.

Update the existing `output/harness.md` without deleting or unnecessarily rewriting the documentation from previous problems.
Add a concise API reference with one line per route, specifying:

* HTTP method and URL.
* What the route does.
* Required inputs, if any.
* The main information or result it returns.

Also document how to start the backend, the relevant environment variables, how it connects to the existing agents and MCP server, and any important operational limitations.

*Follow-up — what was lacking after the first prompt:* `output/harness.md` did not yet have a one-line-per-route API reference, startup instructions, environment variables, or the backend's operational limits.

## Problem 8 — Agent dashboard

Problem 8 — Build the Campus Customs Operations Dashboard
Build a polished, creative, fully functional front-end dashboard for the Campus Customs multi-agent operations system using React, Vite, and TypeScript in the `frontend/` directory.
The dashboard is the human operator's desk: a person should be able to review the three tickets, launch the agent team, follow its work in real time, understand each agent's contribution, approve a payment or purchase when requested, and monitor the checking balance.
1. Visual concept and creative direction
Design a distinctive interface called Campus Customs — Operations Desk. It should feel like a premium, modern operations room at Yale: intelligent, calm, editorial, and welcoming, rather than a generic corporate admin dashboard.
Use Yale-inspired colors as the foundation:

* Deep Yale blue for the main navigation, key surfaces, and primary actions.
* Warm ivory or off-white for the workspace background.
* White or softly tinted panels to create clear content areas.
* Restrained red accents for alerts, overdue obligations, or important exceptions.
* Muted secondary colors for metadata, timestamps, and supporting information.

Use typography with personality: a refined editorial or serif style for selected headings paired with a highly legible sans-serif for operational data. Use strong hierarchy, thoughtful spacing, elegant borders, and carefully chosen iconography.
Make the page feel designed, not assembled from default components. Explore a distinctive composition with a ticket rail, a central active-work area, and an agent activity panel. Use responsive layouts, subtle transitions, and purposeful motion to communicate progress.
Avoid excessive gradients, excessive rounded cards, decorative clutter, oversized empty areas, and unnecessary animations. The design should remain easy to scan when several agents are active.
The interface must work on desktop first, while remaining usable on narrower screens.
2. Overall dashboard layout
Create a clear hierarchy with the following areas:
A. Header and navigation
Include:

* Campus Customs branding and an operations-desk title.
* A clear indicator that the system is connected to the local backend.
* A visible current checking balance.
* A compact overall operations status, such as agents idle, workflow running, or attention required.

Only show a connected status after a real backend request succeeds. If the backend is unavailable, display a clear disconnected or error state rather than pretending the system is online.
B. Ticket desk
Display all three actual tickets retrieved from `GET /tickets`.
Each ticket should have a visually distinct, compact ticket item showing the real ticket ID, a concise description, and its current status.
Use clear visual differences for:

* Open tickets.
* A ticket currently being processed.
* Resolved tickets.
* Tickets that are blocked or need human intervention, if that state is supported by the backend.

Selecting a ticket should open its workspace without losing track of the other tickets.
Provide an obvious primary action to start the agent team on the selected eligible ticket. Disable or adjust the action when a run is already active or the ticket is not eligible to run.
Show loading, success, and error feedback when starting a workflow. Use the actual run ID returned by the backend to track that run.
C. Active ticket workspace
When a ticket is selected, show its actual ID, description, status, and current run status.
Create a focused workspace where the user can understand the operational problem and follow the agent team's work.
Include:

* The selected ticket's real information.
* A clear indicator of the current workflow state.
* A short summary of the latest decision or next step, when one is available from the backend.
* A visible distinction between work in progress, completion, errors, and blockers.
* A concise summary of each agent's contribution once sufficient real events exist.

Do not invent a ticket description, recommendation, result, or resolution.
D. Live agent activity feed
Create a visually engaging activity feed that shows what each agent is doing as the workflow progresses.
Use the real events returned by `GET /events`. Refresh the feed periodically while a run is active, using the actual backend response format. Stop unnecessary polling when there is no active run, and handle temporary API failures gracefully.
Each event should display the information available from the backend, such as:

* Agent name and role.
* Event type or activity.
* A concise description of what the agent said, decided, or did.
* The MCP tool used, if applicable.
* A relevant finding or tool result.
* Timestamp.
* Status or stop reason, where available.

Make agent identities easy to distinguish visually. For example, use consistent iconography, initials, or subtle color accents for the Boss, Inventory, Accounting, Facilities, and Customer Service agents.
Differentiate events such as delegation, investigation, tool use, findings, recommendations, errors, and completion. The distinction must be based on actual event data, not guessed from arbitrary text.
The feed should make it possible to follow the workflow without reading long blocks of text. Allow longer details to be expanded when useful.
Display events in a consistent chronological order. Avoid duplicating events across refreshes, and handle missing optional fields gracefully.
E. Ticket resolution and agent summaries
When the agent run finishes, display a clear final state.

* Mark a ticket resolved only when the backend confirms that the ticket's persisted status is resolved.
* If the run finishes but the ticket remains open or blocked, display that actual state instead.
* Do not equate the end of an agent run with successful resolution.
* Show a short summary of what each agent actually contributed, based on recorded findings and events.
* Show the Boss's final operational recommendation and any outstanding action requiring a human, when available.

Preserve the completed ticket's activity and summaries when the user switches to another ticket, subject to the backend's event-retention behavior.
F. Human approval panel
Build a clear approval interface for a payment or purchase that requires human action.
Use the actual proposal or approval information provided by the backend. Show the available details, such as the proposal ID, vendor or recipient, amount, purpose, and operation type, only when those fields exist in the actual data.
The panel must:

* Explain what the human is being asked to approve.
* Distinguish a purchase-order approval from an actual payment.
* Provide explicit Approve and, if supported, Reject or Decline actions.
* Require a deliberate human action; never auto-approve.
* Show a confirmation step for consequential approvals.
* Display the result returned by the backend.
* Refresh the checking balance after a successful payment.
* Update the proposal's status to prevent the user from unknowingly submitting the same approval again.

A proposed payment must not be presented as completed before the backend confirms successful execution.
If approval fails because the balance is insufficient, the proposal is invalid, or the backend rejects the action, show the real error and keep the balance unchanged.
Do not add an approval button to every ticket indiscriminately. Show approval controls when an actual eligible proposal requires human attention.
G. Checking balance
Show the current checking balance prominently in the dashboard header or another persistent location.

* Fetch the balance from `GET /cash-balance`.
* Format the amount as currency, using the actual account currency and available account information.
* Refresh the balance after a successful payment, after a database reset, and when the dashboard reloads.
* If the balance changes, use a subtle transition or indicator to help the user notice.
* Never calculate a new balance solely in the front end or use a hardcoded initial amount.

The balance displayed must always reflect the backend's current persisted value, subject to normal request latency.
If useful, include a compact indicator for cash available or a recent payment, but do not invent transactions or financial metrics that the backend does not provide.
3. Connect the front end to the backend
Use the existing FastAPI backend at:
`http://localhost:8000`
Configure a single reusable API client or configuration constant rather than scattering the base URL throughout the code.
Use the actual routes and response formats implemented in Problem 7. Expected capabilities include:

* Retrieve ticket data and statuses.
* Start a workflow for a selected ticket.
* Retrieve recent events and run progress.
* Submit an explicit approval.
* Retrieve the current checking balance.

Use the exact routes and payloads found in the actual backend implementation. Do not assume the response structure without inspecting the code or testing the endpoint.
If the reset endpoint is exposed in the dashboard, make it a clearly separated, deliberate action with a confirmation step. Do not trigger a reset on page load or silently erase a test run.
CORS configuration
Update the FastAPI CORS configuration to allow the local Vite development origin:
`http://localhost:5173`
Allow only the origins and methods necessary for this local application. Do not use a wildcard origin with credentials.
The front end must make real HTTP requests to FastAPI. Do not bypass the backend and access the database directly.
Error and loading states
Implement user-friendly handling for:

* Backend unavailable or disconnected.
* Ticket loading.
* Starting a workflow.
* Active workflow with no events yet.
* Empty activity feed.
* Failed API requests.
* Invalid or unavailable approval proposals.
* Successful and rejected approvals.
* Missing or incomplete agent-event fields.

Show a useful message and a way to retry where appropriate. Avoid unhandled errors and infinite request loops.
4. React implementation and maintainability
Use React, Vite, and TypeScript in `frontend/`.
Structure the application into understandable components, for example:

* Header and checking-balance display.
* Ticket list.
* Active ticket workspace.
* Agent activity feed.
* Agent summary.
* Approval panel.
* Status indicators and reusable UI elements.

Keep API access, state management, and presentation reasonably separated. Define TypeScript interfaces for the actual API response shapes.
Ensure ticket selection, run state, activity events, ticket statuses, proposals, and checking balance remain consistent as the user interacts with the dashboard.
Do not introduce unnecessary dependencies. Reuse existing packages where practical and avoid a complete rewrite if a working front end already exists.
5. Design documentation
Create `output/design.md` describing the actual dashboard you implemented.
Include:

1. Design concept: the visual identity and the intended feeling of the Campus Customs Operations Desk.
2. Layout: how the header, ticket list, active workspace, activity feed, approvals, and balance fit together.
3. Color and typography: the palette, type hierarchy, and how they support the Yale-inspired identity.
4. Agent activity: how agents and different event types are distinguished and how live activity is presented.
5. Ticket states: how open, running, resolved, blocked, and error states are communicated, as applicable.
6. Cash and approvals: how the checking balance, approval requests, and successful payments are shown.
7. Interaction and accessibility: loading/error states, confirmation steps, responsive behavior, readable contrast, keyboard accessibility, and motion choices.
8. Creative decisions: the specific design choices that make this feel like a real, enjoyable desk for a human operator rather than a generic admin dashboard.

Document what is actually implemented, not features that are merely planned.

npm run dev

*Follow-up — what was lacking after the first prompt:* it was not clear how to start the dashboard myself with `npm run dev`, from which folder, and that the preview copy already running on port 5173 had to be stopped first.

## Problem 9 — Resolve the tickets

Problem 9 — Full End-to-End Run, Cash Reconciliation, and Evidence
2. Reset the working database and record the opening balance
Before running any tickets:
1. Use the system's reset functionality to restore data/campus_customs_new.db to its verified original baseline.
2. Confirm that the reset succeeded.
3. Verify that the three tickets are back in their expected initial state.
4. Query the working database's cash-account records and record the actual starting checking balance.
5. Record the timestamp of the reset, the opening balance, and the relevant account identifier in your run notes.
Never modify the original source database. Do not manually edit ticket statuses or cash balances to make the run easier.
If the reset fails or the initial state cannot be verified, stop and diagnose the issue before running the tickets.
The audit trail must remain append-only. Do not delete prior runs or clear output/audit_trail.json as part of the reset.

2. Run all three tickets through the React dashboard
Start the MCP server, backend, and front end using the project's documented commands. Confirm that the dashboard is connected to the actual backend.
Then open the React board in your browser and process the three tickets through the dashboard.
For each ticket:
1. Select the actual ticket in the board.
2. Start its agent workflow using the dashboard's normal run action.
3. Follow the real activity feed while the agents work.
4. Allow the Boss to delegate based on the ticket's needs. Do not force every specialist to work on every ticket.
5. When a payment or purchase requires human approval, review the actual proposal and make the approval decision through the dashboard. Never approve automatically or bypass the approval route.
6. Follow any necessary follow-up work until the ticket reaches its legitimate terminal state.
7. Confirm that the backend and working database show the ticket as resolved.
8. Capture a screenshot of the React board showing that ticket in its resolved state.
Repeat this process for all three tickets. Capture genuine screenshots from the browser; do not reconstruct the board in an image editor or create mock screenshots.
If a ticket cannot be resolved safely or legitimately, do not mark it resolved just to satisfy the requirement. Investigate the failure, document it, and make only the necessary fixes to the existing system before rerunning the affected workflow.
Record which run produced each outcome so that the evidence corresponds to the correct ticket and test.
4. Complete output/desk_tickets.html
Open the existing Problem 6 file and preserve its original structure and expected predictions.
A. Ticket tabs — actual versus expected
For each of the three ticket tabs, complete the **Actual** section using evidence from the real run.
Record:
- Actual starting state and final status.
- Which agents worked on the ticket.
- The order of delegations and which agent delegated to whom.
- The reason for each important delegation, where recorded.
- The actual MCP tools used, including the tool name, calling agent, and purpose.
- The important findings and decisions made by the agents.
- What each agent contributed to the outcome.
- Any human approval requested and the actual decision.
- The final outcome and any relevant operational or financial consequences.
Use the actual tool names registered in the MCP server. Distinguish a tool that was expected to be used from one that was actually called.
Keep the Expected section unchanged so the reader can compare your original predictions with the actual behavior.
If the actual workflow differed from the expected one, explain the difference briefly. Do not rewrite your original prediction to make the result look more accurate.

B. Cash tab — full reconciliation
Complete the Cash tab with an itemized reconciliation of the real transactions during this run.
Include:
- The verified starting checking balance immediately after reset.
- Each cash movement attributable to each ticket.
- The payment or purchase involved, its actual dollar amount, and the reason for the transaction.
- The relevant invoice, purchase-order, payment, or ticket identifier where available.
- The checking balance after each actual cash movement.
- The final checking balance after all three tickets have been processed.
Use a transaction ledger with clear columns, for example:
| Ticket | Transaction and reason | Cash outflow | Balance after transaction |
|---|---|---:|---:|
| Actual ticket ID | Actual transaction or no cash movement | Actual amount | Verified balance |
Add opening and closing balance rows. If a ticket causes no cash movement, explicitly record that fact and explain why rather than inventing a transaction.
Use the sign convention consistently. For example, show payments as positive outflow amounts in the outflow column and subtract them from the checking balance.
Reconcile the arithmetic:
**Ending checking balance = starting checking balance − total actual cash outflows**
Verify the opening balance, transaction amounts, and ending balance against the persisted cash-account records. Check relevant payment and invoice records as well. Do not rely only on the dashboard's displayed balance.
If the displayed balance and the database disagree, investigate and report the discrepancy. Do not change the figures in the report to make the arithmetic appear correct.
5. Create output/resolved_tickets.json
Create a valid JSON file containing one record for each of the three actual tickets.
Use a consistent structure such as:
- `ticket_id`: the real ticket ID.
- `final_status`: the status verified after the run.
- `short_outcome`: a concise explanation of what actually happened.
- `agents`: a list of agents that actually contributed, with each agent's name, role, and short description of its contribution.
- `delegations`: the actual important delegations, where available.
- `tools_used`: the actual MCP tool names used for this ticket.
- `human_approvals`: the actual approval requests and decisions, including proposal identifiers and amounts when applicable.
- `cash_impact`: actual cash outflows attributable to this ticket, or zero when there was no cash movement.
- `run_id`: the identifier for the run, if available.
Adapt field names as needed to fit the actual implementation, but keep the schema consistent across all three records.
Requirements:
- Use actual data from the run, agent events, approval records, and persisted database.
- Include all three tickets, not just the first successful one.
- Do not report an approval unless a human actually made that decision.
- Do not claim that a purchase was paid for unless the payment was actually executed and persisted.
- Ensure the final status agrees with the backend and database.
- Validate that the file is syntactically valid JSON.
If a required fact was not captured by the existing system, state that it is unavailable rather than inventing it.
6. Create output/resolved_board.html
Create a standalone HTML page that can be opened by double-clicking the file.
It must contain genuine screenshots of the React dashboard showing each of the three tickets in its resolved state.
Requirements:
- Include one clearly labeled section for each actual ticket ID.
- Embed the real screenshots or reference image files using reliable relative paths that work when the page is opened locally.
- Include a short caption explaining what the screenshot demonstrates.
- Make the page easy to navigate and grade, with a clear title, consistent layout, and readable image sizes.
- Confirm that every image loads when the HTML file is opened from its actual output location.
Capture the screenshots from the running React application after the corresponding ticket has actually resolved. 
7. Append the real runs to output/audit_trail.json
Preserve the existing audit history and append the events generated during the Problem 9 runs.
The audit trail must reflect the actual execution, including relevant events such as:
- Database reset and verified initial state.
- Ticket run starts and run identifiers.
- Agent starts, delegations, findings, and decisions.
- MCP tool calls and their actual outcomes.
- Approval requests and human decisions.
- Payment execution results and cash changes.
- Ticket resolution, blockers, errors, and stop reasons.
Retain timestamps and useful identifiers so that events can be associated with the correct ticket and run.
Do not fabricate missing events or backfill a false sequence after the fact. If the current audit implementation does not capture an important event, make the smallest appropriate fix, then run the affected workflow again to capture genuine evidence.
Never log API keys, passwords, or other secrets. Keep the audit trail valid and readable according to its existing format.
**8. Update output/harness.md**
Update the existing file into a coherent description of the complete system. Preserve useful material from earlier problems and correct any outdated descriptions.
Ensure it covers:
Database
- Original and working database locations.
- Tables, important fields, primary and foreign keys, and relationships.
- Relevant ticket, vendor, invoice, purchase-order, payment, and cash-account records.
- How the working database is reset.

MCP server
- How the MCP server is started and connected.
- Every actual registered tool, its parameters, purpose, and the tables or fields it accesses.
- Which agents use each tool.
- Which tools read data and which can change state.

Five agents
- Boss, Inventory Manager, Accounting Manager, Facilities Manager, and Customer Service Manager.
- Each agent's responsibility, prompt, tools, and delegation relationships.
- How the Boss chooses which specialists to involve.
- How the team handles errors, incomplete information, and blocked tickets.

Backend API
- Every implemented route, its HTTP method and URL, what it does, and the important request/response fields.
- How the backend starts.
- How the front end connects to it.
- How ticket runs and recent events are exposed.

Dashboard
- How to start the React/Vite front end.
- The dashboard's major features and design.
- How it displays ticket status, agent activity, human approval requests, and the checking balance.
- How the front end refreshes events and balance information.

Safety and financial controls
- Human approval requirements.
- How the backend validates and executes payments.
- The insufficient-cash guard and protection against duplicate execution.
- The prohibition on agents executing payments directly.
- The append-only audit trail.
- Agent-loop, delegation, tool-call, and timeout limits.
- Restrictions on real-world purchases, payments, vendor contact, and customer communications.

Problem 9 test results
- The three tickets tested and their actual final statuses.
- The verified starting and ending checking balances.
- Actual cash movements and how they reconcile to the database.
- Any failures, fixes, or remaining limitations.

Document the implementation that actually exists, not an intended future design.

## Problem 10 — Reflection

Problem 10
Open the existing `output/desk_tickets.html` file from Problem 6 and complete its Reflection tab.
Write in a natural, thoughtful, personal voice, as if I were reflecting on the project and what I learned from building and testing it. Be detailed and thorough, but not repetitive or artificially academic. Use concrete examples from Campus Customs.
If evidence is missing or inconsistent, identify the limitation instead of inventing facts. If a ticket did not actually resolve, describe what happened honestly rather than claiming success.
1. Evaluate the performance of the agents on each ticket
Create a separate, clearly labeled subsection for each of the three actual tickets.
For each ticket, answer all of the following:
A. How well did the agents perform, and why?
Evaluate the quality of the actual workflow, not just the final status.
Discuss:

* Whether the Boss identified the right first specialist and delegated to the appropriate agents.
* Whether each specialist contributed information that was relevant to the ticket.
* Whether the team used the available MCP tools effectively and obtained the information needed to make its decisions.
* Whether agents coordinated well, or whether there were unnecessary delegations, repeated investigations, redundant tool calls, or missed opportunities to simplify the process.
* Whether the team identified the relevant financial, inventory, facilities, or customer-service constraints.
* Whether the final decision was supported by the facts available in the database.
* Whether the human approval process and financial safety rules were followed correctly, if relevant.
* What the team did particularly well and what could have been better.

Name the actual agents and tools involved wherever the evidence supports doing so. Explain why their actions helped or did not help resolve that specific ticket.
Do not assume every agent should be involved. A smaller, well-targeted workflow may be better than sending every ticket to all five agents.
B. Compare the actual workflow with the original Expected plan
Use the Expected and Actual sections already recorded in that ticket's tab.
Explain:

* Which parts of the expected delegation sequence were correct.
* Which agents or tools were used as predicted.
* What happened differently from the original plan.
* Whether the actual approach was more efficient, less efficient, or simply different.
* Whether the difference improved the outcome or introduced unnecessary complexity.
* What the actual run taught us about how the Boss should delegate this type of work in the future.

Make this comparison specific to the ticket. Do not repeat a generic explanation of how the system works.
If the original plan predicted that a specialist would be called first but the actual workflow started elsewhere, explain the difference and whether the actual choice made sense in light of the ticket's facts.
C. Overall judgment for this ticket
Conclude with a clear evaluation of the ticket's performance.
Explain whether the workflow was effective, whether the final result was adequately supported by the evidence, and the most important improvement you would make to this ticket's workflow.
If the ticket required a payment, explicitly distinguish the agent's recommendation, the human's approval, and the actual execution of the payment. Use the Cash tab and database evidence when discussing financial outcomes.
2. What would have been simpler as one agent with tools, and why?
Add a separate subsection comparing the multi-agent design with a simpler single-agent architecture.
Use the three actual ticket runs to identify which work could reasonably have been completed by one capable operations agent equipped with the existing MCP tools.
For each example, explain:

* Which ticket or part of the workflow you are referring to.
* Which agents were involved in the actual run.
* Whether those agents performed genuinely distinct work or mostly passed information between one another.
* How a single agent could have completed the same work with fewer handoffs.
* Whether the single-agent approach would likely have been faster, easier to audit, or less complex.
* What might be lost by combining the work into one agent.

Consider whether straightforward record lookup, gathering related facts, checking a known status, or preparing a simple summary really requires several specialist agents. Contrast this with situations where separate accounting, inventory, facilities, or customer-service expertise adds real value.
Do not automatically conclude that a single agent is better. Use the actual ticket evidence to identify where multi-agent delegation provided meaningful specialization and where it added overhead.
End this section with a clear conclusion about what the Campus Customs system should delegate to specialists and what could be handled by a single agent.
3. Three new Campus Customs problems the existing team could solve
Describe three realistic new operational problems that Campus Customs might face and that the current agent team could reasonably help solve with the tools already built.
For each proposed problem, include:

1. The situation: A specific, believable Campus Customs scenario.
2. The connection to the existing tickets: Explain how it resembles or extends an issue observed in one or more of the three actual tickets.
3. The workflow: Explain which agent should take the lead, which specialists should be delegated to, and why.
4. Existing tools: Name the actual MCP tools that could support the work and identify the relevant data they expose.
5. Expected outcome: Explain what the team could determine, recommend, prepare, or safely execute under the existing system.
6. Limitations: Identify any remaining need for human judgment or approval.

Choose three meaningfully different scenarios, not three variations of the same problem. Possible categories to consider include stock shortages, outstanding invoices or cash constraints, vendor-related purchasing decisions, facilities obligations, and customer-service issues—but select scenarios that genuinely fit the tools and data that exist.
Be precise about what the current implementation can do. For example, an agent that can inspect inventory and prepare a purchasing recommendation cannot be described as having placed a real vendor order if the system has no such capability.
Do not invent MCP tools or database fields. If a tool only provides read access, do not claim that it can change the relevant records.
4. Three new Campus Customs problems the existing team could NOT solve with its current tools
Describe three additional, realistic Campus Customs problems that the current system cannot fully solve because it lacks the necessary data, integrations, tools, permissions, or agent capabilities.
For each problem, explain all of the following:
A. The new problem
Describe a concrete business situation and why the current system cannot resolve it end to end.
Explicitly identify the missing capability. Distinguish between a task that the agents could partially investigate and one that they could actually complete.
B. What is missing
Identify the exact gap in the existing system. Examples might include missing live supplier information, lack of sales forecasting data, lack of a real order-management integration, lack of shipping tracking, or inability to communicate with customers. Use only examples that are genuinely absent from the current implementation.
Verify the actual MCP tool list, database schema, and agent capabilities before claiming something is missing.
C. What new tools and agents would be needed
Propose the minimum practical extension to the existing system. Explain:

* Which new MCP tools or external integrations would be required.
* What data the tools would retrieve or change.
* Which existing agent should own the task.
* Whether a new specialist agent is justified and, if so, its responsibilities.
* How the new agent would coordinate with the Boss and existing specialists.
* What validation, permissions, and human approval would be needed before any consequential action.

For example, if the system cannot track a supplier shipment, explain the supplier or carrier integration and shipment-status tool that would be needed. If a new forecasting agent is proposed, explain what historical sales, inventory, or seasonal data it would require and why the existing tools are insufficient.
These should be genuine capability gaps, not simply problems the current agents could already solve with their existing database access and MCP tools.
D. Connection to the three actual tickets
For every proposed problem, explain how it connects to something learned from the three tickets that were actually run. Identify the operational lesson that suggests the business could face this new problem, without claiming that an event occurred if it did not.
The point is to demonstrate that you understand the boundary between the capabilities built for this assignment and the capabilities a more advanced Campus Customs operations system would need.
5. Use the Cash tab as evidence
Use the Cash tab to support the financial aspects of the reflection wherever relevant.
In particular:

* Refer to actual payments, purchase decisions, cash outflows, or the absence of cash movement.
* Explain how financial constraints affected the decisions the agents made.
* Evaluate whether the human approval process was appropriate and correctly enforced.
* Identify any unnecessary steps or missing checks revealed by the actual runs.
* Explain how the current team could handle a similar future cash or invoice problem.
* Identify what additional tools or data would be necessary for a more complex financial scenario.

All amounts and payment claims must agree with the Cash tab and the persisted database. Do not invent financial details or infer a cash movement merely because a purchase was discussed.
