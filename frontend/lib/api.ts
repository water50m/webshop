// Resolve this in the browser, not while Next.js builds the bundle.  On a
// phone/tablet, localhost means that device itself; the page hostname is the
// computer that is actually running the backend.
const runtimeApiBaseUrl = () => {
  const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configuredApiBaseUrl) return configuredApiBaseUrl;
  const location = globalThis.location;
  // Production is served by the same Next.js origin, which proxies /api to
  // FastAPI.  Keep the explicit port for the local frontend dev server.
  if (location) {
    return location.port === "3000"
      ? `${location.protocol}//${location.hostname}:8000`
      : location.origin;
  }
  return "http://localhost:8000";
};

export const API_BASE_URL = runtimeApiBaseUrl();

const activeShopHeaders = (): Record<string, string> => {
  const shopId = typeof window === "undefined" ? null : window.localStorage.getItem("active-shop-id");
  return shopId ? { "X-Shop-ID": shopId } : {};
};

export function resolveImageUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  return url.startsWith("/") ? `${API_BASE_URL}${url}` : url;
}

export type Conversation = {
  id: number;
  channel_id: number;
  customer_id: number;
  customer_display_name: string;
  customer_profile_image_url: string;
  last_message_at: string;
  status: ConversationStatus;
  is_hidden: boolean;
  is_pinned: boolean;
  unread_count: number;
  bill_count: number;
  primary_label: string | null;
  payment_label: string | null;
  delivery_note: string;
  order_confirmed_at: string | null;
};

export type ConversationStatus = "open" | "waiting_reply" | "in_progress" | "done" | "spam";

export type HistoryPreparationStatus = {
  state: "waiting_for_token" | "ready";
  token_ready: boolean;
  page_id_ready: boolean;
  lookback_days: number;
  source: "facebook";
  analysis_only: boolean;
  sending_enabled: boolean;
  next_action: string;
};

export type HistoryAnalysisBatchSummary = {
  id: number;
  batch_number: number;
  status: "draft" | "approved";
  conversation_count: number;
  message_count: number;
  approved_at: string | null;
};

export type HistoryAnalysisPreparation = {
  id: number;
  status: "draft";
  conversation_count: number;
  message_count: number;
  batch_count: number;
  redaction_counts: Record<string, number>;
  created_at: string;
  batches: HistoryAnalysisBatchSummary[];
};

export type HistoryAnalysisBatch = HistoryAnalysisBatchSummary & {
  preparation_id: number;
  content: {
    conversations: {
      conversation: string;
      messages: { speaker: "customer" | "shop"; text: string }[];
    }[];
  };
};

export type ParserV2Item = {
  product_id: number;
  product_name: string;
  matched_text: string;
  quantity: number;
  packaging: "wrapped" | "box";
  match_source: "exact" | "alias" | "context";
  fallback_product_name?: string | null;
  substitution_from?: string | null;
};

export type ParserV2Result = {
  normalized_text: string;
  tokens: string[];
  intent: string;
  next_state: string;
  items: ParserV2Item[];
  handoff_reason: string | null;
  candidates: { matched_text: string; product_id: number; product_name: string; score: number }[];
  order_options: string[];
  answer_text: string | null;
  handoff_id: number | null;
  conversation_state?: ParserV2ConversationState;
};

export type ParserV2ConversationState = {
  conversation_id: number;
  state: string;
  last_items: { product_id: number; product_name: string; quantity: number; packaging: "wrapped" | "box" }[];
  delivery_context_confirmed: boolean;
  updated_at: string;
};

export type OrderOption = {
  id: number;
  name: string;
  stock_mode: "unlimited" | "tracked";
  stock_quantity: number;
  is_available: boolean;
};

export type ParserV2Handoff = {
  id: number;
  redacted_text: string;
  intent: string;
  reason: string;
  candidates: { items?: { matched_text: string; product_id: number; product_name: string; score: number }[] };
  status: "pending" | "resolved";
  resolution: string;
  resolved_at: string | null;
  created_at: string;
};

export type ProductAlias = {
  id: number;
  product_id: number;
  alias_text: string;
  status: "approved";
};

export type ParserV2HistorySummary = {
  preparation_id: number;
  approved_batch_count: number;
  customer_message_count: number;
  intent_counts: Record<string, number>;
  next_state_counts: Record<string, number>;
  handoff_reason_counts: Record<string, number>;
  matched_product_quantity: Record<string, number>;
  match_source_counts: Record<string, number>;
};

export type Message = {
  id: number;
  direction: "in" | "out";
  text: string;
  created_at: string;
  sent_by_display_name: string | null;
};

export type DraftOrderItem = {
  id: number;
  product_id: number | null;
  product_name: string | null;
  matched_text: string;
  quantity: number;
  unit_price: number;
  special_request: string;
};

