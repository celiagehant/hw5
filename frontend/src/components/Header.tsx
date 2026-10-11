import { useEffect, useState } from "react";
import { API_BASE } from "../api/client";
import type { Balance } from "../api/types";
import type { Tone } from "../lib/agents";
import { dateLong, money } from "../lib/format";
import type { BalanceChange, Connection } from "../state/useDesk";
import { Icon } from "./Icon";
import { Pill } from "./ui";

interface Props {
  connection: Connection;
  connectionError: string | null;
  shopDate: string | null;
  balance: Balance | null;
  balanceError: string | null;
  balanceChange: BalanceChange | null;
  opsStatus: { label: string; tone: Tone; live?: boolean };
  onRetry: () => void;
}

export function Header(p: Props) {
  return (
    <header className="masthead">
      <div className="masthead__brand">
        <span className="crest" aria-hidden>
          CC
        </span>
        <div>
          <div className="masthead__org">Campus Customs</div>
          <h1 className="masthead__title serif">Operations Desk</h1>
        </div>
      </div>

      <div className="masthead__meta">
        <ConnectionIndicator connection={p.connection} error={p.connectionError} onRetry={p.onRetry} />
        <div className="masthead__status">
          <span className="masthead__label">Operations</span>
          <Pill tone={p.opsStatus.tone} live={p.opsStatus.live}>
            {p.opsStatus.label}
          </Pill>
        </div>
        {p.shopDate && (
          <div className="masthead__status">
            <span className="masthead__label">Business date</span>
            <span className="masthead__value">{dateLong(p.shopDate)}</span>
          </div>
        )}
      </div>

      <BalanceDisplay
        balance={p.balance}
        error={p.balanceError}
        change={p.balanceChange}
        stale={p.connection === "offline"}
      />
    </header>
  );
}

function ConnectionIndicator({
  connection,
  error,
  onRetry,
}: {
  connection: Connection;
  error: string | null;
  onRetry: () => void;
}) {
  if (connection === "online") {
    return (
      <div className="conn conn--online" title={`Connected to ${API_BASE}`}>
        <span className="conn__dot" aria-hidden />
        <span>
          Connected <span className="conn__host">· {API_BASE.replace(/^https?:\/\//, "")}</span>
        </span>
      </div>
    );
  }
  if (connection === "connecting") {
    return (
      <div className="conn conn--connecting">
        <span className="conn__dot" aria-hidden />
        <span>Connecting to backend…</span>
      </div>
    );
  }
  return (
    <div className="conn conn--offline" role="alert" title={error ?? undefined}>
      <Icon name="plug" size={14} />
      <span>Backend offline</span>
      <button type="button" className="link-button link-button--light" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}

/** The checking balance as the backend reports it. A change is flagged for a few seconds. */
function BalanceDisplay({
  balance,
  error,
  change,
  stale,
}: {
  balance: Balance | null;
  error: string | null;
  change: BalanceChange | null;
  stale: boolean;
}) {
  const [showChange, setShowChange] = useState(false);
  useEffect(() => {
    if (!change) return;
    setShowChange(true);
    const t = window.setTimeout(() => setShowChange(false), 12000);
    return () => window.clearTimeout(t);
  }, [change]);

  return (
    <div className="ledger" aria-live="polite">
      <div className="ledger__label">
        <Icon name="wallet" size={14} />
        {balance ? `${balance.account[0].toUpperCase()}${balance.account.slice(1)} balance` : "Checking balance"}
      </div>
      {balance ? (
        <>
          <div key={balance.balance} className={`ledger__amount serif ${change && showChange ? "ledger__amount--changed" : ""}`}>
            {money(balance.balance, balance.currency)}
          </div>
          <div className="ledger__foot">
            {stale ? (
              <span className="ledger__stale">Last known value · backend offline</span>
            ) : change && showChange ? (
              <span className={change.to < change.from ? "ledger__delta ledger__delta--down" : "ledger__delta"}>
                {change.to < change.from ? "▼" : "▲"} was {money(change.from, balance.currency)}
              </span>
            ) : (
              <span>
                {balance.currency} · as of {dateLong(balance.balance_date)}
              </span>
            )}
          </div>
        </>
      ) : error ? (
        <div className="ledger__error">Unavailable</div>
      ) : (
        <div className="ledger__amount ledger__amount--loading serif">—</div>
      )}
    </div>
  );
}
