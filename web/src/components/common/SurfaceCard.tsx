import { type ReactNode, type HTMLAttributes } from "react";

export interface SurfaceCardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "standard" | "hero" | "subtle";
  padding?: "sm" | "md" | "lg" | "none";
  children: ReactNode;
  className?: string;
}

export default function SurfaceCard({
  variant = "standard",
  padding = "md",
  children,
  className = "",
  style,
  ...rest
}: SurfaceCardProps) {
  const variantClass =
    variant === "hero"
      ? "surface-card-hero"
      : variant === "subtle"
        ? "surface-card-subtle"
        : "surface-card-standard";

  const paddingClass =
    padding === "none"
      ? "p-0"
      : padding === "sm"
        ? "surface-card-p-sm"
        : padding === "lg"
          ? "surface-card-p-lg"
          : "surface-card-p-md";

  return (
    <div
      className={`surface-card ${variantClass} ${paddingClass} ${className}`.trim()}
      style={style}
      {...rest}
    >
      {children}
    </div>
  );
}
