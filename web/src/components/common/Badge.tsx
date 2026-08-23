import React from "react";

export type BadgeVariant =
  | "neutral"
  | "success"
  | "warn"
  | "danger"
  | "info"
  | "credit"
  | "debit";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  size?: "sm" | "md";
  icon?: React.ReactNode;
  children: React.ReactNode;
}

export default function Badge({
  variant = "neutral",
  size = "sm",
  icon,
  children,
  className = "",
  style,
  ...rest
}: BadgeProps) {
  const getColors = (): { bg: string; color: string; border?: string } => {
    switch (variant) {
      case "success":
      case "credit":
        return {
          bg: "var(--credit-soft, rgba(47, 109, 79, 0.12))",
          color: "var(--credit, #2f6d4f)",
          border: "1px solid rgba(47, 109, 79, 0.2)",
        };
      case "warn":
        return {
          bg: "var(--warn-soft, rgba(138, 90, 18, 0.12))",
          color: "var(--warn, #8a5a12)",
          border: "1px solid rgba(138, 90, 18, 0.2)",
        };
      case "danger":
      case "debit":
        return {
          bg: "var(--debit-soft, rgba(165, 51, 59, 0.12))",
          color: "var(--debit, #a5333b)",
          border: "1px solid rgba(165, 51, 59, 0.2)",
        };
      case "info":
        return {
          bg: "var(--info-soft, rgba(45, 91, 136, 0.12))",
          color: "var(--info, #2d5b88)",
          border: "1px solid rgba(45, 91, 136, 0.2)",
        };
      case "neutral":
      default:
        return {
          bg: "var(--surface-muted, rgba(0, 0, 0, 0.04))",
          color: "var(--ink-muted, #6b707a)",
          border: "1px solid var(--line, #d9dde1)",
        };
    }
  };

  const colors = getColors();
  const isSm = size === "sm";

  return (
    <span
      className={`badge badge-${variant} ${className}`.trim()}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: isSm ? "2px 7px" : "3px 10px",
        fontSize: isSm ? "var(--text-2xs, 0.72rem)" : "var(--text-xs, 0.78rem)",
        fontWeight: 600,
        borderRadius: "var(--radius-sm, 4px)",
        letterSpacing: "0.01em",
        whiteSpace: "nowrap",
        background: colors.bg,
        color: colors.color,
        border: colors.border,
        ...style,
      }}
      {...rest}
    >
      {icon && (
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            lineHeight: 1,
          }}
        >
          {icon}
        </span>
      )}
      <span>{children}</span>
    </span>
  );
}
