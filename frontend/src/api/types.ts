// Response shapes of the FastAPI backend (backend/main.py, backend/service.py,
// backend/models.py, mcp_server/operations.py). Run results are serialised with
// exclude_none, so optional fields may be absent.

export type AgentId =
  | "boss"
  | "inventory"
  | "accounting"
  | "facilities"
  | "customer_service";

export type WorkflowStatus =
  | "received"
  | "in_progress"
  | "awaiting_human_approval"
  | "blocked"
  | "needs_clarification"
  | "escalated"
  | "resolved"
  | "limit_reached"
  | "failed";

export interface HealthResponse {
  ok: boolean;
  model: string;
  database: string;
  active_runs: Record<string, string>;
}

/** GET /api/runs and the `active_run` field of a ticket. */
export interface RunSummary {
  run_id: string;
  ticket_id: number;
  state: "running" | "completed" | "failed";
  started_at: string;
  finished_at: string | null;
  workflow_status: WorkflowStatus | null;
  stop_reason: string | null;
  error: string | null;
}

/** GET /api/runs/{run_id} */
export interface RunDetail extends RunSummary {
  result?: TicketRunResult;
}

/** `latest_run` of a ticket: the last run recorded in the database. */
export interface LatestRun {
  ticket_id: number;
  run_id: string;
  run_status: WorkflowStatus;
  recorded_at: string;
}

export interface Ticket {
  ticket_id: number;
  type: string;
  requester: string;
  subject: string;
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  status: string; // persisted tickets.status: "open" | "resolved"
  created_at: string;
  latest_run: LatestRun | null;
  active_run: RunSummary | null;
}

export interface TicketsResponse {
  shop_date: string;
  count: number;
  tickets: Ticket[];
}

/** GET /api/tickets/{id} — the MCP get_ticket_details result. */
export interface TicketDetail {
  found: true;
  shop_date: string;
  database: {
    ticket: {
      ticket_id: number;
      type: string;
      requester: string;
      subject: string;
      sku: string | null;
      size: string | null;
      qty: number | null;
      lease_id: number | null;
      invoice_id: number | null;
      status: string;
      notes: string | null;
      created_at: string;
    };
    linked_records: {
      product?: {
        sku: string;
        size: string | null;
        sku_exists: boolean;
        product_name: string | null;
        inventory_row_exists: boolean;
      };
      lease?: { id: number; space_name?: string; landlord?: string; exists?: boolean };
      invoice?: {
        id: number;
        vendor_id?: number;
        vendor_name?: string | null;
        status?: string;
        exists?: boolean;
      };
    };
  };
  notes: string[];
}

export interface StartRunResponse {
  ok: true;
  status: "started";
  run_id: string;
  ticket_id: number;
  run_url: string;
  events_url: string;
}

export type EventCategory =
  | "run"
  | "status"
  | "agent_started"
  | "finding"
  | "error"
  | "tool_call"
  | "delegation"
  | "guardrail"
  | "completion"
  | "approval"
  | "reset"
  | "other";

export interface EventTool {
  name: string;
  args: Record<string, unknown> | null;
  outcome: string | null;
  record_ids: string[] | null;
}

/** One event from GET /api/events (service.dashboard_event). */
export interface DashboardEvent {
  event_id: string;
  timestamp: string;
  run_id: string;
  ticket_id: number | null;
  agent: string | null;
  depth: number | null;
  event_type: string;
  category: EventCategory | string;
  description: string;
  delegation_target: string | null;
  tool: EventTool | null;
  findings: unknown;
  recommendation: unknown;
  status: string | null;
  stop_reason: string | null;
  error: string | null;
  model: string | null;
  portkey_trace_id: string | null;
}

export interface EventsResponse {
  count: number;
  total_matching: number;
  next_after: string | null;
  events: DashboardEvent[];
}

export type ProposalKind = "pay_invoice" | "pay_rent" | "purchase_order" | "offer_discount";
export type ProposalStatus = "pending" | "executed" | "approved" | "declined" | "superseded";

/** One row of action_proposals (GET /api/proposals). */
export interface Proposal {
  id: number;
  run_id: string;
  ticket_id: number;
  kind: ProposalKind;
  ref_table: string;
  ref_id: number;
  amount: number;
  payee: string;
  sku: string | null;
  size: string | null;
  quantity: number | null;
  discount_pct: number | null;
  description: string;
  blocked_reason: string | null;
  status: ProposalStatus;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  payment_id: number | null;
  balance_after: number | null;
  result: string | null;
}

