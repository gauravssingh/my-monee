export function formatMoney(amount: number, currency = "INR"): string {
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `₹${amount.toLocaleString("en-IN")}`;
  }
}

export function monthLabel(year: number, month: number): string {
  return new Date(year, month - 1, 1).toLocaleString("en-IN", {
    month: "long",
    year: "numeric",
  });
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

const SOURCE_LABELS: Record<string, string> = {
  rule: "Rule",
  user: "Manual",
  unknown: "Unknown",
  model: "Model",
};

export function formatSource(source: string): string {
  return SOURCE_LABELS[source] ?? (source.charAt(0).toUpperCase() + source.slice(1));
}

export const ISSUE_TYPE_LABELS: Record<string, string> = {
  wrong_amount: "Wrong amount",
  wrong_date: "Wrong date",
  wrong_merchant: "Wrong merchant",
  wrong_direction: "Wrong debit/credit",
  not_a_transaction: "Not a transaction",
  duplicate: "Duplicate",
  other: "Other",
};

export function formatIssueType(issueType: string): string {
  return ISSUE_TYPE_LABELS[issueType] ?? issueType;
}

const ISSUE_FIELD_BY_TYPE: Record<string, string | null> = {
  wrong_amount: "amount",
  wrong_date: "transaction_date",
  wrong_merchant: "merchant_normalized",
  wrong_direction: "direction",
  not_a_transaction: null,
  duplicate: null,
  other: null,
};

export function issueFieldForType(issueType: string): string | null {
  return ISSUE_FIELD_BY_TYPE[issueType] ?? null;
}
