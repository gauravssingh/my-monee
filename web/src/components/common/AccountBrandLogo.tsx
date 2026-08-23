import React from "react";
import { BankBrand } from "../../utils/accountDisplay";

interface AccountBrandLogoProps {
  brand: BankBrand;
  size?: number;
  className?: string;
  style?: React.CSSProperties;
}

export default function AccountBrandLogo({
  brand,
  size = 24,
  className = "",
  style,
}: AccountBrandLogoProps) {
  const containerStyle: React.CSSProperties = {
    width: size,
    height: size,
    borderRadius: Math.max(4, Math.round(size * 0.22)),
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    overflow: "hidden",
    boxShadow: "0 1px 2px rgba(0, 0, 0, 0.08)",
    ...style,
  };

  switch (brand) {
    case "axis":
      return (
        <div style={{ ...containerStyle, background: "#97144D" }} className={className} title="Axis Bank">
          <svg width={size * 0.7} height={size * 0.7} viewBox="0 0 24 24" fill="none">
            <path d="M12 3L21 19H15.5L12 12.5L8.5 19H3L12 3Z" fill="#FFFFFF" />
            <path d="M12 12.5L15.5 19H8.5L12 12.5Z" fill="#97144D" />
          </svg>
        </div>
      );

    case "hdfc":
      return (
        <div style={{ ...containerStyle, background: "#004C8F" }} className={className} title="HDFC Bank">
          <svg width={size * 0.75} height={size * 0.75} viewBox="0 0 24 24" fill="none">
            <rect x="2" y="2" width="20" height="20" rx="2" fill="#004C8F" />
            <rect x="5" y="5" width="14" height="14" fill="#ED232A" />
            <rect x="9" y="3" width="6" height="18" fill="#FFFFFF" />
            <rect x="3" y="9" width="18" height="6" fill="#FFFFFF" />
            <rect x="9" y="9" width="6" height="6" fill="#004C8F" />
          </svg>
        </div>
      );

    case "icici":
      return (
        <div style={{ ...containerStyle, background: "#F37021" }} className={className} title="ICICI Bank">
          <svg width={size * 0.75} height={size * 0.75} viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="7" r="2.5" fill="#FFFFFF" />
            <path d="M10 12H14V20H10V12Z" fill="#FFFFFF" />
            <path d="M7 12H9V20H7V12Z" fill="#A51C24" />
          </svg>
        </div>
      );

    case "scapia":
      return (
        <div
          style={{ ...containerStyle, background: "#CE3E00", color: "#FFFFFF" }}
          className={className}
          title="Scapia"
        >
          <svg width={size * 0.65} height={size * 0.65} viewBox="0 0 24 24" fill="none">
            <path
              d="M17.5 6.5C17.5 4.5 15.5 3.2 12.5 3.2C9 3.2 6.5 5.2 6.5 8.2C6.5 11.5 10 12.5 14 13.5C17.5 14.5 18.5 16 18.5 18.5C18.5 21.5 15.5 23 12 23C8 23 5.5 21 5.5 18"
              stroke="#FFFFFF"
              strokeWidth="3.5"
              strokeLinecap="round"
            />
          </svg>
        </div>
      );

    case "sbi":
      return (
        <div style={{ ...containerStyle, background: "#00B5EF" }} className={className} title="State Bank of India">
          <svg width={size * 0.75} height={size * 0.75} viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" fill="#280071" />
            <circle cx="12" cy="10" r="3.5" fill="#00B5EF" />
            <rect x="10.8" y="10" width="2.4" height="9" fill="#00B5EF" />
          </svg>
        </div>
      );

    case "kotak":
      return (
        <div style={{ ...containerStyle, background: "#ED1C24" }} className={className} title="Kotak Mahindra Bank">
          <svg width={size * 0.7} height={size * 0.7} viewBox="0 0 24 24" fill="none">
            <path
              d="M6 12C6 9 8.5 7 11 7C14 7 16 10 18 12C16 14 14 17 11 17C8.5 17 6 15 6 12Z"
              stroke="#FFFFFF"
              strokeWidth="2.5"
            />
            <path
              d="M18 12C18 9 15.5 7 13 7C10 7 8 10 6 12C8 14 10 17 13 17C15.5 17 18 15 18 12Z"
              stroke="#003366"
              strokeWidth="2"
            />
          </svg>
        </div>
      );

    case "stanchart":
      return (
        <div style={{ ...containerStyle, background: "#FFFFFF", border: "1px solid var(--line)" }} className={className} title="Standard Chartered">
          <svg width={size * 0.8} height={size * 0.8} viewBox="0 0 24 24" fill="none">
            <path d="M4 14C4 10 8 7 12 7C16 7 20 10 20 14" stroke="#007A3D" strokeWidth="3" strokeLinecap="round" />
            <path d="M4 10C4 14 8 17 12 17C16 17 20 14 20 10" stroke="#0099DA" strokeWidth="3" strokeLinecap="round" />
          </svg>
        </div>
      );

    case "federal":
      return (
        <div style={{ ...containerStyle, background: "#003A70" }} className={className} title="Federal Bank">
          <svg width={size * 0.7} height={size * 0.7} viewBox="0 0 24 24" fill="none">
            <path d="M12 2L20 6V12C20 17 16.5 21 12 22C7.5 21 4 17 4 12V6L12 2Z" fill="#FDB913" />
            <path d="M12 5L17 8V12C17 15.5 14.8 18.5 12 19.5C9.2 18.5 7 15.5 7 12V8L12 5Z" fill="#003A70" />
          </svg>
        </div>
      );

    case "idfc":
      return (
        <div style={{ ...containerStyle, background: "#9D1D27" }} className={className} title="IDFC FIRST Bank">
          <svg width={size * 0.7} height={size * 0.7} viewBox="0 0 24 24" fill="none">
            <rect x="4" y="4" width="7" height="7" rx="1.5" fill="#FFFFFF" />
            <rect x="13" y="4" width="7" height="7" rx="1.5" fill="#FDB913" />
            <rect x="4" y="13" width="7" height="7" rx="1.5" fill="#FDB913" />
            <rect x="13" y="13" width="7" height="7" rx="1.5" fill="#FFFFFF" />
          </svg>
        </div>
      );

    case "amex":
      return (
        <div style={{ ...containerStyle, background: "#006FCF" }} className={className} title="American Express">
          <svg width={size * 0.75} height={size * 0.75} viewBox="0 0 24 24" fill="none">
            <rect x="2" y="5" width="20" height="14" rx="2" fill="#006FCF" />
            <path d="M5 15L8 9L11 15H9.5L8.8 13.5H7.2L6.5 15H5Z" fill="#FFFFFF" />
            <path d="M12 9H14.5L16 12L17.5 9H19V15H17.5V11.5L16 14.5L14.5 11.5V15H12V9Z" fill="#FFFFFF" />
          </svg>
        </div>
      );

    case "onecard":
      return (
        <div style={{ ...containerStyle, background: "#1E293B" }} className={className} title="OneCard">
          <svg width={size * 0.7} height={size * 0.7} viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="8" stroke="#F59E0B" strokeWidth="2.5" />
            <path d="M12 7V17" stroke="#38BDF8" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </div>
      );

    case "wallet":
      return (
        <div style={{ ...containerStyle, background: "var(--info-soft)", color: "var(--info)", border: "1px solid rgba(45, 91, 136, 0.2)" }} className={className} title="Wallet">
          <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect width="20" height="14" x="2" y="5" rx="2" />
            <path d="M16 12h.01" />
          </svg>
        </div>
      );

    case "cash":
      return (
        <div style={{ ...containerStyle, background: "var(--credit-soft)", color: "var(--credit)", border: "1px solid rgba(47, 109, 79, 0.2)" }} className={className} title="Cash">
          <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect width="20" height="12" x="2" y="6" rx="2" />
            <circle cx="12" cy="12" r="2" />
            <path d="M6 12h.01M18 12h.01" />
          </svg>
        </div>
      );

    case "generic_card":
      return (
        <div style={{ ...containerStyle, background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--line)" }} className={className} title="Credit Card">
          <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect width="20" height="14" x="2" y="5" rx="2" />
            <line x1="2" y1="10" x2="22" y2="10" />
          </svg>
        </div>
      );

    case "generic_bank":
    default:
      return (
        <div style={{ ...containerStyle, background: "var(--surface-muted)", color: "var(--ink-muted)", border: "1px solid var(--line)" }} className={className} title="Bank Account">
          <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="12 2 2 7 22 7 12 2" />
            <line x1="5" y1="10" x2="5" y2="18" />
            <line x1="10" y1="10" x2="10" y2="18" />
            <line x1="14" y1="10" x2="14" y2="18" />
            <line x1="19" y1="10" x2="19" y2="18" />
            <polygon points="2 22 22 22 22 19 2 19 2 22" />
          </svg>
        </div>
      );
  }
}
