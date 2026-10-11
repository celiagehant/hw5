import { useState } from "react";
import { ApiError } from "../api/client";
import type { ApprovalResult, Balance, DeclineResult, Proposal, ProposalKind } from "../api/types";
import { humanize, money, time } from "../lib/format";
import type { Connection } from "../state/useDesk";
import { Icon, type IconName } from "./Icon";
import { Notice, Pill, SectionTitle, Spinner } from "./ui";

const APPROVER_KEY = "campus-customs.approver";

interface KindInfo {
  label: string;
  /** Approving moves cash out of checking. */
  isPayment: boolean;
  target: string;
  icon: IconName;
  approveLabel: string;
}

const KIND: Record<ProposalKind, KindInfo> = {
  pay_invoice: { label: "Payment · vendor invoice", isPayment: true, target: "Invoice", icon: "coin", approveLabel: "" },
  pay_rent: { label: "Payment · rent", isPayment: true, target: "Lease", icon: "coin", approveLabel: "" },
  purchase_order: {
    label: "Purchase order",
    isPayment: false,
    target: "Vendor",
    icon: "cart",
    approveLabel: "Approve purchase order",
  },
  offer_discount: {
    label: "Price decision · discount",
    isPayment: false,
    target: "Ticket",
    icon: "ticket",
    approveLabel: "Approve discount",
  },
};

const STATUS_TONE = {
  pending: "attention",
  executed: "success",
  approved: "success",
  declined: "neutral",
  superseded: "neutral",
} as const;
const STATUS_LABEL = {
  pending: "Awaiting you",
  executed: "Paid",
  approved: "Approved",
  declined: "Declined",
  superseded: "Superseded",
} as const;

type Outcome = ApprovalResult | DeclineResult;

interface Props {
  proposals: Proposal[];
  loaded: boolean;
  error?: string;
  balance: Balance | null;
  connection: Connection;
  onApprove: (p: Proposal, approvedBy: string) => Promise<unknown>;
  onDecline: (p: Proposal, declinedBy: string, reason: string) => Promise<unknown>;
}

function outcomeTitle(r: Outcome): string {
  if (r.outcome === "declined") return `Proposal #${r.proposal_id}: declined`;
  if (r.outcome === "executed") return `Proposal #${r.proposal_id}: payment executed`;
  return `Proposal #${r.proposal_id}: ${r.kind === "offer_discount" ? "discount approved" : "purchase order approved"}`;
}

