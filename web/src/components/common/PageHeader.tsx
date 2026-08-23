import React from "react";

export interface PageHeaderProps {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  breadcrumbs?: React.ReactNode;
  className?: string;
}

export default function PageHeader({
  title,
  subtitle,
  actions,
  breadcrumbs,
  className = "",
}: PageHeaderProps) {
  return (
    <header
      className={`page-header ${className}`.trim()}
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: "var(--space-4, 16px)",
        marginBottom: "var(--space-5, 20px)",
      }}
    >
      <div style={{ flex: "1 1 auto", minWidth: 260 }}>
        {breadcrumbs && (
          <div
            style={{
              marginBottom: "var(--space-1, 4px)",
              fontSize: "var(--text-xs, 0.75rem)",
              color: "var(--ink-muted)",
            }}
          >
            {breadcrumbs}
          </div>
        )}
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontSize: "var(--text-2xl, 1.75rem)",
            fontWeight: 600,
            letterSpacing: "-0.02em",
            color: "var(--ink)",
            lineHeight: 1.2,
          }}
        >
          {title}
        </h1>
        {subtitle && (
          <p
            className="lead"
            style={{
              margin: "var(--space-1, 4px) 0 0",
              fontSize: "var(--text-sm, 0.82rem)",
              color: "var(--ink-muted)",
              lineHeight: 1.45,
            }}
          >
            {subtitle}
          </p>
        )}
      </div>

      {actions && (
        <div
          className="page-actions"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2, 8px)",
            flexWrap: "wrap",
            flexShrink: 0,
          }}
        >
          {actions}
        </div>
      )}
    </header>
  );
}
