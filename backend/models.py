"""Shared typed models for the Campus Customs multi-agent team.

Agents exchange these models, never free text, for anything the workflow acts
on. Shop facts are not copied into new tables here: evidence points back to
database rows with RecordRef, and the values themselves come from MCP tools.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AgentName(str, Enum):
    BOSS = "boss"
    INVENTORY = "inventory"
    ACCOUNTING = "accounting"
    FACILITIES = "facilities"
    CUSTOMER_SERVICE = "customer_service"


SPECIALISTS = (AgentName.INVENTORY, AgentName.ACCOUNTING,
               AgentName.FACILITIES, AgentName.CUSTOMER_SERVICE)


class WorkflowStatus(str, Enum):
    """Where a ticket stands. The backend, not the Boss, sets the final value."""
    RECEIVED = "received"
    IN_PROGRESS = "in_progress"
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    BLOCKED = "blocked"
    NEEDS_CLARIFICATION = "needs_clarification"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    LIMIT_REACHED = "limit_reached"
    FAILED = "failed"


BOSS_STATUSES = (WorkflowStatus.AWAITING_HUMAN_APPROVAL, WorkflowStatus.BLOCKED,
                 WorkflowStatus.NEEDS_CLARIFICATION, WorkflowStatus.ESCALATED,
                 WorkflowStatus.RESOLVED)


class TaskOutcome(str, Enum):
    """How a specialist's task ended."""
    COMPLETED = "completed"
    BLOCKED = "blocked"
    NEEDS_INFORMATION = "needs_information"
    ESCALATE = "escalate"


