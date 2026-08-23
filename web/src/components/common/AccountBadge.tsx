import React from "react";
import AccountBrandLogo from "./AccountBrandLogo";
import { getAccountBrandInfo } from "../../utils/accountDisplay";

interface AccountBadgeProps {
  accountName: string;
  accountType?: string;
  cardLast4?: string | null;
  accountNumberMasked?: string | null;
  logoSize?: number;
  showIdentifiers?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

export default function AccountBadge({
  accountName,
  accountType,
  cardLast4,
  accountNumberMasked,
  logoSize = 22,
  showIdentifiers = true,
  className = "",
  style,
}: AccountBadgeProps) {
  const info = getAccountBrandInfo(accountName, accountType, cardLast4, accountNumberMasked);

  const identifier = cardLast4
    ? `•••• ${cardLast4}`
    : accountNumberMasked
      ? `•••• ${accountNumberMasked.slice(-4)}`
      : null;

  return (
    <div
      className={`account-badge ${className}`.trim()}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        ...style,
      }}
    >
      <AccountBrandLogo brand={info.brand} size={logoSize} />
      <span style={{ display: "inline-flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
        <strong style={{ fontWeight: 600, color: "var(--ink)", fontSize: "0.9rem" }}>
          {info.shortName}
        </strong>
        {showIdentifiers && identifier && (
          <span
            style={{
              fontSize: "0.8rem",
              color: "var(--ink-muted)",
              fontFamily: "var(--font-mono, monospace)",
              letterSpacing: "0.02em",
            }}
          >
            ({identifier})
          </span>
        )}
      </span>
    </div>
  );
}
