export interface Account {
  id: string;
  name: string;
  account_type: string;
  is_asset: boolean;
  is_liability: boolean;
  balance: number;
  raw_balance: number;
  currency: string;
  account_number_masked?: string;
  card_last4?: string;
  upi_identifier_masked?: string;
  credit_limit?: number;
  opening_balance?: number;
};

export type AccountsResponse = {
  net_worth: number;
  assets: number;
  liabilities: number;
  accounts: Account[];
};

export interface StatementProcessingEvent {
  id: string;
  stage: string;
  status: string;
  message: string | null;
  metadata: Record<string, any>;
  started_at: string | null;
  completed_at: string | null;
}

export interface StatementAccount {
  id: string;
  account_type: string;
  institution: string;
  account_identifier?: string | null;
  masked_identifier?: string | null;
  card_network?: string | null;
  account_name?: string | null;
  currency: string;
  opening_balance?: number | null;
  closing_balance?: number | null;
  credit_limit?: number | null;
  available_limit?: number | null;
  cash_withdrawal_limit?: number | null;
  attribution_confidence: string;
}

export interface StatementSummary {
  previous_balance?: number | null;
  payments?: number | null;
  refunds?: number | null;
  purchases?: number | null;
  cash_withdrawals?: number | null;
  fees?: number | null;
  interest?: number | null;
  other_charges?: number | null;
  total_due?: number | null;
  minimum_due?: number | null;
  statement_date?: string | null;
  due_date?: string | null;
  currency: string;
  extra_json?: Record<string, any>;
}

export interface StatementSection {
  id: string;
  section_type: string;
  page_start: number;
  page_end: number;
}

export interface StatementTransaction {
  id: string;
  statement_account_id?: string | null;
  transaction_date: string;
  transaction_time?: string | null;
  value_date?: string | null;
  description: string;
  reference_number?: string | null;
  transaction_type: string;
  amount: number;
  debit_amount?: number | null;
  credit_amount?: number | null;
  currency: string;
  running_balance?: number | null;
  source_page: number;
  source_row?: number | null;
  raw_text?: string | null;
  attribution_status: string;
  match_status: string;
  match_confidence?: number | null;
  match_reason?: string | null;
  matched_transaction_id?: string | null;
  matched_transaction?: {
    id: string;
    transaction_date: string | null;
    amount: number;
    currency?: string;
    direction: string;
    merchant_raw?: string | null;
    merchant_normalized?: string | null;
    category?: string | null;
    account?: string | null;
    card?: string | null;
    source?: string | null;
  } | null;
}

export interface ValidationEquation {
  name: string;
  formula: string;
  expected: number;
  calculated: number;
  difference: number;
  is_balanced: boolean;
}

export interface ValidationDetails {
  transaction_count?: number;
  account_count?: number;
  total_extracted_debits?: number;
  total_extracted_credits?: number;
  reported_purchases?: number | null;
  reported_payments?: number | null;
  reported_total_due?: number | null;
  equations?: ValidationEquation[];
  messages?: string[];
  warnings?: string[];
}

export interface CreditCardStatement {
  id: string;
  account_id: string | null;
  account_name: string | null;
  account_type?: string | null;
  account_number_masked?: string | null;
  source_email_id: string | null;
  source_attachment_id: string | null;
  gmail_url?: string | null;
  issuer: string;
  statement_type?: "CREDIT_CARD" | "BANK_ACCOUNT" | string;
  card_last4: string | null;
  statement_period_start: string | null;
  statement_period_end: string | null;
  statement_date: string | null;
  payment_due_date?: string | null;
  total_amount_due?: number | null;
  email_received_at?: string | null;
  original_filename: string;
  original_sha256: string | null;
  unlocked_sha256: string | null;
  has_original_file: boolean;
  has_unlocked_file: boolean;
  is_encrypted: boolean;
  password_strategy_id: string | null;
  status: string;
  validation_status?: string;
  validation_details?: ValidationDetails;
  parser_name?: string | null;
  parser_version?: string | null;
  discovered_at: string | null;
  downloaded_at: string | null;
  unlocked_at: string | null;
  created_at: string;
  updated_at: string;
  error_code: string | null;
  error_message: string | null;
  event_count?: number;
  events?: StatementProcessingEvent[];
  transaction_count?: number;
  statement_accounts?: StatementAccount[];
  summary?: StatementSummary | null;
  sections?: StatementSection[];
  transactions?: StatementTransaction[];
}

