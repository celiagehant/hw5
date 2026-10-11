import { ActivityFeed } from "./components/ActivityFeed";
import { Header } from "./components/Header";
import { Icon } from "./components/Icon";
import { TicketRail } from "./components/TicketRail";
import { Notice } from "./components/ui";
import { Workspace } from "./components/Workspace";
import { useDesk } from "./state/useDesk";

export default function App() {
  const desk = useDesk();
  const ticket = desk.tickets?.find((t) => t.ticket_id === desk.selectedId) ?? null;
  const view = ticket ? desk.views[ticket.ticket_id] : undefined;
  const run = view?.run && view.runUnavailable !== view.run.run_id ? view.run : undefined;
  const currentRunId = ticket ? (ticket.active_run?.run_id ?? run?.run_id ?? ticket.latest_run?.run_id ?? null) : null;
  const running = ticket ? desk.activeRuns.has(ticket.ticket_id) : false;

  return (
    <div className="app">
      <a className="skip-link" href="#workspace">
        Skip to workspace
      </a>
      <Header
        connection={desk.connection}
        connectionError={desk.connectionError}
        shopDate={desk.shopDate}
        balance={desk.balance}
        balanceError={desk.balanceError}
        balanceChange={desk.balanceChange}
        opsStatus={desk.opsStatus}
        onRetry={desk.retry}
      />

      {desk.connection === "offline" && (
        <div className="banner" role="alert">
          <Icon name="plug" size={16} />
          <span>
            <strong>Disconnected.</strong> {desk.connectionError} Data on screen may be out of date.
          </span>
          <button type="button" className="btn btn--small btn--light" onClick={desk.retry}>
            Retry now
          </button>
        </div>
      )}

      <div className="desk">
        <TicketRail
          tickets={desk.tickets}
          ticketsError={desk.ticketsError}
          states={desk.ticketStates}
          selectedId={desk.selectedId}
          onSelect={desk.setSelectedId}
          onRetry={desk.retry}
          activeRunCount={desk.activeRuns.size}
          resetting={desk.resetting}
          onReset={desk.reset}
        />

        <div id="workspace" className="desk__center">
          {ticket ? (
            <Workspace
              key={ticket.ticket_id}
              ticket={ticket}
              state={desk.ticketStates.get(ticket.ticket_id)}
              view={view}
              connection={desk.connection}
              starting={desk.starting === ticket.ticket_id}
              balance={desk.balance}
              onStart={() => void desk.startRun(ticket.ticket_id)}
              onApprove={desk.approve}
              onDecline={desk.decline}
              onReload={() => desk.reloadTicket(ticket.ticket_id)}
            />
          ) : desk.tickets && desk.tickets.length === 0 ? (
            <div className="workspace">
              <Notice tone="neutral" title="No tickets">
                The backend returned no tickets.
              </Notice>
            </div>
          ) : (
            <div className="workspace workspace--placeholder">
              <span className="crest crest--ghost" aria-hidden>
                CC
              </span>
              <p className="serif">Select a ticket to open its workspace.</p>
            </div>
          )}
        </div>

        {ticket && (
          <ActivityFeed
            key={ticket.ticket_id}
            ticketId={ticket.ticket_id}
            events={view?.events ?? []}
            loaded={view?.eventsLoaded ?? false}
            error={view?.eventsError}
            currentRunId={currentRunId}
            running={running}
            onRetry={() => desk.reloadTicket(ticket.ticket_id)}
          />
        )}
      </div>

      <div className="toasts" aria-live="polite">
        {desk.toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.tone}`} role="status">
            <div>
              <strong>{t.title}</strong>
              {t.message && <p>{t.message}</p>}
            </div>
            <button type="button" className="toast__close" onClick={() => desk.dismissToast(t.id)} aria-label="Dismiss">
              <Icon name="x" size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
