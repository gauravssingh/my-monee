export type Overview = {
  period: { year: number; month: number };
  current_month_spending: number;
  previous_month_spending: number;
  income: number;
  previous_month_income: number;
  income_change_pct: number | null;
  net_cash_flow: number;
  transaction_count: number;
  largest_transaction: {
    id: string;
    amount: number;
    merchant: string | null;
    date: string;
  } | null;
  needs_review_count: number;
  currency: string;
};

export type IncomeTrend = {
  months: number;
  currency: string;
  points: Array<{
    year: number;
    month: number;
    label: string;
    income: number;
  }>;
};

export type CategorySpend = {
  category_id: string;
  category: string;
  total: number;
  count: number;
};

export type Transaction = {
  id: string;
  source: string;
  source_email_id?: string | null;
  source_thread_id?: string | null;
  gmail_url?: string | null;
  transaction_date: string | null;
  amount: number | null;
  currency: string;
  direction: string;
  transaction_type: string;
  merchant_raw: string | null;
  merchant_normalized: string | null;
  description?: string | null;
  category_id?: string | null;
  subcategory_id?: string | null;
  category: string | null;
  subcategory: string | null;
  classification_confidence: number | null;
  classification_source: string;
  user_verified: boolean;
  needs_review: boolean;
  is_transfer?: boolean;
  is_refund?: boolean;
  excludes_from_spending?: boolean;
};

export type DataIssueType =
  | "wrong_amount"
  | "wrong_date"
  | "wrong_merchant"
  | "wrong_direction"
  | "not_a_transaction"
  | "duplicate"
  | "other";

export type DataIssueStatus = "open" | "resolved" | "dismissed";

export type DataIssue = {
  id: string;
  transaction_id: string;
  issue_type: DataIssueType;
  field_name: string | null;
  reported_value: string | null;
  suggested_value: string | null;
  note: string | null;
  status: DataIssueStatus;
  source: string | null;
  merchant_normalized: string | null;
  created_at: string | null;
  resolved_at: string | null;
  resolved_note: string | null;
  transaction: {
    id: string;
    merchant: string | null;
    amount: number | null;
    currency: string;
    transaction_date: string | null;
    source_email_id: string | null;
  } | null;
};

export type DataIssueSummaryGroup = {
  issue_type: DataIssueType;
  source: string | null;
  count: number;
  latest: string | null;
};

export type SystemStatus = {
  app: {
    name: string;
    host: string;
    port: number;
    data_dir: string;
    database_path: string;
    gmail_enabled: boolean;
    scheduler_enabled: boolean;
    allow_external_ai: boolean;
    currency: string;
  };
  database: {
    transaction_count: number;
    email_count: number;
  };
  gmail: {
    last_sync_at: string | null;
    connected: boolean;
    credentials_file?: string;
    credentials_file_present?: boolean;
  };
  last_ingestion_run: Record<string, unknown> | null;
};

export type GmailStatus = {
  enabled: boolean;
  connected: boolean;
  credentials_file: string;
  credentials_file_present: boolean;
  redirect_uri: string;
  scopes: string[];
  sync_after_date: string | null;
  initial_lookback_days: number;
  max_messages_per_sync: number;
};

export type CategoryTree = {
  id: string;
  name: string;
  slug: string;
  sort_order: number;
  is_system: boolean;
  transaction_count: number;
  subcategories: Array<{
    id: string;
    name: string;
    slug: string;
    sort_order: number;
  }>;
};

export type GmailMessageView = {
  id: string;
  thread_id: string | null;
  sender: string | null;
  subject: string | null;
  snippet: string | null;
  received_at: string | null;
  body_text: string;
  body_html: string | null;
  gmail_url: string | null;
  stored_locally: boolean;
};