export interface PasswordProfile {
  configured: boolean;
  id?: string;
  account_id: string;
  account_name?: string;
  issuer: string;
  strategy: string;
  configuration: Record<string, any>;
  has_custom_password?: boolean;
  available_strategies: string[];
  created_at?: string | null;
  updated_at?: string | null;
}




export type Merchant = {
  id: string;
  display_name: string;
  canonical_name: string | null;
  normalized_key: string;
  default_category?: string | null;
  aliases: string[];
  total_spent?: number;
  spent_last_30d?: number;
  transaction_count?: number;
};

export type Subscription = {
  id: string;
  name: string;
  amount: number;
  billing_frequency: string;
  next_billing_date: string | null;
  status: string;
  annual_cost: number;
};

export type Bill = {
  id: string;
  name: string;
  expected_amount: number;
  due_date: string | null;
  frequency: string;
  status: string;
};

export interface AISuggestion {
  transaction_id: string;
  category_id: string;
  subcategory_id: string | null;
  category_name: string;
  subcategory_name: string | null;
  confidence: number;
  signals: string[];
  cached: boolean;
  provider: string;
  model: string;
  prompt_version: string;
  operation_id: string;
}

export type CategoryAnalyticsPeriod = {
  start: string;
  end: string;
  months: number;
  year: number;
  month: number;
  range: string;
};

export type CategoryAnalyticsSummary = {
  period_total_spend: number;
  previous_period_spend: number;
  period_change_pct: number | null;
  current_month_spend: number;
  previous_month_spend: number;
  current_month_mom_change_pct: number | null;
  transaction_count: number;
  avg_ticket: number;
  median_ticket: number;
  share_of_living_spend: number;
};

export type CategoryTrendMonth = {
  month: string;
  year: number;
  month_num: number;
  total: number;
  subcategories: Array<{
    id: string;
    name: string;
    slug: string;
    spend: number;
    count: number;
  }>;
};

export type CategorySubcategorySummary = {
  id: string;
  name: string;
  slug: string;
  spend: number;
  share_of_category: number;
  transaction_count: number;
  avg_ticket: number;
  current_month_spend: number;
  previous_month_spend: number;
  mom_change_pct: number | null;
  rolling_3m_avg: number;
};

export type CategoryMerchantSummary = {
  merchant_id: string | null;
  name: string;
  spend: number;
  transaction_count: number;
  share_of_category: number;
  avg_ticket: number;
};

export type CategoryConcentration = {
  top_1_share: number;
  top_3_share: number;
  top_5_share: number;
};

export type CategoryInsight = {
  type: string;
  severity: "info" | "positive" | "warning";
  title: string;
  message: string;
};

export type CategoryAnalytics = {
  category: {
    id: string;
    name: string;
    slug: string;
    expense_type: string | null;
  };
  period: CategoryAnalyticsPeriod;
  comparison: {
    type: string;
    start: string;
    end: string;
  };
  summary: CategoryAnalyticsSummary;
  trend: CategoryTrendMonth[];
  subcategories: CategorySubcategorySummary[];
  merchants: CategoryMerchantSummary[];
  concentration: CategoryConcentration;
  insights: CategoryInsight[];
};