export type DraftOrder = {
  id: number;
  conversation_id: number;
  status: "pending" | "confirmed" | "rejected";
  note: string;
  total: number;
  confirmed_at: string | null;
  confirmed_by_display_name: string | null;
  items: DraftOrderItem[];
};

export type FacebookPageChoice = {
  id: string;
  name: string;
  category: string;
  tasks: string[];
};

export type FacebookPendingConnection = {
  id: string;
  expires_at: string;
  pages: FacebookPageChoice[];
};

export type FacebookConnection = {
  id: number;
  page_id: string;
  name: string;
  shop_id: number;
  connected_at: string;
};

export type DataDeletionRequest = {
  confirmation_code: string;
  status: string;
  detail: string;
};

export type ChannelMember = {
  user_id: number;
  username: string;
  display_name: string;
  facebook_name: string;
  profile_picture_url: string;
  role: "page_owner" | "page_manager" | "page_staff" | "viewer";
  is_active: boolean;
};

export type ShopUserLookup = { id: number; username: string; display_name: string };
export type Shop = {
  id: number;
  name: string;
  role: "owner" | "manager" | "staff";
  facebook_page_name: string | null;
  facebook_page_id: string | null;
};

export type InboxMessageEvent = {
  conversation: Conversation;
  message: Message;
  draft_order: DraftOrder | null;
};

export type ChatOrderHistoryItem = {
  product_name: string;
  quantity: number;
  unit_price: number;
};

export type ChatOrderHistoryOrder = {
  id: number;
  confirmed_at: string;
  total: number;
  items: ChatOrderHistoryItem[];
};

export type ChatOrderHistoryCustomer = {
  customer_id: number;
  customer_display_name: string;
  order_count: number;
  total_spent: number;
  last_order_at: string;
  orders: ChatOrderHistoryOrder[];
};

export type ExpenseCategory =
  | "cost_of_goods"
  | "shipping"
  | "rent"
  | "utilities"
  | "marketing"
  | "other";

export type Expense = {
  id: number;
  category: ExpenseCategory;
  amount: number;
  description: string;
  expense_date: string;
};

export type ShopType = "individual" | "juristic";
export type InventoryMode = "simple" | "recipe";

export type OrderParserMode = "algorithm" | "ai";

export type ShopSettings = {
  shop_type: ShopType;
  shop_name: string;
  address: string;
  tax_id: string;
  promptpay_id: string;
  loyalty_baht_per_point: number;
  low_stock_line_token: string;
  low_stock_line_target_id: string;
  receipt_printer_ip: string;
  receipt_printer_port: number;
  inventory_mode: InventoryMode;
  order_parser_mode: OrderParserMode;
  ai_api_key: string;
  menu_answer_format: "text" | "image";
};

export type PrintBridge = {
  id: number;
  name: string;
  is_online: boolean;
  last_seen_at: string | null;
  wifi_ssid: string;
  wifi_rssi: number | null;
  printer_connected: boolean;
  printer_name: string;
  printer_address: string;
  printer_error: string;
  firmware_version: string;
};

export type CreatedPrintBridge = PrintBridge & { device_token: string };

export type PrintBridgeCommand = {
  id: number;
  command: string;
  status: "pending" | "delivered" | "succeeded" | "failed";
  result: Record<string, unknown>;
  created_at: string;
};

export type Ingredient = {
  id: number;
  name: string;
  unit: string;
  stock_quantity: number;
  low_stock_threshold: number;
};

export type RecipeItem = {
  id: number;
  ingredient_id: number;
  ingredient_name: string;
  unit: string;
  quantity_per_unit: number;
};

export type StocktakeLine = {
  id: number;
  product_id: number | null;
  ingredient_id: number | null;
  name: string;
  unit: string;
  expected_quantity: number;
  counted_quantity: number | null;
};

export type StocktakeSession = {
  id: number;
  status: "open" | "closed";
  entity_type: "product" | "ingredient";
  opened_by_name: string;
  opened_at: string;
  closed_by_name: string | null;
  closed_at: string | null;
  note: string;
  lines: StocktakeLine[];
};

export type StocktakeCloseResult = {
  session: StocktakeSession;
  adjusted_count: number;
  skipped_count: number;
};

export type ProductModifier = {
  id: number;
  name: string;
  price_delta: number;
};

export type Product = {
  id: number;
  sku: string;
  name: string;
  category: string;
  price: number;
  cost_price: number;
  stock_quantity: number;
  stock_mode: "tracked" | "unlimited";
  is_available: boolean;
  low_stock_threshold: number;
  image_url: string | null;
  show_in_menu_answer: boolean;
  discounted_price: number | null;
  modifiers: ProductModifier[];
};

export type SaleStatus = "held" | "completed" | "voided";
export type PaymentMethod = "cash" | "transfer";

export type SaleItemModifier = {
  name: string;
  price_delta: number;
};