export interface ProposalsResponse {
  proposals: Proposal[];
}

export interface ApprovalRequest {
  approved_by: string;
  confirm_amount: number;
  confirm_payee: string;
}

/** Successful POST /api/proposals/{id}/approve. */
export interface ApprovalResult {
  ok: true;
  outcome: "executed" | "approved";
  proposal_id: number;
  ticket_id: number;
  run_id: string;
  kind: ProposalKind;
  ref_table: string;
  ref_id: number;
  amount: number;
  payee: string;
  approved_by: string;
  payment_id: number | null;
  balance_before: number;
  balance_after: number;
  message: string;
  resolved_ticket_ids: number[];
}

/** Successful POST /api/proposals/{id}/decline. */
export interface DeclineResult {
  ok: true;
  outcome: "declined";
  proposal_id: number;
  ticket_id: number;
  run_id: string;
  kind: ProposalKind;
  amount: number;
  payee: string;
  declined_by: string;
  message: string;
  resolved_ticket_ids: number[];
}

/** GET /api/cash/checking */
export interface Balance {
  account: string;
  balance: number;
  currency: string;
  balance_date: string;
  shop_date: string;
}

/** POST /api/reset */
export interface ResetResult {
  ok: true;
  restored_from: string;
  working_db: string;
  original_sha256_unchanged: string;
  integrity: string;
  row_counts: Record<string, number>;
  checking_balance: number;
  ticket_status: Record<string, string>;
  open_invoices: number[];
}

/** Error body produced by the backend's ServiceError handler. */
export interface ApiErrorBody {
  ok: false;
  error: string;
  message: string;
  [extra: string]: unknown;
}

// --- Run result (backend/models.py TicketRunResult) -------------------------

export interface RecordRef {
  table: string;
  id: string;
}

export interface Evidence {
  record: RecordRef;
  fact: string;
}

export interface Finding {
  summary: string;
  evidence?: Evidence[];
}

export interface ProposedAction {
  action_type: string;
  description: string;
  target?: RecordRef;
  amount?: number;
  payee?: string;
  sku?: string;
  size?: string;
  quantity?: number;
  discount_pct?: number;
  requires_human_approval?: boolean;
  status?: "proposed" | "needs_human_approval" | "blocked";
  blocked_reason?: string;
}

export interface CustomerMessageDraft {
  to: string;
  subject: string;
  body: string;
  open_questions?: string[];
  is_draft: true;
}

export interface SpecialistReport {
  outcome: "completed" | "blocked" | "needs_information" | "escalate";
  summary: string;
  findings?: Finding[];
  recommended_actions?: ProposedAction[];
  blockers?: string[];
  next_step: string;
  escalation_reason?: string;
  draft?: CustomerMessageDraft;
}

export interface SpecialistResult {
  agent: AgentId;
  requested_by: string;
  task: string;
  report: SpecialistReport;
}

export interface BossDecision {
  ticket_id: number;
  problem: string;
  urgency: string;
  expected_outcome: string;
  assigned_agents: AgentId[];
  decision: string;
  proposed_status: WorkflowStatus;
  actions?: ProposedAction[];
  blockers?: string[];
  outstanding_items?: string[];
  conflicts_resolved?: string[];
  evidence?: Evidence[];
  operator_summary: string;
  next_step: string;
}

export interface ApprovalRequirement {
  action_type: string;
  description: string;
  target?: RecordRef;
  amount?: number;
  payee?: string;
  status: string;
  blocked_reason?: string;
  approver: string;
}

export interface AgentRunSummary {
  agent: AgentId;
  depth: number;
  requested_by: string;
  task: string;
  outcome: string;
  duration_s: number;
  model?: string;
  portkey_trace_id: string;
  requests?: number;
  tool_calls?: number;
  total_tokens?: number;
}

export interface TicketRunResult {
  run_id: string;
  ticket_id: number;
  status: WorkflowStatus;
  stop_reason?: string;
  decision?: BossDecision;
  approvals_required?: ApprovalRequirement[];
  blockers?: string[];
  customer_drafts?: CustomerMessageDraft[];
  specialist_reports?: SpecialistResult[];
  agent_runs?: AgentRunSummary[];
  recorded_proposals?: Record<string, unknown>;
  recording_error?: string;
  usage?: { requests: number; tool_calls: number; input_tokens: number; output_tokens: number };
  started_at: string;
  finished_at?: string;
}
