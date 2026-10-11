import { useState } from "react";
import type { Ticket } from "../api/types";
import { humanize, type TicketState } from "../lib/format";
import { ConfirmDialog } from "./ConfirmDialog";
import { Icon } from "./Icon";
import { Notice, Pill, Spinner } from "./ui";

interface Props {
  tickets: Ticket[] | null;
  ticketsError: string | null;
  states: Map<number, TicketState>;
  selectedId: number | null;
  onSelect: (id: number) => void;
  onRetry: () => void;
  activeRunCount: number;
  resetting: boolean;
  onReset: () => Promise<unknown>;
}

const STATE_ICON = {
  running: "refresh",
  resolved: "check",
  attention: "flag",
  blocked: "stop",
  failed: "alert",
  open: "ticket",
} as const;

export function TicketRail(p: Props) {
  const [confirming, setConfirming] = useState(false);

  return (
    <nav className="rail" aria-label="Tickets">
      <div className="rail__head">
        <div className="kicker">Ticket desk</div>
        <div className="rail__count">{p.tickets ? `${p.tickets.length} tickets` : ""}</div>
      </div>

      {!p.tickets && !p.ticketsError && (
        <div className="rail__loading">
          <Spinner label="Loading tickets" /> Loading tickets…
        </div>
      )}
      {p.ticketsError && !p.tickets && (
        <Notice
          tone="danger"
          title="Tickets unavailable"
          action={
            <button type="button" className="btn btn--small" onClick={p.onRetry}>
              Retry
            </button>
          }
        >
          {p.ticketsError}
        </Notice>
      )}

      {p.tickets && (
        <ul className="stubs">
          {p.tickets.map((t) => {
            const s = p.states.get(t.ticket_id);
            const selected = t.ticket_id === p.selectedId;
            return (
              <li key={t.ticket_id}>
                <button
                  type="button"
                  className={`stub stub--${s?.key ?? "open"} ${selected ? "stub--selected" : ""}`}
                  aria-current={selected ? "true" : undefined}
                  onClick={() => p.onSelect(t.ticket_id)}
                >
                  <span className="stub__no">No. {t.ticket_id}</span>
                  <span className="stub__subject serif">{t.subject}</span>
                  <span className="stub__meta">
                    {humanize(t.type)} · {t.requester}
                  </span>
                  {s && (
                    <span className="stub__state">
                      <Pill tone={s.tone} live={s.key === "running"} icon={STATE_ICON[s.key]}>
                        {s.label}
                      </Pill>
                    </span>
                  )}
                  {s?.key === "running" && <span className="stub__progress" aria-hidden />}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className="rail__foot">
        <div className="kicker">Simulation</div>
        <p className="rail__note">
          Restore the working database to its baseline: all tickets open, original balance, no payments. The audit
          trail is kept.
        </p>
        <button
          type="button"
          className="btn btn--ghost btn--small"
          disabled={p.resetting || p.activeRunCount > 0 || !p.tickets}
          title={p.activeRunCount > 0 ? "Wait for the active run to finish" : undefined}
          onClick={() => setConfirming(true)}
        >
          <Icon name="refresh" size={14} />
          {p.resetting ? "Resetting…" : "Reset working database…"}
        </button>
      </div>

      {confirming && (
        <ConfirmDialog
          title="Reset the working database?"
          confirmLabel="Reset to baseline"
          tone="danger"
          busy={p.resetting}
          onCancel={() => setConfirming(false)}
          onConfirm={async () => {
            await p.onReset();
            setConfirming(false);
          }}
        >
          <p>
            This restores <code>data/campus_customs_new.db</code> from the untouched original. Ticket statuses,
            payments, proposals and approvals made in the simulation will be cleared, and the checking balance returns
            to its original value.
          </p>
          <p>The original database is not modified, and the audit trail keeps every past event.</p>
        </ConfirmDialog>
      )}
    </nav>
  );
}