export type SaleItem = {
  id: number;
  product_id: number | null;
  product_name: string;
  sku: string;
  quantity: number;
  unit_price: number;
  discount_amount: number;
  refunded_quantity: number;
  modifiers: SaleItemModifier[];
  line_total: number;
};

export type SalePayment = {
  method: PaymentMethod;
  amount: number;
};

export type Sale = {
  id: number;
  receipt_no: number | null;
  status: SaleStatus;
  payment_method: PaymentMethod | null;
  discount_amount: number;
  paid_amount: number | null;
  change_amount: number | null;
  note: string;
  created_by_name: string | null;
  completed_at: string | null;
  items: SaleItem[];
  payments: SalePayment[];
  subtotal: number;
  total_discount: number;
  promotion_discount: number;
  total: number;
  customer_phone: string | null;
  customer_name: string | null;
  points_earned: number;
  points_redeemed: number;
  customer_points_balance: number | null;
};

export type Customer = {
  id: number;
  phone: string;
  name: string;
  points: number;
};

export type Supplier = {
  id: number;
  name: string;
  phone: string;
  address: string;
  note: string;
};

export type PurchaseOrderStatus = "draft" | "ordered" | "received" | "cancelled";

export type PurchaseOrderItem = {
  id: number;
  product_id: number | null;
  product_name: string;
  quantity: number;
  unit_cost: number;
};

export type PurchaseOrder = {
  id: number;
  supplier_id: number;
  supplier_name: string;
  status: PurchaseOrderStatus;
  note: string;
  created_at: string;
  received_at: string | null;
  items: PurchaseOrderItem[];
  total_cost: number;
};

export type Shift = {
  id: number;
  opened_by_name: string;
  opening_cash: number;
  opened_at: string;
  closed_by_name: string | null;
  closing_cash_counted: number | null;
  closed_at: string | null;
  note: string;
};

export type ShiftSummary = {
  sale_count: number;
  total_revenue: number;
  totals_by_method: Record<string, number>;
  opening_cash: number;
  expected_cash: number;
  closing_cash_counted: number | null;
  cash_difference: number | null;
};

export type PromotionType = "time_discount" | "bundle";
export type DiscountType = "percent" | "amount";

export type PromotionItem = {
  id: number;
  product_id: number;
  product_name: string;
  quantity: number;
};

export type Promotion = {
  id: number;
  name: string;
  type: PromotionType;
  is_active: boolean;
  is_active_now: boolean;
  discount_type: DiscountType | null;
  discount_value: number | null;
  bundle_price: number | null;
  start_at: string | null;
  end_at: string | null;
  items: PromotionItem[];
};

export type SaleAuditLog = {
  id: number;
  sale_id: number;
  receipt_no: number | null;
  action: "void" | "refund";
  user_name: string | null;
  note: string;
  created_at: string;
};

export type PromotionIn = {
  name: string;
  type: PromotionType;
  is_active?: boolean;
  discount_type?: DiscountType | null;
  discount_value?: number | null;
  bundle_price?: number | null;
  start_at?: string | null;
  end_at?: string | null;
  items: { product_id: number; quantity: number }[];
};

export type LowStockProduct = {
  id: number;
  name: string;
  sku: string;
  stock_quantity: number;
  low_stock_threshold: number;
};

export type OpenShift = {
  id: number;
  opened_by_name: string;
  opening_cash: number;
  opened_at: string;
};

export type TodaySummary = {
  sale_count: number;
  total_revenue: number;
  low_stock_products: LowStockProduct[];
  open_shifts: OpenShift[];
};

export type ProductPerformance = {
  product_id: number | null;
  name: string;
  sku: string;
  quantity_sold: number;
  revenue: number;
};

export type ReportSummary = {
  year: number;
  month: number | null;
  income: number;
  cogs: number;
  gross_profit: number;
  expense_breakdown: Record<ExpenseCategory, number>;
  total_expense: number;
  net_profit: number;
  shop_type: ShopType;
  tax_estimate: number;
  tax_disclaimer: string;
};

export type DailyReportDay = {
  date: string;
  income: number;
  expense: number;
  order_count: number;
  top_product_quantities: Record<string, number>;
};

export type AllTimeTopProduct = {
  name: string;
  sku: string;
  quantity_sold: number;
};

export type ReportOrder = {
  id: number;
  receipt_no: number | null;
  completed_at: string;
  revenue: number;
  source: "pos" | "chat";
  reference: string;
};

export type DailyReport = {
  days: DailyReportDay[];
  top_products: AllTimeTopProduct[];
  orders: ReportOrder[];
};

export type DbEngine = "sqlite" | "postgres";

export type DbConfig = {
  engine: DbEngine;
  sqlite_path: string;
  postgres_url: string;
  env_override: boolean;
};