export type IngestionResult = {
  run_id: string;
  status: string;
  emails_discovered: number;
  emails_processed: number;
  emails_skipped: number;
  transactions_extracted: number;
  transactions_duplicated: number;
  transactions_rejected: number;
  parsing_errors: number;
  auth_errors: number;
  error_summary: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  overview: () => request<Overview>("/api/overview"),
  byCategory: (year?: number, month?: number) => {
    let url = "/api/overview/by-category";
    if (year != null && month != null) url += `?year=${year}&month=${month}`;
    return request<{ items: CategorySpend[] }>(url);
  },
  incomeTrend: (months = 6) =>
    request<IncomeTrend>(`/api/overview/income-trend?months=${months}`),
  transactions: (
    params?: {
      needs_review?: boolean;
      direction?: "debit" | "credit";
      q?: string;
      date_from?: string;
      date_to?: string;
      limit?: number;
      offset?: number;
      sort_by?: "date" | "amount" | "merchant" | "category" | "source" | "status";
      sort_dir?: "asc" | "desc";
    },
    signal?: AbortSignal
  ) => {
    const qs = new URLSearchParams();
    if (params?.needs_review != null) qs.set("needs_review", String(params.needs_review));
    if (params?.direction) qs.set("direction", params.direction);
    if (params?.q) qs.set("q", params.q);
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    if (params?.limit != null) qs.set("limit", String(params.limit));
    if (params?.offset != null) qs.set("offset", String(params.offset));
    if (params?.sort_by) qs.set("sort_by", params.sort_by);
    if (params?.sort_dir) qs.set("sort_dir", params.sort_dir);
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<{ total: number; items: Transaction[] }>(`/api/transactions${suffix}`, { signal });
  },
  classifyTransaction: (id: string, body: { category_id: string; subcategory_id?: string | null }) =>
    request<Transaction>(`/api/transactions/${encodeURIComponent(id)}/classify`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  classifyTransactionsBulk: (body: {
    transaction_ids: string[];
    category_id: string;
    subcategory_id?: string | null;
  }) =>
    request<{ updated: number; items: Transaction[] }>("/api/transactions/classify-bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  excludeTransactions: (transactionIds: string[]) =>
    request<{ updated: number; items: Transaction[] }>("/api/transactions/exclude", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transaction_ids: transactionIds }),
    }),
  markReimbursed: (transactionIds: string[]) =>
    request<{ updated: number; items: Transaction[] }>("/api/transactions/reimbursed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transaction_ids: transactionIds }),
    }),
  flagIssue: (
    transactionId: string,
    body: {
      issue_type: DataIssueType;
      field_name?: string | null;
      suggested_value?: string | null;
      note?: string | null;
    }
  ) =>
    request<DataIssue>(`/api/transactions/${encodeURIComponent(transactionId)}/flag-issue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  flagIssuesBulk: (body: {
    transaction_ids: string[];
    issue_type: DataIssueType;
    field_name?: string | null;
    suggested_value?: string | null;
    note?: string | null;
  }) =>
    request<{ created: number; items: DataIssue[] }>("/api/transactions/flag-issue-bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  dataIssues: (params?: {
    status?: DataIssueStatus;
    issue_type?: DataIssueType;
    source?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.issue_type) qs.set("issue_type", params.issue_type);
    if (params?.source) qs.set("source", params.source);
    if (params?.limit != null) qs.set("limit", String(params.limit));
    if (params?.offset != null) qs.set("offset", String(params.offset));
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<{ total: number; items: DataIssue[] }>(`/api/data-issues${suffix}`);
  },
  dataIssuesSummary: (status: DataIssueStatus = "open") =>
    request<{ groups: DataIssueSummaryGroup[] }>(`/api/data-issues/summary?status=${status}`),
  resolveDataIssuesBulk: (body: {
    issue_ids: string[];
    status?: DataIssueStatus;
    resolved_note?: string | null;
  }) =>
    request<{ updated: number; items: DataIssue[] }>("/api/data-issues/resolve-bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  system: () => request<SystemStatus>("/api/system/status"),

  gmailStatus: () => request<GmailStatus>("/api/gmail/status"),
  installCredentials: (clientSecrets: Record<string, unknown>) =>
    request<{ installed: boolean; credentials_file: string }>("/api/gmail/credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_secrets: clientSecrets }),
    }),
  gmailAuthStart: () =>
    request<{ authorization_url: string; state: string }>("/api/gmail/auth/start", {
      method: "POST",
    }),
  gmailDisconnect: () =>
    request<{ disconnected: boolean; connected: boolean }>("/api/gmail/disconnect", {
      method: "POST",
    }),
  gmailSync: (opts?: { fullYear?: boolean; afterDate?: string; maxMessages?: number }) => {
    const qs = new URLSearchParams();
    if (opts?.fullYear) qs.set("full_year", "true");
    if (opts?.afterDate) qs.set("after_date", opts.afterDate);
    if (opts?.maxMessages != null) qs.set("max_messages", String(opts.maxMessages));
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<IngestionResult>(`/api/gmail/sync${suffix}`, { method: "POST" });
  },
  fetchGmailMessage: (messageId: string) =>
    request<GmailMessageView>(`/api/gmail/messages/${encodeURIComponent(messageId)}`),
  categories: () => request<{ items: CategoryTree[] }>("/api/categories"),
  createCategory: (name: string) =>
    request<CategoryTree>("/api/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  renameCategory: (id: string, name: string) =>
    request<CategoryTree>(`/api/categories/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  deleteCategory: (id: string) =>
    request<{ deleted: boolean }>(`/api/categories/${id}`, { method: "DELETE" }),
  createSubcategory: (categoryId: string, name: string) =>
    request<{ id: string; name: string }>(`/api/categories/${categoryId}/subcategories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  deleteSubcategory: (id: string) =>
    request<{ deleted: boolean }>(`/api/categories/subcategories/${id}`, { method: "DELETE" }),

};