class Urgency(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class DbTable(str, Enum):
    TICKETS = "tickets"
    INVENTORY = "inventory"
    PRICING = "pricing"
    VENDORS = "vendors"
    INVOICES = "invoices"
    LEASES = "leases"
    CASH_ACCOUNTS = "cash_accounts"
    PAYMENTS = "payments"
    DESK = "desk"


class ActionType(str, Enum):
    PAY_INVOICE = "pay_invoice"
    PAY_RENT = "pay_rent"
    DRAFT_PURCHASE_ORDER = "draft_purchase_order"
    OFFER_DISCOUNT = "offer_discount"
    CUSTOMER_MESSAGE_DRAFT = "customer_message_draft"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    REQUEST_INFORMATION = "request_information"
    NO_ACTION = "no_action"


PAYMENT_ACTIONS = frozenset({ActionType.PAY_INVOICE, ActionType.PAY_RENT})
APPROVAL_REQUIRED_ACTIONS = frozenset({
    ActionType.PAY_INVOICE, ActionType.PAY_RENT, ActionType.DRAFT_PURCHASE_ORDER,
    ActionType.OFFER_DISCOUNT, ActionType.CUSTOMER_MESSAGE_DRAFT,
})


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    NEEDS_HUMAN_APPROVAL = "needs_human_approval"
    BLOCKED = "blocked"


# --- Evidence -----------------------------------------------------------------

class RecordRef(BaseModel):
    """A database row the agent saw in an MCP tool result during this run."""
    table: DbTable
    id: str = Field(
        max_length=60,
        description=(
            "Row identifier as text: tickets/vendors/invoices/leases/payments use their "
            "numeric id (e.g. '7'); inventory uses 'SKU:SIZE'; pricing uses the SKU; "
            "cash_accounts uses the account name; desk uses 'date_today'."
        ),
    )

    def key(self) -> tuple[str, str]:
        return (self.table.value, self.id)


class Evidence(BaseModel):
    record: RecordRef
    fact: str = Field(max_length=240, description="The value read from that record, stated plainly.")


class Finding(BaseModel):
    summary: str = Field(max_length=300)
    evidence: list[Evidence] = Field(default_factory=list, max_length=5)


# --- Actions and approvals ----------------------------------------------------

class ProposedAction(BaseModel):
    """Something an agent recommends. Nothing here is ever executed by an agent."""
    action_type: ActionType
    description: str = Field(max_length=300)
    target: RecordRef | None = Field(
        default=None,
        description="Record the action is about: the invoice or lease to pay, the vendor "
                    "for a purchase order, the pricing SKU for a discount, the ticket for a message.",
    )
    amount: float | None = Field(default=None, ge=0, description="Dollar amount, if any.")
    payee: str | None = Field(default=None, max_length=100)
    sku: str | None = Field(default=None, max_length=40)
    size: str | None = Field(default=None, max_length=10)
    quantity: int | None = Field(default=None, ge=1)
    discount_pct: float | None = Field(default=None, gt=0, lt=100,
                                       description="Discount off list price, for offer_discount.")
    requires_human_approval: bool = True
    status: ActionStatus = ActionStatus.PROPOSED
    blocked_reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _check_shape(self) -> ProposedAction:
        if self.action_type in PAYMENT_ACTIONS:
            missing = [n for n in ("target", "amount", "payee") if getattr(self, n) is None]
            if missing:
                raise ValueError(f"{self.action_type.value} needs {', '.join(missing)}")
            expected = (DbTable.INVOICES if self.action_type is ActionType.PAY_INVOICE
                        else DbTable.LEASES)
            if self.target.table is not expected:
                raise ValueError(f"{self.action_type.value} must target a row in {expected.value}")
        if self.action_type is ActionType.DRAFT_PURCHASE_ORDER:
            if self.target is None or self.target.table is not DbTable.VENDORS:
                raise ValueError("draft_purchase_order must target a row in vendors")
            if self.sku is None or self.quantity is None:
                raise ValueError("draft_purchase_order needs sku and quantity")
        if self.action_type is ActionType.OFFER_DISCOUNT:
            if self.target is None or self.target.table is not DbTable.PRICING:
                raise ValueError("offer_discount must target a row in pricing")
            if self.discount_pct is None:
                raise ValueError("offer_discount needs discount_pct")
        # An agent cannot waive approval: these action types always need a human.
        if self.action_type in APPROVAL_REQUIRED_ACTIONS:
            self.requires_human_approval = True
        return self

    def dedupe_key(self) -> tuple:
        target = self.target.key() if self.target else None
        return (self.action_type.value, target, self.sku, self.size)


class ApprovalRequirement(BaseModel):
    """A human sign-off the operator still owes. Derived by the backend from actions."""
    action_type: ActionType
    description: str
    target: RecordRef | None = None
    amount: float | None = None
    payee: str | None = None
    status: ActionStatus
    blocked_reason: str | None = None
    approver: Literal["human operator"] = "human operator"


class CustomerMessageDraft(BaseModel):
    """A message for a human to review. The system has no way to send it."""
    to: str = Field(max_length=120)
    subject: str = Field(max_length=150)
    body: str = Field(max_length=2500)
    open_questions: list[str] = Field(default_factory=list, max_length=4,
                                      description="Points a human must confirm before sending.")
    is_draft: Literal[True] = True


# --- Tasks and results ----------------------------------------------------------

class TicketContext(BaseModel):
    """A ticket as returned by the get_ticket_details MCP tool."""
    ticket_id: int
    type: str
    requester: str
    subject: str
    sku: str | None = None
    size: str | None = None
    qty: int | None = None
    lease_id: int | None = None
    invoice_id: int | None = None
    status: str
    notes: str | None = None
    created_at: str


class TaskRequest(BaseModel):
    """What an agent is asked to do. Built by the backend, sent as the agent's prompt."""
    ticket: TicketContext
    shop_date: str
    requested_by: Literal["operator", "boss", "inventory", "accounting", "facilities",
                          "customer_service"]
    task: str = Field(max_length=600)
    reason: str = Field(max_length=300)
    context_from_caller: str = Field(default="", description="Findings the caller already has.")


class SpecialistReport(BaseModel):
    """The structured result every specialist returns."""
    outcome: TaskOutcome
    summary: str = Field(max_length=400)
    findings: list[Finding] = Field(default_factory=list, max_length=6)
    recommended_actions: list[ProposedAction] = Field(default_factory=list, max_length=4)
    blockers: list[str] = Field(default_factory=list, max_length=5)
    next_step: str = Field(max_length=300)
    escalation_reason: str | None = Field(default=None, max_length=300)

    def record_ids(self) -> list[str]:
        refs = {f"{e.record.table.value}:{e.record.id}" for f in self.findings for e in f.evidence}
        refs |= {f"{a.target.table.value}:{a.target.id}" for a in self.recommended_actions if a.target}
        return sorted(refs)


class CustomerServiceReport(SpecialistReport):
    draft: CustomerMessageDraft | None = None


class DelegationResult(BaseModel):
    """What a delegating agent gets back. `refused` means the target never ran."""
    target: AgentName
    task: str
    reason: str
    status: Literal["completed", "cached", "refused", "failed"]
    report: CustomerServiceReport | SpecialistReport | None = None
    consulted: list[str] = Field(default_factory=list,
                                 description="Specialists the target itself asked, with their answers.")
    error: str | None = None


class BossDecision(BaseModel):
    """The Boss's final, structured decision for one ticket."""
    ticket_id: int
    problem: str = Field(max_length=300)
    urgency: Urgency
    expected_outcome: str = Field(max_length=300)
    assigned_agents: list[AgentName] = Field(max_length=4)
    decision: str = Field(max_length=500)
    proposed_status: WorkflowStatus = Field(
        description="One of awaiting_human_approval, blocked, needs_clarification, escalated, resolved.")
    actions: list[ProposedAction] = Field(default_factory=list, max_length=6)
    blockers: list[str] = Field(default_factory=list, max_length=6)
    outstanding_items: list[str] = Field(default_factory=list, max_length=6)
    conflicts_resolved: list[str] = Field(default_factory=list, max_length=4)
    evidence: list[Evidence] = Field(default_factory=list, max_length=8)
    operator_summary: str = Field(max_length=900)
    next_step: str = Field(max_length=300)

    @model_validator(mode="after")
    def _check_status(self) -> BossDecision:
        if self.proposed_status not in BOSS_STATUSES:
            raise ValueError("proposed_status must be one of "
                             + ", ".join(s.value for s in BOSS_STATUSES))
        if AgentName.BOSS in self.assigned_agents:
            raise ValueError("assigned_agents lists specialists only")
        return self

    def record_ids(self) -> list[str]:
        refs = {f"{e.record.table.value}:{e.record.id}" for e in self.evidence}
        refs |= {f"{a.target.table.value}:{a.target.id}" for a in self.actions if a.target}
        return sorted(refs)


AgentOutput = BossDecision | CustomerServiceReport | SpecialistReport


class SpecialistResult(BaseModel):
    agent: AgentName
    requested_by: str
    task: str
    report: CustomerServiceReport | SpecialistReport


class AgentRunSummary(BaseModel):
    agent: AgentName
    depth: int
    requested_by: str
    task: str
    outcome: str
    duration_s: float
    model: str | None = None
    portkey_trace_id: str
    requests: int = 0
    tool_calls: int = 0
    total_tokens: int = 0


class UsageTotals(BaseModel):
    requests: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class TicketRunResult(BaseModel):
    """Everything the operator (and later the dashboard) needs about one ticket run."""
    run_id: str
    ticket_id: int
    status: WorkflowStatus
    stop_reason: str | None = None
    decision: BossDecision | None = None
    approvals_required: list[ApprovalRequirement] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    customer_drafts: list[CustomerMessageDraft] = Field(default_factory=list)
    specialist_reports: list[SpecialistResult] = Field(default_factory=list)
    agent_runs: list[AgentRunSummary] = Field(default_factory=list)
    recorded_proposals: dict | None = Field(
        default=None, description="What record_run_outcome stored: proposal ids created, kept, "
                                  "superseded or skipped, and whether the ticket was resolved.")
    recording_error: str | None = None
    usage: UsageTotals = Field(default_factory=UsageTotals)
    started_at: datetime
    finished_at: datetime | None = None