export type Overview = {
  period: { year: number; month: number };
  currency: string;
  summary: {
    spent: number;
    consumer_spent?: number;
    commitments_spent?: number;
    income: number;
    net_cash_flow: number;
    transaction_count: number;
    debit_count: number;
    credit_count: number;
    total_recorded_count?: number;
    excluded_count?: number;
  };
  month_comparison: {
    spent_change_pct: number | null;
    income_change_pct: number | null;
    previous_spent: number;
    previous_income: number;
  };
  category_breakdown: Array<{
    category_id: string;
    category: string;
    expense_type?: string;
    total: number;
    previous_total: number;
    count: number;
    percentage: number;
  }>;
  daily_spending: Array<{
    date: string;
    spent: number;
    count?: number;
  }>;
  top_merchants: Array<{
    merchant: string;
    total: number;
    count: number;
  }>;
  largest_transactions: Array<{
    id: string;
    date: string;
    merchant: string | null;
    category: string | null;
    amount: number;
    account: string | null;
  }>;
  account_breakdown: Array<{
    account: string;
    total: number;
    percentage: number;
  }>;
  review: {
    needs_review_count: number;
    needs_review_amount: number;
  };
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

export type FinancialTrendPoint = {
  year: number;
  month: number;
  label: string;
  spent: number;
  income: number;
  net_cash_flow: number;
};

export type FinancialTrends = {
  months: number;
  currency: string;
  points: FinancialTrendPoint[];
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
  account?: string | null;
  card?: string | null;
  payment_method?: string | null;
  is_transfer?: boolean;
  is_refund?: boolean;
  excludes_from_spending?: boolean;
  classification_signals?: Record<string, any>;
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

export interface SystemStatus {
  app: {
    name: string;
    host: string;
    port: number;
    data_dir: string;
    database_path: string;
    gmail_enabled: boolean;
    scheduler_enabled: boolean;
    allow_external_ai: boolean;
    ai_enabled?: boolean;
    ai_provider?: string;
    ai_model?: string;
    ai_fallback_models?: string[];
    currency: string;
    upi_handles: string[];
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
  expense_type: string;
  transaction_count: number;
  subcategories: Array<{
    id: string;
    name: string;
    slug: string;
    sort_order: number;
  }>;
};

export type ClassificationRuleItem = {
  id: string;
  name: string | null;
  merchant_normalized: string | null;
  merchant_entity_id: string | null;
  upi_id: string | null;
  category_id: string;
  category_name: string;
  subcategory_id: string | null;
  subcategory_name: string | null;
  priority: number;
  is_active: boolean;
  hit_count: number;
  source: string;
  created_at: string | null;
  updated_at: string | null;
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

export type AuthStatus = {
  configured: boolean;
  authenticated: boolean;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("mymonee_auth_token") : null;
  const authHeaders: Record<string, string> = {};
  if (token) {
    authHeaders["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json", ...authHeaders, ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep status text
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  overview: (year?: number, month?: number) => {
    const qs = new URLSearchParams();
    if (year != null) qs.set("year", String(year));
    if (month != null) qs.set("month", String(month));
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<Overview>(`/api/overview${suffix}`);
  },
  byCategory: (year?: number, month?: number) => {
    let url = "/api/overview/by-category";
    if (year != null && month != null) url += `?year=${year}&month=${month}`;
    return request<{ items: CategorySpend[] }>(url);
  },
  incomeTrend: (months = 6) =>
    request<IncomeTrend>(`/api/overview/income-trend?months=${months}`),
  financialTrends: (months = 6, year?: number, month?: number) => {
    let url = `/api/overview/trends?months=${months}`;
    if (year != null && month != null) url += `&year=${year}&month=${month}`;
    return request<FinancialTrends>(url);
  },
  categoryAnalytics: (
    categoryId: string,
    params?: {
      range?: string;
      year?: number;
      month?: number;
    },
    signal?: AbortSignal
  ) => {
    const qs = new URLSearchParams();
    if (params?.range) qs.set("range", params.range);
    if (params?.year != null) qs.set("year", String(params.year));
    if (params?.month != null) qs.set("month", String(params.month));
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<CategoryAnalytics>(`/api/analytics/category/${encodeURIComponent(categoryId)}${suffix}`, { signal });
  },
  transactions: (
    params?: {
      needs_review?: boolean;
      direction?: "debit" | "credit";
      q?: string;
      date_from?: string;
      date_to?: string;
      merchant_id?: string;
      account?: string;
      status?: string;
      category_id?: string;
      category_ids?: string[];
      subcategory_id?: string;
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
    if (params?.account) qs.set("account", params.account);
    if (params?.status) qs.set("status", params.status);
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    if (params?.merchant_id) qs.set("merchant_id", params.merchant_id);
    if (params?.category_id) qs.set("category_id", params.category_id);
    if (params?.category_ids && params.category_ids.length > 0) {
      for (const cid of params.category_ids) {
        qs.append("category_ids", cid);
      }
    }
    if (params?.subcategory_id) qs.set("subcategory_id", params.subcategory_id);
    if (params?.limit != null) qs.set("limit", String(params.limit));
    if (params?.offset != null) qs.set("offset", String(params.offset));
    if (params?.sort_by) qs.set("sort_by", params.sort_by);
    if (params?.sort_dir) qs.set("sort_dir", params.sort_dir);
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<{
      total: number;
      total_amount?: number;
      total_debit?: number;
      total_credit?: number;
      items: Transaction[];
    }>(`/api/transactions${suffix}`, { signal });
  },
  getTransactionsByMerchant: (merchant_id: string) =>
    api.transactions({ merchant_id }),
  getAiSuggestion: (transactionId: string, forceRefresh?: boolean) =>
    request<AISuggestion>("/api/ai/classify-transaction", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transaction_id: transactionId, force_refresh: !!forceRefresh }),
    }),
  classifyTransaction: (
    id: string,
    body: {
      category_id: string;
      subcategory_id?: string | null;
      create_rule?: boolean;
      apply_to_past?: boolean;
    }
  ) =>
    request<Transaction>(`/api/transactions/${encodeURIComponent(id)}/classify`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  classifyTransactionsBulk: (body: {
    transaction_ids: string[];
    category_id: string;
    subcategory_id?: string | null;
    create_rule?: boolean;
  }) =>
    request<{ updated: number; items: Transaction[] }>("/api/transactions/classify-bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  getTransactionLinks: (id: string) =>
    request<{
      transaction_id: string;
      links: Array<{
        id: string;
        direction: "in" | "out";
        kind: string;
        confidence: number | null;
        notes: string | null;
        related_transaction: Transaction | null;
      }>;
    }>(`/api/transactions/${encodeURIComponent(id)}/links`),
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
  updateCategoryExpenseType: (id: string, expense_type: string) =>
    request<CategoryTree>(`/api/categories/${id}/expense_type`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expense_type }),
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
  rules: () => request<{ rules: ClassificationRuleItem[]; count: number }>("/api/rules"),
  updateRule: (
    id: string,
    patch: { is_active?: boolean; priority?: number; category_id?: string; subcategory_id?: string | null }
  ) =>
    request<{ ok: boolean; id: string; is_active?: boolean }>(`/api/rules/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteRule: (id: string) =>
    request<{ ok: boolean; deleted_id: string }>(`/api/rules/${id}`, { method: "DELETE" }),
  accounts: () => request<AccountsResponse>("/api/accounts"),
  createAccount: (data: Partial<Account>) =>
    request<{ id: string }>("/api/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  updateAccount: (id: string, data: Partial<Account>) =>
    request<{ id: string }>(`/api/accounts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteAccount: (id: string) =>
    request<{ deleted: boolean }>(`/api/accounts/${id}`, {
      method: "DELETE",
    }),
  getMerchants: () => request<{ items: Merchant[] }>("/api/merchants"),
  mergeMerchants: (merchant_ids: string[], canonical_name: string) =>
    request<{ status: string; canonical_id: string }>("/api/merchants/merge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ merchant_ids, canonical_name }),
    }),
  getRecurring: () => request<{ subscriptions: Subscription[], bills: Bill[], detected: any[] }>("/api/recurring"),
  createSubscription: (data: Partial<Subscription> & { transaction_id?: string }) =>
    request<{ id: string; subscription_id: string }>("/api/recurring/subscriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  createBill: (data: Partial<Bill> & { transaction_id?: string }) =>
    request<{ id: string; bill_id: string }>("/api/recurring/bills", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  authStatus: () => request<AuthStatus>("/api/auth/status"),
  authSetup: (pin: string) =>
    request<{ success: boolean; token: string }>("/api/auth/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    }),
  authLogin: (pin: string) =>
    request<{ success: boolean; token: string }>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    }),
  authLogout: () =>
    request<{ success: boolean }>("/api/auth/logout", { method: "POST" }),
  authChangePin: (old_pin: string, new_pin: string) =>
    request<{ success: boolean; token: string }>("/api/auth/change-pin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_pin, new_pin }),
    }),

  // Statements & Password Profiles (Statement Vault)
  statements: (params?: { account_id?: string; issuer?: string; status?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.account_id) query.set("account_id", params.account_id);
    if (params?.issuer) query.set("issuer", params.issuer);
    if (params?.status) query.set("status", params.status);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return request<{ statements: CreditCardStatement[]; total: number; limit: number; offset: number }>(
      `/api/statements${qs ? `?${qs}` : ""}`
    );
  },
  statement: (id: string) => request<CreditCardStatement>(`/api/statements/${id}`),
  discoverStatements: (max_messages: number = 50) =>
    request<{ discovered_count: number; statements: CreditCardStatement[] }>(
      `/api/statements/discover?max_messages=${max_messages}`,
      { method: "POST" }
    ),
  uploadStatement: (formData: FormData): Promise<CreditCardStatement> =>
    request<CreditCardStatement>("/api/statements/upload", {
      method: "POST",
      body: formData,
    }),
  unlockStatement: (
    id: string,
    payload: { password: string; save_to_profile?: boolean; strategy?: string }
  ) =>
    request<CreditCardStatement>(`/api/statements/${id}/unlock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  accountPasswordProfile: (accountId: string) =>
    request<PasswordProfile>(`/api/accounts/${accountId}/password-profile`),
  updateAccountPasswordProfile: (
    accountId: string,
    data: { issuer: string; strategy: string; configuration: Record<string, any> }
  ) =>
    request<{ success: boolean; id: string; issuer: string; strategy: string; configuration: Record<string, any> }>(
      `/api/accounts/${accountId}/password-profile`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }
    ),
  accountStatements: (accountId: string) =>
    request<{ account_id: string; account_name: string; statements: CreditCardStatement[] }>(
      `/api/accounts/${accountId}/statements`
    ),
  statementOriginalUrl: (id: string, download: boolean = false) =>
    `/api/statements/${id}/file/original${download ? "?download=true" : ""}`,
  statementUnlockedUrl: (id: string, download: boolean = false) =>
    `/api/statements/${id}/file/unlocked${download ? "?download=true" : ""}`,
  reExtractStatement: (id: string) =>
    request<CreditCardStatement>(`/api/statements/${id}/re-extract`, { method: "POST" }),
  batchExtractStatements: (limit: number = 100) =>
    request<{
      success: boolean;
      total_processed: number;
      validated_count: number;
      review_count: number;
      failed_count: number;
    }>(`/api/statements/batch-extract?limit=${limit}`, { method: "POST" }),
  reconcileStatement: (id: string) =>
    request<{ success: boolean; statement_id: string; reconciliation: any; statement: CreditCardStatement }>(
      `/api/statements/${id}/reconcile`,
      { method: "POST" }
    ),
  updateTransactionMatch: (
    statementId: string,
    transactionId: string,
    payload: { match_status: string; matched_transaction_id?: string | null; match_reason?: string | null }
  ) =>
    request<{ success: boolean; transaction_id: string; statement: CreditCardStatement }>(
      `/api/statements/${statementId}/transactions/${transactionId}/match`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    ),
  importStatementTransaction: (statementId: string, transactionId: string) =>
    request<{ success: boolean; transaction_id: string; ledger_transaction_id: string; statement: CreditCardStatement }>(
      `/api/statements/${statementId}/transactions/${transactionId}/import`,
      { method: "POST" }
    ),
  importStatementBundle: (statementId: string, transactionIds: string[]) =>
    request<{ success: boolean; imported_count: number; ledger_transaction_ids: string[]; statement: CreditCardStatement }>(
      `/api/statements/${statementId}/import-bundle`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transaction_ids: transactionIds }),
      }
    ),
  scanGmailForTransaction: (statementId: string, transactionId: string) =>
    request<{ success: boolean; found: boolean; rrn?: string; message: string; matched_transaction_id?: string; statement: CreditCardStatement }>(
      `/api/statements/${statementId}/transactions/${transactionId}/scan-gmail`,
      { method: "POST" }
    ),
  onboardingState: () =>
    request<{
      completed: boolean;
      current_step: number;
      auth_configured: boolean;
      gmail_connected: boolean;
      currency: string;
      locale: string;
      progress: Record<string, any>;
      discovered: {
        accounts: Array<{
          id: string;
          name: string;
          account_type: string;
          card_last4?: string | null;
          account_number_masked?: string | null;
          is_asset: boolean;
          is_liability: boolean;
          opening_balance?: number;
          payment_account_id?: string | null;
        }>;
        income_sources: Array<{
          name: string;
          amount: number;
          currency: string;
          account?: string | null;
          last_date?: string | null;
          expected_day: number;
        }>;
        recurring: Array<{
          id?: string | null;
          name: string;
          expected_amount: number;
          frequency: string;
          expected_day: number;
          status: string;
        }>;
      };
      metrics: {
        accounts_configured: number;
        transactions_ingested: number;
        needs_review_count: number;
      };
    }>("/api/onboarding/state"),
  onboardingFastScan: () =>
    request<{
      institutions: Array<{
        name: string;
        type: string;
        icon: string;
        status: string;
        sample_subject?: string | null;
      }>;
      emails_scanned: number;
    }>("/api/onboarding/fast-scan"),
  saveOnboardingStep: (step: number, payload: any) =>
    request<{ success: boolean; step: number; next_step: number }>(`/api/onboarding/step/${step}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }),
    }),
  onboardingStatus: () =>
    request<{
      completed: boolean;
      accounts_configured: number;
      transactions_ingested: number;
      recurring_configured: number;
      income_sources_configured: number;
    }>("/api/onboarding/status"),
  onboardingDiscover: () =>
    request<{
      accounts: Array<{
        id: string;
        name: string;
        account_type: string;
        card_last4?: string | null;
        account_number_masked?: string | null;
        is_asset: boolean;
        is_liability: boolean;
      }>;
      income_sources: Array<{
        name: string;
        amount: number;
        currency: string;
        account?: string | null;
        last_date?: string | null;
        expected_day: number;
      }>;
      recurring: Array<{
        id?: string | null;
        name: string;
        expected_amount: number;
        frequency: string;
        expected_day: number;
        status: string;
      }>;
    }>("/api/onboarding/discover"),
  completeOnboarding: (body: {
    primary_salary?: { name: string; expected_amount: number; frequency?: string } | null;
    recurring_items?: Array<{ name: string; expected_amount: number; frequency?: string; expected_day?: number }>;
  }) =>
    request<{
      success: boolean;
      completed: boolean;
      reconciliation: any;
      calibration?: {
        accounts_configured: number;
        transactions_ingested: number;
        recurring_configured: number;
        needs_review_count: number;
      };
    }>("/api/onboarding/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  resetOnboarding: () =>
    request<{ success: boolean; completed: boolean }>("/api/onboarding/reset", { method: "POST" }),
  dbHealth: () =>
    request<{
      healthy: boolean;
      integrity_ok: boolean;
      foreign_keys_ok: boolean;
      database_size_bytes: number;
      wal_size_bytes: number;
      total_disk_bytes: number;
      page_count: number;
      page_size: number;
      freelist_pages: number;
      fragmentation_pct: number;
      table_metrics: Record<string, number>;
    }>("/api/system/db-health"),
  dbVacuum: () =>
    request<{
      success: boolean;
      before_bytes: number;
      after_bytes: number;
      reclaimed_bytes: number;
      health: any;
    }>("/api/system/db-vacuum", { method: "POST" }),
  listBackups: () =>
    request<
      Array<{
        filename: string;
        path: string;
        size_bytes: number;
        created_at: string;
        integrity_verified: boolean;
        note?: string | null;
      }>
    >("/api/system/backups"),
  createBackup: (note?: string) =>
    request<{
      filename: string;
      created_at: string;
      size_bytes: number;
      integrity_verified: boolean;
      note?: string | null;
    }>("/api/system/backups/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    }),
  restoreBackup: (filename: string) =>
    request<{
      success: boolean;
      restored_file: string;
      safety_backup?: string | null;
      health: any;
    }>("/api/system/backups/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename }),
    }),
  deleteBackup: (filename: string) =>
    request<{ success: boolean; deleted: string }>(`/api/system/backups/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    }),
  getDuplicateCandidates: (lookbackDays = 90) =>
    request<
      Array<{
        primary_id: string;
        duplicate_id: string;
        confidence: number;
        reason: string;
        amount: number;
        currency: string;
        primary_merchant?: string | null;
        duplicate_merchant?: string | null;
        primary_date: string;
        duplicate_date: string;
        primary_source: string;
        duplicate_source: string;
        time_diff_seconds: number;
      }>
    >(`/api/intelligence/duplicates?lookback_days=${lookbackDays}`),
  mergeDuplicate: (primaryId: string, duplicateId: string) =>
    request<{ success: boolean; primary_id: string; duplicate_id: string }>("/api/intelligence/duplicates/merge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ primary_id: primaryId, duplicate_id: duplicateId }),
    }),
  unmarkDuplicate: (transactionId: string) =>
    request<{ success: boolean; transaction_id: string }>("/api/intelligence/duplicates/unmark", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transaction_id: transactionId }),
    }),
  getSpendingAnomalies: (lookbackDays = 60) =>
    request<
      Array<{
        id: string;
        anomaly_type: string;
        severity: "high" | "medium" | "low";
        title: string;
        description: string;
        amount: number;
        currency: string;
        transaction_id?: string | null;
        date: string;
        merchant?: string | null;
        category?: string | null;
        metadata: Record<string, any>;
      }>
    >(`/api/intelligence/anomalies?lookback_days=${lookbackDays}`),
};



