import { useEffect, useState } from "react";
import type { Balance, DashboardEvent, Proposal, Ticket } from "../api/types";
import { dateLong, elapsed, humanize, time, timeShort, WORKFLOW_LABEL, WORKFLOW_TONE, type TicketState } from "../lib/format";
import type { Connection, TicketView } from "../state/useDesk";
import { AgentSummary } from "./AgentSummary";
import { ApprovalPanel } from "./ApprovalPanel";
import { Icon } from "./Icon";
import { Notice, Pill, SectionTitle, Spinner } from "./ui";

interface Props {
  ticket: Ticket;
  state: TicketState | undefined;
  view: TicketView | undefined;
  connection: Connection;
  starting: boolean;
  balance: Balance | null;
  onStart: () => void;
  onApprove: (p: Proposal, approvedBy: string) => Promise<unknown>;
  onDecline: (p: Proposal, declinedBy: string, reason: string) => Promise<unknown>;
  onReload: () => void;
}

export function Workspace({
  ticket,
  state,
  view,
  connection,
  starting,
  balance,
  onStart,
  onApprove,
  onDecline,
  onReload,
}: Props) {
  const run = view?.run && view.runUnavailable !== view.run.run_id ? view.run : undefined;
  const currentRunId = ticket.active_run?.run_id ?? run?.run_id ?? ticket.latest_run?.run_id ?? null;
  const runEvents = (view?.events ?? []).filter((e) => e.run_id === currentRunId);
  const result = run?.run_id === currentRunId ? run?.result : undefined;

  return (
    <main className="workspace" aria-label={`Ticket ${ticket.ticket_id} workspace`}>
      <TicketBrief ticket={ticket} state={state} view={view} onReload={onReload} />

      <RunControl
        ticket={ticket}
        state={state}
        connection={connection}
        starting={starting}
        feedback={view?.runFeedback}
        onStart={onStart}
      />

      <RunStatus ticket={ticket} view={view} runEvents={runEvents} currentRunId={currentRunId} />

      <ApprovalPanel
        proposals={view?.proposals ?? []}
        loaded={view?.proposalsLoaded ?? false}
        error={view?.proposalsError}
        balance={balance}
        connection={connection}
        onApprove={onApprove}
        onDecline={onDecline}
      />

      <Decision result={result} runEvents={runEvents} />

      <AgentSummary result={result} runEvents={runEvents} hasRun={Boolean(currentRunId)} />

      {result?.customer_drafts?.length ? (
        <section className="panel">
          <SectionTitle kicker="For review — not sent">Customer reply draft</SectionTitle>
          {result.customer_drafts.map((d, i) => (
            <article key={i} className="letter">
              <div className="letter__head">
                <span>
                  <span className="letter__label">To</span> {d.to}
                </span>
                <span>
                  <span className="letter__label">Subject</span> {d.subject}
                </span>
              </div>
              <div className="letter__body">{d.body}</div>
              {d.open_questions?.length ? (
                <div className="letter__questions">
                  <strong>Confirm before sending:</strong>
                  <ul>
                    {d.open_questions.map((q, j) => (
                      <li key={j}>{q}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <div className="letter__stamp">
                <Icon name="lock" size={13} /> Draft only — the system cannot send email
              </div>
            </article>
          ))}
        </section>
      ) : null}
    </main>
  );
}

function TicketBrief({
  ticket,
  state,
  view,
  onReload,
}: {
  ticket: Ticket;
  state: TicketState | undefined;
  view: TicketView | undefined;
  onReload: () => void;
}) {
  const detail = view?.detail;
  const links = detail?.database.linked_records;
  const facts: { label: string; value: string }[] = [
    { label: "Requester", value: ticket.requester },
    { label: "Received", value: `${dateLong(ticket.created_at)} · ${timeShort(ticket.created_at)}` },
  ];
  if (ticket.sku) {
    const name = links?.product?.product_name;
    facts.push({ label: "Item", value: `${name ? `${name} · ` : ""}${ticket.sku}` });
  }
  if (ticket.size) facts.push({ label: "Size", value: ticket.size });
  if (ticket.qty != null) facts.push({ label: "Quantity", value: String(ticket.qty) });
  if (ticket.invoice_id != null) {
    const v = links?.invoice?.vendor_name;
    facts.push({ label: "Invoice", value: `#${ticket.invoice_id}${v ? ` · ${v}` : ""}` });
  }
  if (ticket.lease_id != null) {
    const s = links?.lease?.space_name;
    facts.push({ label: "Lease", value: `#${ticket.lease_id}${s ? ` · ${s}` : ""}` });
  }

  return (
    <section className="brief">
      <div className="brief__top">
        <span className="brief__no">No. {ticket.ticket_id}</span>
        <span className="brief__type">{humanize(ticket.type)}</span>
        <span className="brief__persisted">
          Ticket status: <strong>{humanize(ticket.status)}</strong>
        </span>
        {state && (
          <Pill tone={state.tone} live={state.key === "running"}>
            {state.label}
          </Pill>
        )}
      </div>
      <h2 className="brief__subject serif">{ticket.subject}</h2>
      {detail?.database.ticket.notes ? (
        <blockquote className="brief__notes">“{detail.database.ticket.notes}”</blockquote>
      ) : view?.detailError ? (
        <Notice
          tone="attention"
          title="Ticket details unavailable"
          action={
            <button type="button" className="btn btn--small" onClick={onReload}>
              Retry
            </button>
          }
        >
          {view.detailError}
        </Notice>
      ) : null}
      <dl className="facts">
        {facts.map((f) => (
          <div key={f.label}>
            <dt>{f.label}</dt>
            <dd>{f.value}</dd>
          </div>
        ))}
      </dl>
      {detail?.notes.length ? (
        <ul className="brief__warnings">
          {detail.notes.map((n, i) => (
            <li key={i}>
              <Icon name="alert" size={13} /> {n}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function RunControl({
  ticket,
  state,
  connection,
  starting,
  feedback,
  onStart,
}: {
  ticket: Ticket;
  state: TicketState | undefined;
  connection: Connection;
  starting: boolean;
  feedback: TicketView["runFeedback"];
  onStart: () => void;
}) {
  let disabledReason: string | null = null;
  if (connection !== "online") disabledReason = "The backend is not connected.";
  else if (state?.key === "running") disabledReason = "The agent team is already working on this ticket.";
  else if (ticket.status.toLowerCase() !== "open")
    disabledReason = "This ticket is resolved. Reset the working database to run it again.";

  const again = Boolean(ticket.latest_run);
  return (
    <section className="runbar">
      <div className="runbar__text">
        <div className="kicker">Agent team</div>
        <p>
          The Boss reads the ticket, decides which specialists to involve, and returns a decision for you. Nothing is
          paid or sent without your approval.
        </p>
      </div>
      <div className="runbar__action">
        <button
          type="button"
          className="btn btn--primary btn--large"
          disabled={Boolean(disabledReason) || starting}
          onClick={onStart}
          aria-describedby={disabledReason ? "run-disabled-reason" : undefined}
        >
          {starting ? <Spinner label="Starting" /> : <Icon name="play" size={15} />}
          {starting ? "Starting…" : again ? "Run the agent team again" : "Run the agent team"}
        </button>
        {disabledReason && (
          <div id="run-disabled-reason" className="runbar__reason">
            {disabledReason}
          </div>
        )}
        {feedback && <div className={`runbar__feedback runbar__feedback--${feedback.tone}`}>{feedback.message}</div>}
      </div>
    </section>
  );
}

function RunStatus({
  ticket,
  view,
  runEvents,
  currentRunId,
}: {
  ticket: Ticket;
  view: TicketView | undefined;
  runEvents: DashboardEvent[];
  currentRunId: string | null;
}) {
  const run = view?.run && view.run.run_id === currentRunId ? view.run : undefined;
  const running = ticket.active_run?.state === "running" || run?.state === "running";
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!running) return;
    const h = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(h);
  }, [running]);

  if (!currentRunId) {
    return (
      <section className="status status--idle">
        <Icon name="clock" size={18} />
        <div>
          <strong>No agent run yet</strong>
          <span>The team has not worked on this ticket since the database was last reset.</span>
        </div>
      </section>
    );
  }

  const startedAt = run?.started_at ?? ticket.active_run?.started_at;
  if (running) {
    const last = runEvents[runEvents.length - 1];
    return (
      <section className="status status--running" aria-live="polite">
        <span className="live-dot live-dot--large" aria-hidden />
        <div>
          <strong>Agents are working</strong>
          <span>
            Run <code>{currentRunId}</code>
            {startedAt ? ` · ${elapsed(startedAt)} elapsed` : ""} · {runEvents.length} events
          </span>
          {last && <span className="status__latest">Latest: {last.description}</span>}
        </div>
        <span className="status__bar" aria-hidden />
      </section>
    );
  }

  if (run?.state === "failed") {
    return (
      <section className="status status--danger" role="alert">
        <Icon name="alert" size={18} />
        <div>
          <strong>The run failed</strong>
          <span>
            Run <code>{run.run_id}</code> · {run.error ?? "No error detail was returned."}
          </span>
        </div>
      </section>
    );
  }

  const wf = run?.workflow_status ?? ticket.latest_run?.run_status ?? null;
  const tone = wf ? WORKFLOW_TONE[wf] : "neutral";
  const resolved = ticket.status.toLowerCase() === "resolved";
  return (
    <section className={`status status--${tone}`}>
      <Icon name={tone === "success" ? "check" : tone === "danger" ? "stop" : "flag"} size={18} />
      <div>
        <strong>Run finished: {wf ? WORKFLOW_LABEL[wf] : "status unknown"}</strong>
        <span>
          Run <code>{currentRunId}</code>
          {run?.finished_at ? ` · finished ${time(run.finished_at)}` : ""}
          {run?.stop_reason ? ` · ${run.stop_reason}` : ""}
        </span>
        <span className={`status__persisted ${resolved ? "status__persisted--resolved" : ""}`}>
          {resolved
            ? "The database confirms this ticket is resolved."
            : "The ticket is still open in the database — the run finishing does not resolve it."}
        </span>
        {view?.runUnavailable === currentRunId && (
          <span className="status__note">
            Full run details are no longer held by the backend (it was restarted); summaries below come from the audit
            trail.
          </span>
        )}
      </div>
    </section>
  );
}

function asList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === "string" && value) return [value];
  return [];
}

function Decision({
  result,
  runEvents,
}: {
  result: NonNullable<TicketView["run"]>["result"] | undefined;
  runEvents: DashboardEvent[];
}) {
  const decision = result?.decision;
  if (decision) {
    const tone = WORKFLOW_TONE[result.status] ?? "neutral";
    return (
      <section className="panel decision">
        <SectionTitle
          kicker="The Boss's decision"
          aside={
            <span className="decision__chips">
              <Pill tone={tone}>{WORKFLOW_LABEL[result.status] ?? humanize(result.status)}</Pill>
              <Pill tone={decision.urgency === "urgent" || decision.urgency === "high" ? "danger" : "neutral"}>
                Urgency: {humanize(decision.urgency)}
              </Pill>
            </span>
          }
        >
          Recommendation
        </SectionTitle>
        <p className="decision__quote serif">{decision.decision}</p>
        <p className="decision__summary">{decision.operator_summary}</p>
        <div className="decision__next">
          <Icon name="arrow" size={15} />
          <span>
            <strong>Next step:</strong> {decision.next_step}
          </span>
        </div>
        <div className="decision__lists">
          {decision.blockers?.length ? (
            <div className="decision__list decision__list--danger">
              <h4>Blockers</h4>
              <ul>
                {decision.blockers.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {decision.outstanding_items?.length ? (
            <div className="decision__list">
              <h4>Outstanding for a human</h4>
              <ul>
                {decision.outstanding_items.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {result.approvals_required?.length ? (
            <div className="decision__list">
              <h4>Needs human sign-off</h4>
              <ul>
                {result.approvals_required.map((a, i) => (
                  <li key={i}>
                    <span className={`tag tag--${a.status === "blocked" ? "danger" : "neutral"}`}>
                      {humanize(a.action_type)}
                    </span>{" "}
                    {a.description}
                    {a.blocked_reason ? <em className="decision__blocked"> — blocked: {a.blocked_reason}</em> : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </section>
    );
  }

  // Fall back to the Boss's decision event recorded in the audit trail.
  const bossDone = [...runEvents].reverse().find((e) => e.event_type === "agent_completed" && e.agent === "boss");
  if (!bossDone) return null;
  const findings = asList(bossDone.findings);
  const recs = asList(bossDone.recommendation);
  return (
    <section className="panel decision">
      <SectionTitle kicker="The Boss's decision · from the audit trail">Recommendation</SectionTitle>
      <p className="decision__quote serif">{findings[0] ?? bossDone.description}</p>
      {recs.length ? (
        <div className="decision__list">
          <h4>Recommended actions</h4>
          <ul>
            {recs.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="muted small">Audit entries are shortened; the full decision was held by the backend session that ran it.</p>
    </section>
  );
}
