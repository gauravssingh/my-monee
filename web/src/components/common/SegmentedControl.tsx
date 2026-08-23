import React from "react";

export interface SegmentOption<T extends string = string> {
  value: T;
  label: React.ReactNode;
  count?: number | string;
  icon?: React.ReactNode;
}

export interface SegmentedControlProps<T extends string = string> {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: "sm" | "md";
  className?: string;
  style?: React.CSSProperties;
}

export default function SegmentedControl<T extends string = string>({
  options,
  value,
  onChange,
  size = "md",
  className = "",
  style,
}: SegmentedControlProps<T>) {
  const isSm = size === "sm";

  return (
    <div
      role="tablist"
      className={`segmented-control ${className}`.trim()}
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: 3,
        background: "var(--surface-muted, rgba(0, 0, 0, 0.04))",
        borderRadius: "var(--radius-md, 8px)",
        border: "1px solid var(--line, #d9dde1)",
        gap: 2,
        ...style,
      }}
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: isSm ? "4px 8px" : "6px 12px",
              fontSize: isSm ? "var(--text-xs, 0.75rem)" : "var(--text-sm, 0.82rem)",
              fontWeight: active ? 600 : 500,
              color: active ? "var(--ink)" : "var(--ink-muted)",
              background: active ? "var(--surface)" : "transparent",
              border: "none",
              borderRadius: "calc(var(--radius-md, 8px) - 2px)",
              boxShadow: active ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
              cursor: "pointer",
              transition: "all 0.15s ease",
              whiteSpace: "nowrap",
            }}
          >
            {opt.icon && (
              <span style={{ display: "inline-flex", alignItems: "center" }}>
                {opt.icon}
              </span>
            )}
            <span>{opt.label}</span>
            {opt.count !== undefined && (
              <span
                style={{
                  fontSize: "var(--text-2xs, 0.68rem)",
                  padding: "1px 5px",
                  borderRadius: "var(--radius-full, 9999px)",
                  background: active ? "var(--accent-soft)" : "rgba(0,0,0,0.06)",
                  color: active ? "var(--accent)" : "var(--ink-muted)",
                  fontWeight: 700,
                  marginLeft: 2,
                }}
              >
                {opt.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