export function ApprovalPanel({ proposals, loaded, error, balance, connection, onApprove, onDecline }: Props) {
  const pending = proposals.filter((p) => p.status === "pending");
  const history = proposals.filter((p) => p.status !== "pending");
  const [showHistory, setShowHistory] = useState(false);
  // Results stay visible after the proposal leaves the pending list.
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const currency = balance?.currency ?? "USD";

  if (!loaded && !error) return null;
  if (error && !proposals.length) {
    return (
      <section className="panel">
        <Notice tone="attention" title="Proposals unavailable">
          {error}
        </Notice>
      </section>
    );
  }
  if (!pending.length && !history.length && !outcomes.length) return null;

  return (
    <section className={`panel approvals ${pending.length ? "approvals--pending" : ""}`}>
      <SectionTitle
        kicker={pending.length ? "Your decision is needed" : "Approvals"}
        aside={
          history.length ? (
            <button type="button" className="link-button" onClick={() => setShowHistory((s) => !s)} aria-expanded={showHistory}>
              {showHistory ? "Hide" : "Show"} history ({history.length})
            </button>
          ) : null
        }
      >
        {pending.length
          ? `${pending.length} proposal${pending.length > 1 ? "s" : ""} awaiting your decision`
          : "No proposals awaiting a decision"}
      </SectionTitle>

      {outcomes.map((r) => (
        <Notice
          key={r.proposal_id}
          tone={r.outcome === "declined" ? "neutral" : "success"}
          title={outcomeTitle(r)}
          action={
            <button
              type="button"
              className="btn btn--small"
              onClick={() => setOutcomes((o) => o.filter((x) => x.proposal_id !== r.proposal_id))}
            >
              Dismiss
            </button>
          }
        >
          {r.message}
          {r.outcome !== "declined" &&
            ` Checking: ${money(r.balance_before, currency)} → ${money(r.balance_after, currency)} (reported by the backend).`}
          {r.resolved_ticket_ids.length > 0 && ` Ticket ${r.resolved_ticket_ids.join(", ")} is now resolved.`}
        </Notice>
      ))}

      {pending.map((p) => (
        <ProposalCard
          key={p.id}
          proposal={p}
          balance={balance}
          connection={connection}
          onApprove={onApprove}
          onDecline={onDecline}
          onDone={(r) => setOutcomes((o) => [...o.filter((x) => x.proposal_id !== r.proposal_id), r])}
        />
      ))}

      {showHistory && (
        <ul className="history">
          {history.map((p) => (
            <li key={p.id} className="history__row">
              <span className="history__id">#{p.id}</span>
              <span>
                {KIND[p.kind]?.label ?? humanize(p.kind)} · {money(p.amount, currency)}
                {p.kind === "offer_discount" ? ` below list for ${p.payee}` : ` to ${p.payee}`}
              </span>
              <Pill tone={STATUS_TONE[p.status]}>{STATUS_LABEL[p.status]}</Pill>
              {p.result && <span className="history__result">{p.result}</span>}
              {p.decided_by && (
                <span className="history__by">
                  by {p.decided_by}
                  {p.decided_at ? ` · ${time(p.decided_at)}` : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type Phase =
  | { step: "idle" }
  | { step: "confirm" }
  | { step: "declining" }
  | { step: "submitting"; action: "approve" | "decline" }
  | { step: "failed"; code: string; message: string; action: "approve" | "decline" };

function ProposalCard({
  proposal: p,
  balance,
  connection,
  onApprove,
  onDecline,
  onDone,
}: {
  proposal: Proposal;
  balance: Balance | null;
  connection: Connection;
  onApprove: Props["onApprove"];
  onDecline: Props["onDecline"];
  onDone: (r: Outcome) => void;
}) {
  const kind: KindInfo = KIND[p.kind] ?? {
    label: humanize(p.kind),
    isPayment: true,
    target: humanize(p.ref_table),
    icon: "coin",
    approveLabel: "Approve",
  };
  const [phase, setPhase] = useState<Phase>({ step: "idle" });
  const [approver, setApprover] = useState(() => window.localStorage.getItem(APPROVER_KEY) ?? "");
  const [reason, setReason] = useState("");
  const currency = balance?.currency ?? "USD";
  const amount = money(p.amount, currency);
  const isDiscount = p.kind === "offer_discount";
  const submitting = phase.step === "submitting";

  const run = async (action: "approve" | "decline") => {
    const name = approver.trim();
    if (!name) return;
    window.localStorage.setItem(APPROVER_KEY, name);
    setPhase({ step: "submitting", action });
    try {
      const result =
        action === "approve"
          ? ((await onApprove(p, name)) as ApprovalResult)
          : ((await onDecline(p, name, reason.trim())) as DeclineResult);
      onDone(result);
      setPhase({ step: "idle" });
    } catch (e) {
      setPhase(
        e instanceof ApiError
          ? { step: "failed", code: e.code, message: e.message, action }
          : { step: "failed", code: "error", message: "The decision could not be submitted.", action },
      );
    }
  };

  const nameField = (
    <label className="field">
      <span>Decided by (your name)</span>
      <input
        value={approver}
        onChange={(e) => setApprover(e.target.value)}
        maxLength={80}
        placeholder="e.g. Celia Gehant"
        autoFocus
        disabled={submitting}
      />
    </label>
  );

  return (
    <article className={`proposal ${kind.isPayment ? "proposal--payment" : "proposal--order"}`}>
      <header className="proposal__head">
        <span className={`proposal__kind ${kind.isPayment ? "" : "proposal__kind--order"}`}>
          <Icon name={kind.icon} size={14} />
          {kind.label}
        </span>
        <span className="proposal__id">Proposal #{p.id}</span>
      </header>

      <div className="proposal__main">
        {isDiscount ? (
          <>
            <div className="proposal__amount serif">{p.discount_pct != null ? `${p.discount_pct}% off` : "Discount"}</div>
            <div className="proposal__who">
              <span className="muted">for</span> <strong>{p.payee}</strong>
              <span className="proposal__ref">
                {p.quantity ?? ""} × {p.sku} · {amount} below list price in total
              </span>
            </div>
          </>
        ) : (
          <>
            <div className="proposal__amount serif">{amount}</div>
            <div className="proposal__who">
              <span className="muted">{kind.isPayment ? "to" : "from"}</span> <strong>{p.payee}</strong>
              <span className="proposal__ref">
                {kind.target} #{p.ref_id}
                {p.sku ? ` · ${p.quantity ?? ""} × ${p.sku}${p.size ? ` ${p.size}` : ""}` : ""}
              </span>
            </div>
          </>
        )}
      </div>
      <p className="proposal__desc">{p.description}</p>

      <p className="proposal__explain">
        {kind.isPayment ? (
          <>
            Approving <strong>pays {amount}</strong> from checking to {p.payee} in the local simulation. The backend
            re-checks the balance and the {kind.target.toLowerCase()} at the moment of payment.
          </>
        ) : isDiscount ? (
          <>
            Approving records a <strong>price decision</strong> for this request. No cash moves, the price list is not
            changed and nothing is sent to {p.payee}. The backend re-checks that the discounted price stays above unit
            cost.
          </>
        ) : (
          <>
            Approving records an <strong>approved draft purchase order</strong>. No cash moves and nothing is sent to
            the vendor. The backend first re-checks that {p.payee} has no unpaid invoice.
          </>
        )}
      </p>

      {p.blocked_reason && (
        <Notice tone="attention" title="Flagged by the agents">
          {p.blocked_reason} The backend will refuse the approval if this still applies.
        </Notice>
      )}

      {phase.step === "idle" && (
        <div className="proposal__actions">
          <button
            type="button"
            className="btn btn--primary"
            disabled={connection !== "online"}
            onClick={() => setPhase({ step: "confirm" })}
          >
            <Icon name="check" size={15} /> Review and approve…
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            disabled={connection !== "online"}
            onClick={() => setPhase({ step: "declining" })}
          >
            <Icon name="x" size={14} /> Decline…
          </button>
          <span className="proposal__note">Nothing happens until you decide. Declining records your decision; nothing is paid or sent.</span>
        </div>
      )}

      {(phase.step === "confirm" || (submitting && phase.action === "approve")) && (
        <div className="confirm" role="group" aria-label="Confirm approval">
          <div className="confirm__title serif">
            {kind.isPayment
              ? `Confirm payment of ${amount}`
              : isDiscount
                ? `Confirm ${p.discount_pct ?? ""}% discount for ${p.payee}`
                : "Confirm purchase-order approval"}
          </div>
          <dl className="confirm__facts">
            <div>
              <dt>{kind.isPayment ? "Payee" : isDiscount ? "Requester" : "Vendor"}</dt>
              <dd>{p.payee}</dd>
            </div>
            <div>
              <dt>{isDiscount ? "Below list" : "Amount"}</dt>
              <dd>{amount}</dd>
            </div>
            <div>
              <dt>{kind.target}</dt>
              <dd>#{p.ref_id}</dd>
            </div>
            {kind.isPayment && balance && (
              <div>
                <dt>Checking now</dt>
                <dd>{money(balance.balance, balance.currency)}</dd>
              </div>
            )}
          </dl>
          {nameField}
          <div className="confirm__actions">
            <button type="button" className="btn btn--ghost" onClick={() => setPhase({ step: "idle" })} disabled={submitting}>
              Back
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => run("approve")}
              disabled={!approver.trim() || submitting || connection !== "online"}
            >
              {submitting ? <Spinner label="Submitting" /> : <Icon name="lock" size={14} />}
              {submitting ? "Submitting…" : kind.isPayment ? `Authorize payment of ${amount}` : kind.approveLabel}
            </button>
          </div>
        </div>
      )}

      {(phase.step === "declining" || (submitting && phase.action === "decline")) && (
        <div className="confirm confirm--decline" role="group" aria-label="Confirm decline">
          <div className="confirm__title serif">Decline proposal #{p.id}?</div>
          <p className="muted small">
            The proposal is marked declined and your decision is recorded. Nothing is paid, ordered or sent.
          </p>
          {nameField}
          <label className="field">
            <span>Reason (optional)</span>
            <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} disabled={submitting} />
          </label>
          <div className="confirm__actions">
            <button type="button" className="btn btn--ghost" onClick={() => setPhase({ step: "idle" })} disabled={submitting}>
              Back
            </button>
            <button
              type="button"
              className="btn btn--danger"
              onClick={() => run("decline")}
              disabled={!approver.trim() || submitting || connection !== "online"}
            >
              {submitting ? "Submitting…" : "Decline proposal"}
            </button>
          </div>
        </div>
      )}

      {phase.step === "failed" && (
        <Notice
          tone="danger"
          title={`Not ${phase.action === "approve" ? "approved" : "declined"} — ${humanize(phase.code)}`}
          action={
            <button type="button" className="btn btn--small" onClick={() => setPhase({ step: "idle" })}>
              Dismiss
            </button>
          }
        >
          {phase.message} Nothing was paid; the balance shown is the backend's.
        </Notice>
      )}
    </article>
  );
}
