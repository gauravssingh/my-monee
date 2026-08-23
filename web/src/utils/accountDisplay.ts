export type BankBrand =
  | "axis"
  | "hdfc"
  | "icici"
  | "sbi"
  | "scapia"
  | "stanchart"
  | "kotak"
  | "idfc"
  | "federal"
  | "amex"
  | "onecard"
  | "wallet"
  | "cash"
  | "generic_bank"
  | "generic_card";

export interface AccountBrandInfo {
  brand: BankBrand;
  brandName: string;
  shortName: string;
  badgeBg: string;
  badgeColor: string;
}

/**
 * Detects the institution/brand and extracts a clean, shortened display label.
 * Example: "Axis Bank Credit Card (XX4951)" -> brand "axis", shortName "Credit Card"
 */
export function getAccountBrandInfo(
  rawName: string,
  accountType?: string,
  cardLast4?: string | null,
  _accountNumberMasked?: string | null,
): AccountBrandInfo {
  const name = (rawName || "").trim();
  const lower = name.toLowerCase();

  const isCard =
    accountType === "CREDIT_CARD" ||
    lower.includes("credit card") ||
    lower.includes("card") ||
    Boolean(cardLast4);

  const isCash = accountType === "CASH" || lower.includes("cash");
  const isWallet = accountType === "WALLET" || lower.includes("wallet") || lower.includes("fastag") || lower.includes("paytm");

  let brand: BankBrand = isCard ? "generic_card" : isCash ? "cash" : isWallet ? "wallet" : "generic_bank";
  let brandName = "Bank";
  let shortName = name;

  // 1. Brand Detection
  if (lower.includes("axis")) {
    brand = "axis";
    brandName = "Axis Bank";
  } else if (lower.includes("scapia")) {
    brand = "scapia";
    brandName = "Scapia";
  } else if (lower.includes("hdfc")) {
    brand = "hdfc";
    brandName = "HDFC Bank";
  } else if (lower.includes("icici")) {
    brand = "icici";
    brandName = "ICICI Bank";
  } else if (lower.includes("sbi") || lower.includes("state bank")) {
    brand = "sbi";
    brandName = "SBI";
  } else if (lower.includes("kotak")) {
    brand = "kotak";
    brandName = "Kotak Bank";
  } else if (lower.includes("standard chartered") || lower.includes("scb") || lower.includes("stanchart")) {
    brand = "stanchart";
    brandName = "StanChart";
  } else if (lower.includes("federal")) {
    brand = "federal";
    brandName = "Federal Bank";
  } else if (lower.includes("idfc")) {
    brand = "idfc";
    brandName = "IDFC FIRST";
  } else if (lower.includes("amex") || lower.includes("american express")) {
    brand = "amex";
    brandName = "Amex";
  } else if (lower.includes("onecard") || lower.includes("one card")) {
    brand = "onecard";
    brandName = "OneCard";
  } else if (isCash) {
    brand = "cash";
    brandName = "Cash";
  } else if (isWallet) {
    brand = "wallet";
    brandName = "Wallet";
  }

  // 2. Shorten Name: Strip repetitive brand prefix from display name
  let clean = name.replace(/\s*\([*X\d]+\)\s*$/i, "").trim();

  // Strip brand prefix if already shown in logo
  if (brand === "axis") {
    clean = clean.replace(/^axis\s*(bank)?\s*/i, "").trim();
  } else if (brand === "scapia") {
    clean = clean.replace(/^scapia\s*/i, "").trim();
  } else if (brand === "hdfc") {
    clean = clean.replace(/^hdfc\s*(bank)?\s*/i, "").trim();
  } else if (brand === "icici") {
    clean = clean.replace(/^icici\s*(bank)?\s*/i, "").trim();
  } else if (brand === "sbi") {
    clean = clean.replace(/^(sbi|state bank of india)\s*/i, "").trim();
  } else if (brand === "kotak") {
    clean = clean.replace(/^kotak\s*(mahindra)?\s*(bank)?\s*/i, "").trim();
  } else if (brand === "stanchart") {
    clean = clean.replace(/^(standard chartered|scb)\s*(bank)?\s*/i, "").trim();
  } else if (brand === "federal") {
    clean = clean.replace(/^federal\s*(bank)?\s*/i, "").trim();
  } else if (brand === "idfc") {
    clean = clean.replace(/^idfc\s*(first)?\s*(bank)?\s*/i, "").trim();
  } else if (brand === "amex") {
    clean = clean.replace(/^(amex|american express)\s*/i, "").trim();
  } else if (brand === "onecard") {
    clean = clean.replace(/^onecard\s*/i, "").trim();
  } else if (brand === "cash") {
    clean = clean.replace(/^default\s*cash\s*account/i, "Cash").replace(/^cash\s*account/i, "Cash").trim();
  }

  // If after stripping the name is empty or just "Bank", set sensible generic description
  if (!clean || clean.toLowerCase() === "bank") {
    if (isCard) clean = "Credit Card";
    else if (accountType === "BANK" || !accountType) clean = "Savings Account";
    else clean = brandName;
  }

  // Capitalize properly
  if (clean.toLowerCase() === "credit card") clean = "Credit Card";
  if (clean.toLowerCase() === "savings account") clean = "Savings Account";
  if (clean.toLowerCase() === "account") clean = "Account";

  shortName = clean;

  // Colors for logo emblem
  const brandColors: Record<BankBrand, { bg: string; color: string }> = {
    axis: { bg: "#97144D", color: "#FFFFFF" },
    hdfc: { bg: "#004C8F", color: "#FFFFFF" },
    icici: { bg: "#F37021", color: "#FFFFFF" },
    sbi: { bg: "#280071", color: "#00B5EF" },
    scapia: { bg: "#CE3E00", color: "#FFFFFF" },
    stanchart: { bg: "#007A3D", color: "#FFFFFF" },
    kotak: { bg: "#ED1C24", color: "#FFFFFF" },
    idfc: { bg: "#9D1D27", color: "#FFFFFF" },
    federal: { bg: "#003A70", color: "#FDB913" },
    amex: { bg: "#006FCF", color: "#FFFFFF" },
    onecard: { bg: "#1E293B", color: "#F59E0B" },
    wallet: { bg: "#3B82F6", color: "#FFFFFF" },
    cash: { bg: "#10B981", color: "#FFFFFF" },
    generic_bank: { bg: "var(--accent-soft)", color: "var(--accent)" },
    generic_card: { bg: "var(--info-soft)", color: "var(--info)" },
  };

  const { bg: badgeBg, color: badgeColor } = brandColors[brand] || brandColors.generic_bank;

  return {
    brand,
    brandName,
    shortName,
    badgeBg,
    badgeColor,
  };
}