export type DbConfigIn = {
  engine: DbEngine;
  sqlite_path: string;
  postgres_url: string;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...activeShopHeaders(), ...(init?.headers ?? {}) },
    cache: "no-store",
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.text();
    let detail = body;
    try {
      detail = JSON.parse(body).detail ?? body;
    } catch {
      // body wasn't JSON, keep raw text
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export type UserRole = "owner" | "manager" | "cashier";

export type AuthUser = {
  id: number;
  username: string;
  display_name: string;
  role: UserRole;
  has_pin: boolean;
  has_facebook_identity: boolean;
};

export type FacebookOnboardingPage = {
  id: string;
  name: string;
  registered: boolean;
  channel_id: number | null;
  shop_id: number | null;
};

export type FacebookOnboardingPending = { id: string; pages: FacebookOnboardingPage[] };

export type UserIn = {
  username: string;
  password: string;
  display_name?: string;
  role?: UserRole;
};

export type UserUpdateIn = {
  display_name: string;
  role: UserRole;
  password?: string | null;
};

export const api = {
  health: () => request<{ status: string }>("/health"),
  startFacebookLogin: () => request<{ authorization_url: string }>("/api/auth/facebook/start", { method: "POST" }),
  getFacebookLoginPending: (attemptId: string) => request<FacebookOnboardingPending>(`/api/auth/facebook/pending/${attemptId}`),
  registerFacebookLoginPage: (attemptId: string, pageId: string) => request<FacebookOnboardingPage>(`/api/auth/facebook/pending/${attemptId}/register`, { method: "POST", body: JSON.stringify({ page_id: pageId }) }),
  selectFacebookLoginPage: (attemptId: string, pageId: string) => request<FacebookOnboardingPage>(`/api/auth/facebook/pending/${attemptId}/select`, { method: "POST", body: JSON.stringify({ page_id: pageId }) }),
  listShops: () => request<Shop[]>("/api/shops"),
  createShop: (name: string) => request<Shop>("/api/shops", { method: "POST", body: JSON.stringify({ name }) }),
  inboxEventsUrl: () => `${API_BASE_URL}/api/events/inbox`,
  getHistoryPreparationStatus: () => request<HistoryPreparationStatus>("/api/history-preparation/status"),
  listHistoryAnalysisPreparations: () =>
    request<HistoryAnalysisPreparation[]>("/api/history-preparation/analysis-preparations"),
  createHistoryAnalysisPreparation: () =>
    request<HistoryAnalysisPreparation>("/api/history-preparation/analysis-preparations", { method: "POST", body: "{}" }),
  getHistoryAnalysisBatch: (id: number) =>
    request<HistoryAnalysisBatch>(`/api/history-preparation/analysis-batches/${id}`),
  approveHistoryAnalysisBatch: (id: number) =>
    request<HistoryAnalysisBatch>(`/api/history-preparation/analysis-batches/${id}/approve`, { method: "POST" }),
  testParserV2: (text: string) => request<ParserV2Result>("/api/parser-v2/test", { method: "POST", body: JSON.stringify({ text }) }),
  testParserV2ConversationTurn: (conversationId: number, text: string) =>
    request<ParserV2Result>("/api/parser-v2/conversation-turn", {
      method: "POST",
      body: JSON.stringify({ conversation_id: conversationId, text }),
    }),
  confirmParserV2DeliveryContext: (conversationId: number) =>
    request<ParserV2ConversationState>(`/api/parser-v2/conversations/${conversationId}/confirm-delivery-context`, { method: "POST" }),
  resetParserV2ConversationState: (conversationId: number) =>
    request<ParserV2ConversationState>(`/api/parser-v2/conversations/${conversationId}/reset-state`, { method: "POST" }),
  getParserV2HistorySummary: () => request<ParserV2HistorySummary>("/api/parser-v2/history-summary"),
  listParserV2Handoffs: () => request<ParserV2Handoff[]>("/api/parser-v2/handoffs"),
  resolveParserV2Handoff: (id: number, resolution: string) =>
    request<ParserV2Handoff>(`/api/parser-v2/handoffs/${id}/resolve`, { method: "POST", body: JSON.stringify({ resolution }) }),
  listProductAliases: () => request<ProductAlias[]>("/api/parser-v2/aliases"),
  createProductAlias: (productId: number, aliasText: string) =>
    request<ProductAlias>("/api/parser-v2/aliases", { method: "POST", body: JSON.stringify({ product_id: productId, alias_text: aliasText }) }),
  listOrderOptions: () => request<OrderOption[]>("/api/parser-v2/options"),
  setOrderOptionAvailability: (id: number, isAvailable: boolean) =>
    request<OrderOption>(`/api/parser-v2/options/${id}`, { method: "PATCH", body: JSON.stringify({ is_available: isAvailable }) }),

  login: (username: string, password: string) =>
    request<AuthUser>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  unlock: (username: string, pin: string) =>
    request<AuthUser>("/api/auth/unlock", { method: "POST", body: JSON.stringify({ username, pin }) }),
  setPin: (pin: string) => request<{ ok: boolean }>("/api/auth/set-pin", { method: "POST", body: JSON.stringify({ pin }) }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  me: () => request<AuthUser>("/api/auth/me"),
  startFacebookAccountPages: () => request<{ authorization_url: string }>("/api/auth/facebook/pages/start", { method: "POST" }),
  getFacebookAccountPages: (attemptId: string) => request<FacebookOnboardingPending>(`/api/auth/facebook/pages/pending/${attemptId}`),
  registerFacebookAccountPage: (attemptId: string, pageId: string) =>
    request<FacebookOnboardingPage>(`/api/auth/facebook/pages/pending/${attemptId}/register`, { method: "POST", body: JSON.stringify({ page_id: pageId }) }),

  listUsers: () => request<AuthUser[]>("/api/users"),
  createUser: (user: UserIn) => request<AuthUser>("/api/users", { method: "POST", body: JSON.stringify(user) }),
  updateUser: (id: number, user: UserUpdateIn) =>
    request<AuthUser>(`/api/users/${id}`, { method: "PUT", body: JSON.stringify(user) }),
  deleteUser: (id: number) => request<{ ok: boolean }>(`/api/users/${id}`, { method: "DELETE" }),

  listConversations: (filters?: { status?: ConversationStatus; visibility?: "active" | "hidden" | "all"; channelId?: number }) => {
    const params = new URLSearchParams();
    if (filters?.status) params.set("status", filters.status);
    if (filters?.visibility) params.set("visibility", filters.visibility);
    if (filters?.channelId) params.set("channel_id", String(filters.channelId));
    const query = params.toString();
    return request<Conversation[]>(`/api/conversations${query ? `?${query}` : ""}`);
  },
  updateConversation: (conversationId: number, update: Partial<Pick<Conversation, "status" | "is_hidden" | "is_pinned" | "primary_label" | "payment_label" | "delivery_note">>) =>
    request<Conversation>(`/api/conversations/${conversationId}`, {
      method: "PATCH",
      body: JSON.stringify(update),
    }),
  sendDelivery: (conversationId: number) =>
    request<Conversation>(`/api/conversations/${conversationId}/send-delivery`, { method: "POST" }),
  sendConversationMessage: (conversationId: number, text: string) =>
    request<{ conversation: Conversation; message: Message }>(`/api/conversations/${conversationId}/send-message`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  sendConversationPhoto: async (conversationId: number, photo: Blob) => {
    const form = new FormData();
    form.append("photo", photo, "shop-photo.jpg");
    const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}/send-photo`, {
      method: "POST",
      body: form,
      cache: "no-store",
      credentials: "include",
      headers: activeShopHeaders(),
    });
    if (!response.ok) {
      const body = await response.text();
      let detail = body;
      try { detail = JSON.parse(body).detail ?? body; } catch { /* retain non-JSON response */ }
      throw new ApiError(response.status, detail || "ส่งรูปไม่สำเร็จ");
    }
    return response.json() as Promise<Conversation>;
  },
  markConversationRead: (conversationId: number) =>
    request<Conversation>(`/api/conversations/${conversationId}/mark-read`, { method: "POST" }),
  listMessages: (conversationId: number) =>
    request<Message[]>(`/api/conversations/${conversationId}/messages`),
  listDraftOrders: (status?: string) =>
    request<DraftOrder[]>(`/api/draft-orders${status ? `?status=${status}` : ""}`),
  createManualDraftOrder: (payload: { conversation_id: number; items: { product_id: number; quantity: number; unit_price?: number }[] }) =>
    request<DraftOrder>("/api/draft-orders", { method: "POST", body: JSON.stringify(payload) }),
  listChatOrderHistory: () => request<ChatOrderHistoryCustomer[]>("/api/order-history"),
  getDraftOrder: (id: number) => request<DraftOrder>(`/api/draft-orders/${id}`),
  updateDraftOrder: (id: number, payload: { note?: string; items?: { product_id: number; quantity: number; unit_price?: number }[] }) =>
    request<DraftOrder>(`/api/draft-orders/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  confirmDraftOrder: (id: number) =>
    request<DraftOrder>(`/api/draft-orders/${id}/confirm`, { method: "POST" }),
  rejectDraftOrder: (id: number) =>
    request<DraftOrder>(`/api/draft-orders/${id}/reject`, { method: "POST" }),
  startFacebookConnection: () =>
    request<{ authorization_url: string }>("/api/meta/facebook/connections/start", { method: "POST" }),
  getPendingFacebookConnection: (attemptId: string) =>
    request<FacebookPendingConnection>(`/api/meta/facebook/connections/pending/${attemptId}`),
  selectFacebookPage: (attemptId: string, pageId: string) =>
    request<FacebookConnection>(`/api/meta/facebook/connections/pending/${attemptId}/select`, {
      method: "POST",
      body: JSON.stringify({ page_id: pageId }),
    }),
  listFacebookConnections: () => request<FacebookConnection[]>("/api/meta/facebook/connections"),
  disconnectFacebookPage: (channelId: number) =>
    request<{ ok: boolean }>(`/api/meta/facebook/connections/${channelId}`, { method: "DELETE" }),
  deleteFacebookPageData: (channelId: number) =>
    request<DataDeletionRequest>(`/api/meta/facebook/connections/${channelId}/data`, {
      method: "DELETE",
      body: JSON.stringify({ confirmation: true }),
    }),
  createFacebookDataDeletionRequest: (payload: { page_id: string; requester_email?: string; requester_name?: string }) =>
    request<DataDeletionRequest>("/api/meta/facebook/data-deletion-requests", { method: "POST", body: JSON.stringify(payload) }),
  getFacebookDataDeletionRequest: (code: string) =>
    request<DataDeletionRequest>(`/api/meta/facebook/data-deletion-requests/${encodeURIComponent(code)}`),
  listChannelMembers: (channelId: number) => request<ChannelMember[]>(`/api/channels/${channelId}/members`),
  findChannelShopUser: (channelId: number, username: string) => request<ShopUserLookup>(`/api/channels/${channelId}/users?username=${encodeURIComponent(username)}`),
  grantChannelMember: (channelId: number, userId: number, role: ChannelMember["role"]) =>
    request<ChannelMember>(`/api/channels/${channelId}/members`, { method: "PUT", body: JSON.stringify({ user_id: userId, role }) }),
  revokeChannelMember: (channelId: number, userId: number) =>
    request<{ ok: boolean }>(`/api/channels/${channelId}/members/${userId}`, { method: "DELETE" }),
  listExpenses: () => request<Expense[]>("/api/expenses"),
  createExpense: (expense: Omit<Expense, "id">) =>
    request<Expense>("/api/expenses", { method: "POST", body: JSON.stringify(expense) }),
  deleteExpense: (id: number) =>
    request<{ ok: boolean }>(`/api/expenses/${id}`, { method: "DELETE" }),
  getSettings: () => request<ShopSettings>("/api/settings"),
  updateSettings: (settings: ShopSettings) =>
    request<ShopSettings>("/api/settings", { method: "PUT", body: JSON.stringify(settings) }),
  listPrintBridges: () => request<PrintBridge[]>("/api/bridges"),
  createPrintBridge: (name: string) =>
    request<CreatedPrintBridge>("/api/bridges", { method: "POST", body: JSON.stringify({ name }) }),
  listPrintBridgeCommands: (id: number) => request<PrintBridgeCommand[]>(`/api/bridges/${id}/commands`),
  sendPrintBridgeCommand: (id: number, command: string, payload: Record<string, unknown> = {}) =>
    request<PrintBridgeCommand>(`/api/bridges/${id}/commands`, { method: "POST", body: JSON.stringify({ command, payload }) }),
  getPromptPayQr: (amount?: number) =>
    request<{ payload: string }>(`/api/settings/promptpay-qr${amount !== undefined ? `?amount=${amount}` : ""}`),
  getReportSummary: (year: number, month?: number) =>
    request<ReportSummary>(`/api/reports/summary?year=${year}${month ? `&month=${month}` : ""}`),
  getTodaySummary: () => request<TodaySummary>("/api/reports/today"),
  getProductPerformance: (start: string, end: string) =>
    request<ProductPerformance[]>(`/api/reports/products?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  getDailyReport: (start: string, end: string) =>
    request<DailyReport>(`/api/reports/daily?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  listSaleAuditLogs: (params: { start?: string; end?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.start) qs.set("start", params.start);
    if (params.end) qs.set("end", params.end);
    return request<SaleAuditLog[]>(`/api/audit/sales${qs.toString() ? `?${qs.toString()}` : ""}`);
  },

  listProducts: (search?: string, lowStock?: boolean, category?: string) => {
    const qs = new URLSearchParams();
    if (search) qs.set("search", search);
    if (lowStock) qs.set("low_stock", "true");
    if (category) qs.set("category", category);
    return request<Product[]>(`/api/products${qs.toString() ? `?${qs.toString()}` : ""}`);
  },
  listCategories: () => request<string[]>("/api/products/categories"),
  lookupProduct: (code: string) =>
    request<Product>(`/api/products/lookup?code=${encodeURIComponent(code)}`),
  createProduct: (product: Omit<Product, "id" | "stock_quantity" | "discounted_price" | "modifiers">) =>
    request<Product>("/api/products", { method: "POST", body: JSON.stringify(product) }),
  updateProduct: (id: number, product: Omit<Product, "id" | "stock_quantity" | "discounted_price" | "modifiers">) =>
    request<Product>(`/api/products/${id}`, { method: "PUT", body: JSON.stringify(product) }),
  uploadProductImage: async (id: number, file: File): Promise<Product> => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE_URL}/api/products/${id}/image`, {
      method: "POST",
      body: formData,
      credentials: "include",
      headers: activeShopHeaders(),
    });
    if (!res.ok) {
      const body = await res.text();
      let detail = body;
      try {
        detail = JSON.parse(body).detail ?? body;
      } catch {
        // body wasn't JSON, keep raw text
      }
      throw new ApiError(res.status, detail || `Request failed (${res.status})`);
    }
    return res.json() as Promise<Product>;
  },
  adjustStock: (id: number, change: number, note: string = "") =>
    request<Product>(`/api/products/${id}/stock-adjustment`, {
      method: "POST",
      body: JSON.stringify({ change, note }),
    }),
  restockAllProducts: () => request<{ adjusted_count: number; change_per_product: number }>("/api/products/restock-all", { method: "POST" }),
  createModifier: (productId: number, payload: { name: string; price_delta: number }) =>
    request<Product>(`/api/products/${productId}/modifiers`, { method: "POST", body: JSON.stringify(payload) }),
  updateModifier: (productId: number, modifierId: number, payload: { name: string; price_delta: number }) =>
    request<Product>(`/api/products/${productId}/modifiers/${modifierId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deleteModifier: (productId: number, modifierId: number) =>
    request<Product>(`/api/products/${productId}/modifiers/${modifierId}`, { method: "DELETE" }),

  listHeldSales: () => request<Sale[]>("/api/pos/sales?status=held"),
  listSalesHistory: (params: { start?: string; end?: string; status?: string; receipt_no?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.start) qs.set("start", params.start);
    if (params.end) qs.set("end", params.end);
    if (params.status) qs.set("status", params.status);
    if (params.receipt_no) qs.set("receipt_no", String(params.receipt_no));
    return request<Sale[]>(`/api/pos/sales${qs.toString() ? `?${qs.toString()}` : ""}`);
  },
  createSale: () => request<Sale>("/api/pos/sales", { method: "POST" }),
  getSale: (id: number) => request<Sale>(`/api/pos/sales/${id}`),
  updateSale: (id: number, payload: { discount_amount?: number; note?: string }) =>
    request<Sale>(`/api/pos/sales/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  addSaleItem: (
    id: number,
    payload: { code?: string; product_id?: number; quantity?: number; modifier_ids?: number[] }
  ) => request<Sale>(`/api/pos/sales/${id}/items`, { method: "POST", body: JSON.stringify(payload) }),
  updateSaleItem: (id: number, itemId: number, payload: { quantity?: number; discount_amount?: number }) =>
    request<Sale>(`/api/pos/sales/${id}/items/${itemId}`, { method: "PUT", body: JSON.stringify(payload) }),
  removeSaleItem: (id: number, itemId: number) =>
    request<Sale>(`/api/pos/sales/${id}/items/${itemId}`, { method: "DELETE" }),
  checkoutSale: (
    id: number,
    payments: { method: PaymentMethod; amount: number }[],
    options: { customer_phone?: string; customer_name?: string; redeem_points?: number } = {}
  ) =>
    request<Sale>(`/api/pos/sales/${id}/checkout`, {
      method: "POST",
      body: JSON.stringify({ payments, ...options }),
    }),
  voidSale: (id: number) => request<Sale>(`/api/pos/sales/${id}/void`, { method: "POST" }),
  refundSale: (id: number, items: { item_id: number; quantity: number }[], note: string = "") =>
    request<Sale>(`/api/pos/sales/${id}/refund`, { method: "POST", body: JSON.stringify({ items, note }) }),
  printReceiptThermal: (id: number) =>
    request<{ ok: boolean; detail: string }>(`/api/pos/sales/${id}/print-thermal`, { method: "POST" }),

  getCurrentShift: () => request<Shift | null>("/api/shifts/current"),
  openShift: (opening_cash: number, note: string = "") =>
    request<Shift>("/api/shifts/open", { method: "POST", body: JSON.stringify({ opening_cash, note }) }),
  closeShift: (id: number, closing_cash_counted: number, note: string = "") =>
    request<Shift>(`/api/shifts/${id}/close`, {
      method: "POST",
      body: JSON.stringify({ closing_cash_counted, note }),
    }),
  getShiftSummary: (id: number) => request<ShiftSummary>(`/api/shifts/${id}/summary`),

  listPromotions: () => request<Promotion[]>("/api/promotions"),
  createPromotion: (promotion: PromotionIn) =>
    request<Promotion>("/api/promotions", { method: "POST", body: JSON.stringify(promotion) }),
  updatePromotion: (id: number, promotion: PromotionIn) =>
    request<Promotion>(`/api/promotions/${id}`, { method: "PUT", body: JSON.stringify(promotion) }),
  togglePromotion: (id: number) =>
    request<Promotion>(`/api/promotions/${id}/toggle`, { method: "POST" }),

  listCustomers: (search?: string) =>
    request<Customer[]>(`/api/customers${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  lookupCustomer: (phone: string) =>
    request<Customer>(`/api/customers/lookup?phone=${encodeURIComponent(phone)}`),
  createCustomer: (payload: { phone: string; name?: string }) =>
    request<Customer>("/api/customers", { method: "POST", body: JSON.stringify(payload) }),
  updateCustomer: (id: number, payload: { phone: string; name?: string }) =>
    request<Customer>(`/api/customers/${id}`, { method: "PUT", body: JSON.stringify(payload) }),

  listSuppliers: () => request<Supplier[]>("/api/suppliers"),
  createSupplier: (payload: Omit<Supplier, "id">) =>
    request<Supplier>("/api/suppliers", { method: "POST", body: JSON.stringify(payload) }),
  updateSupplier: (id: number, payload: Omit<Supplier, "id">) =>
    request<Supplier>(`/api/suppliers/${id}`, { method: "PUT", body: JSON.stringify(payload) }),

  listPurchaseOrders: (status?: string) =>
    request<PurchaseOrder[]>(`/api/purchase-orders${status ? `?status=${status}` : ""}`),
  createPurchaseOrder: (payload: {
    supplier_id: number;
    note?: string;
    items: { product_id: number; quantity: number; unit_cost: number }[];
  }) => request<PurchaseOrder>("/api/purchase-orders", { method: "POST", body: JSON.stringify(payload) }),
  receivePurchaseOrder: (id: number) =>
    request<PurchaseOrder>(`/api/purchase-orders/${id}/receive`, { method: "POST" }),
  cancelPurchaseOrder: (id: number) =>
    request<PurchaseOrder>(`/api/purchase-orders/${id}/cancel`, { method: "POST" }),

  listIngredients: () => request<Ingredient[]>("/api/ingredients"),
  createIngredient: (payload: { name: string; unit?: string; low_stock_threshold?: number }) =>
    request<Ingredient>("/api/ingredients", { method: "POST", body: JSON.stringify(payload) }),
  updateIngredient: (id: number, payload: { name: string; unit?: string; low_stock_threshold?: number }) =>
    request<Ingredient>(`/api/ingredients/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteIngredient: (id: number) => request<{ ok: boolean }>(`/api/ingredients/${id}`, { method: "DELETE" }),
  adjustIngredientStock: (id: number, change: number, note: string = "") =>
    request<Ingredient>(`/api/ingredients/${id}/stock-adjustment`, {
      method: "POST",
      body: JSON.stringify({ change, note }),
    }),

  getProductRecipe: (productId: number) => request<RecipeItem[]>(`/api/products/${productId}/recipe`),
  updateProductRecipe: (productId: number, items: { ingredient_id: number; quantity_per_unit: number }[]) =>
    request<RecipeItem[]>(`/api/products/${productId}/recipe`, { method: "PUT", body: JSON.stringify(items) }),

  getCurrentStocktakeSession: () => request<StocktakeSession | null>("/api/stocktake/sessions/current"),
  listStocktakeSessions: () => request<StocktakeSession[]>("/api/stocktake/sessions"),
  getStocktakeSession: (id: number) => request<StocktakeSession>(`/api/stocktake/sessions/${id}`),
  openStocktakeSession: (note: string = "") =>
    request<StocktakeSession>("/api/stocktake/sessions", { method: "POST", body: JSON.stringify({ note }) }),
  submitStocktakeCount: (sessionId: number, lineId: number, counted_quantity: number | null) =>
    request<StocktakeLine>(`/api/stocktake/sessions/${sessionId}/lines/${lineId}`, {
      method: "PUT",
      body: JSON.stringify({ counted_quantity }),
    }),
  closeStocktakeSession: (id: number) =>
    request<StocktakeCloseResult>(`/api/stocktake/sessions/${id}/close`, { method: "POST" }),

  exportProductsUrl: () => `${API_BASE_URL}/api/export/products`,
  exportSalesUrl: (start?: string, end?: string) => {
    const qs = new URLSearchParams();
    if (start) qs.set("start", start);
    if (end) qs.set("end", end);
    return `${API_BASE_URL}/api/export/sales${qs.toString() ? `?${qs.toString()}` : ""}`;
  },
  exportExpensesUrl: (start?: string, end?: string) => {
    const qs = new URLSearchParams();
    if (start) qs.set("start", start);
    if (end) qs.set("end", end);
    return `${API_BASE_URL}/api/export/expenses${qs.toString() ? `?${qs.toString()}` : ""}`;
  },

  testLineNotify: () => request<{ ok: boolean; detail: string }>("/api/settings/test-line-notify", { method: "POST" }),

  getDbConfig: () => request<DbConfig>("/api/system/db-config"),
  updateDbConfig: (payload: DbConfigIn) =>
    request<DbConfig>("/api/system/db-config", { method: "PUT", body: JSON.stringify(payload) }),
  testDbConfig: (payload: DbConfigIn) =>
    request<{ ok: boolean; detail: string }>("/api/system/db-config/test", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
