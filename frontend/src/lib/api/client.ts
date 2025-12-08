import axios, { type AxiosInstance, type AxiosError } from 'axios';
import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import { deleteCookie } from '$lib/utils/cookies';
import type { OrderTypeFilter } from '$lib/types/orders';

// API Base URLs
const PUBLIC_API_URL = '/api/public';
const ENRICHMENT_API_URL = '/api/enrichment';
const ADMIN_API_URL = '/api/admin';

// Create axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: PUBLIC_API_URL,
  timeout: 45000, // Increased to 45s to accommodate Whitepages API retries
  headers: {
    'Content-Type': 'application/json',
  },
});

// Create enrichment axios instance
const enrichmentClient: AxiosInstance = axios.create({
  baseURL: ENRICHMENT_API_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Create admin compat axios instance for ticket operations
const adminCompatClient: AxiosInstance = axios.create({
  baseURL: ADMIN_API_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - add JWT token
apiClient.interceptors.request.use(
  (config) => {
    if (browser) {
      const token = localStorage.getItem('access_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor - handle errors
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Skip redirect for public endpoints
      const isPublicEndpoint = error.config?.url?.startsWith('/news/');

      if (!isPublicEndpoint) {
        // Unauthorized - clear token and redirect to login
        if (browser) {
          localStorage.removeItem('access_token');
          deleteCookie('access_token');
          goto('/login');
        }
      }
    } else if (error.response?.status === 429) {
      // Rate limit exceeded
      console.error('Rate limit exceeded. Please try again later.');
    }
    return Promise.reject(error);
  }
);

// Request interceptor for enrichmentClient - add JWT token
enrichmentClient.interceptors.request.use(
  (config) => {
    if (browser) {
      const token = localStorage.getItem('access_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for enrichmentClient - handle errors
enrichmentClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Unauthorized - clear token and redirect to login
      if (browser) {
        localStorage.removeItem('access_token');
        deleteCookie('access_token');
        goto('/login');
      }
    } else if (error.response?.status === 429) {
      // Rate limit exceeded
      console.error('Rate limit exceeded. Please try again later.');
    }
    return Promise.reject(error);
  }
);

// Request interceptor for adminCompatClient - add JWT token
adminCompatClient.interceptors.request.use(
  (config) => {
    if (browser) {
      const token = localStorage.getItem('access_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for adminCompatClient - handle errors
adminCompatClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Unauthorized - clear token and redirect to login
      if (browser) {
        localStorage.removeItem('access_token');
        deleteCookie('access_token');
        goto('/login');
      }
    } else if (error.response?.status === 429) {
      // Rate limit exceeded
      console.error('Rate limit exceeded. Please try again later.');
    }
    return Promise.reject(error);
  }
);

// TypeScript Interfaces
export interface UserResponse {
  id: string;
  username: string;
  email: string;
  telegram?: string;
  jabber?: string;
  balance: number;
  access_code?: string;
  is_banned?: boolean;
  ban_reason?: string;
  banned_at?: string;
  instant_ssn_rules_accepted?: boolean;
  invitation_code?: string;
  invited_by?: string;
  invitation_bonus_received?: boolean;
  created_at: string;
}

export interface SSNRecord {
  id: number;
  firstname?: string;
  lastname?: string;
  ssn: string;
  email?: string;
  phone?: string;
  address?: string;
  city?: string;
  state?: string;
  zip?: string;
  dob?: string;
  source_table?: string;
  // Count fields for lookup results (when actual data is hidden)
  email_count?: number;
  phone_count?: number;
}

export interface InstantSSNParams {
  firstname: string;
  lastname: string;
  address: string;
}

export interface InstantSSNResult {
  // Personal info
  firstname: string;
  lastname: string;
  middlename?: string;
  dob?: string;

  // Primary (current) address
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;

  // Primary (current) contact
  phone?: string;
  email?: string;

  // SSN from local database
  ssn?: string;
  ssn_found: boolean;

  // Source information
  report_token?: string;

  // Local database data (when SSN is found)
  local_db_data?: {
    firstname?: string;
    lastname?: string;
    dob?: string;
    address?: string;
    city?: string;
    state?: string;
    zip?: string;
    phone?: string;
    email?: string;
    source_table?: string;
  };
}

export interface InstantSSNResponse {
  success: boolean;
  results: InstantSSNResult[];
  data_found: boolean;
  ssn_matches_found: number;
  message?: string;
  new_balance?: number;
  order_id?: string;
  charged_amount?: number;
}

export interface MaintenanceStatusResponse {
  is_active: boolean;
  message?: string | null;
  service_name: string;
}

export interface EnrichRecordResponse {
  record: SSNRecord;
  updated_fields: string[];
  enrichment_cost: number;
  enrichment_success: boolean;  // Whether enrichment was successful
  changes: Record<string, any>;  // Only changed key-value pairs
}

export interface OrderItemResponse {
  ssn: string;
  price: string | number;  // Comment 6: Backend returns string, normalize on client
  ssn_details?: SSNRecord;
  // Enrichment metadata
  enrichment_attempted?: boolean;
  enrichment_success?: boolean;
  enrichment_cost?: string | null;
  enrichment_timestamp?: string | null;
  // Additional fields used by orders page
  ssn_record_id?: string;
  firstname?: string;
  middlename?: string;
  lastname?: string;
  dob?: string;
  address?: string;
  city?: string;
  state?: string;
  zip?: string;
  email?: string;
  phone?: string;
}

export interface OrderSummary {
  id: string;
  total_price: number;
  status: string;
  created_at: string;
  items_count: number;
  order_type: string;
}

export interface OrderResponse {
  id: string;
  total_price: number;
  status: string;
  created_at: string;
  items_count: number;
}

export interface OrderDetailResponse {
  id: string;
  total_price: number;
  status: string;
  created_at: string;
  items: OrderItemResponse[];
}

export interface StatsOnlineResponse {
  count: number;
  timestamp: string;
}

export interface StatsIPsResponse {
  unique_ips: number;
  last_30_days: number;
}

export interface StatsLoyaltyResponse {
  percentage: string;
  tier: string;
}

export interface ProxyDataItem {
  proxy_ip: string;
  country: string;
  city: string;
  region: string;
  isp: string;
  zip: string;
  speed: string;
  type: string;
  price: number;
}

export interface TransactionResponse {
  id: string;
  amount: number;
  payment_method: string;
  status: string;
  payment_provider?: string;
  external_transaction_id?: string;
  payment_address?: string;
  currency?: string;
  network?: string;
  metadata?: any;
  created_at: string;
  updated_at: string;
}

export interface TransactionListResponse {
  transactions: TransactionResponse[];
  total_count: number;
}

export interface NewsResponse {
  id: string;
  title: string;
  content: string;
  created_at?: string | null;
}

export interface NewsListResponse {
  news: NewsResponse[];
  total: number;
  limit: number;
  offset: number;
}

// Manual SSN Tickets Interfaces
export interface CreateManualSSNTicketRequest {
  firstname: string;
  lastname: string;
  address: string;
}

export interface TicketResponse {
  id: string;
  user_id: string;
  username: string;
  firstname: string;
  lastname: string;
  address: string;
  status: string; // pending | processing | completed | rejected
  worker_id?: string;
  worker_username?: string;
  response_data?: any;
  is_viewed?: boolean;
  created_at: string;
  updated_at: string;
}

export interface TicketListResponse {
  tickets: TicketResponse[];
  total_count: number;
}

// Thread-based Support interfaces
export interface ThreadResponse {
  id: string;
  user_id: string;
  username: string;
  message_type: string;
  subject: string | null;
  status: string;
  last_message_at: string;
  unread_count: number;
  created_at: string;
  updated_at: string;
  last_message_preview?: string | null;
}

export interface ThreadListResponse {
  threads: ThreadResponse[];
  total_count: number;
}

export interface MessageResponse {
  id: string;
  thread_id: string;
  message: string;
  message_type: string;
  is_read: boolean;
  created_at: string;
  sender_username: string;
}

export interface MessageListResponse {
  messages: MessageResponse[];
  total_count: number;
}

export interface CreateThreadRequest {
  message: string;
  message_type: 'bug_report' | 'feature_request' | 'general_question';
  subject?: string | null;
}

export interface CreateMessageRequest {
  message: string;
}

// DEPRECATED: Support Message interfaces (legacy, use Thread-based instead)
/**
 * @deprecated Use ThreadResponse instead
 */
export interface SupportMessageResponse {
  id: string;
  user_id: string;
  username: string;
  message: string;
  admin_response: string | null;
  status: string;
  responded_by: string | null;
  responded_at: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * @deprecated Use ThreadListResponse instead
 */
export interface SupportMessageListResponse {
  messages: SupportMessageResponse[];
  total_count: number;
}

/**
 * @deprecated Use CreateThreadRequest instead
 */
export interface CreateSupportMessageRequest {
  message: string;
}

// Contact Thread interfaces
/**
 * Contact thread response from Public API (user perspective).
 *
 * **Note on unread_count**: For user-facing API, this field counts unread messages
 * from **admin** (i.e., admin replies that the user has not yet read).
 * This is opposite to the Admin API where unread_count tracks unread user messages.
 */
export interface ContactThreadResponse {
  id: string;
  user_id: string;
  username: string;
  message_type: 'bug_report' | 'feature_request';
  status: 'pending' | 'answered' | 'closed';
  last_message_at: string;
  /** Number of unread admin messages (admin replies not yet read by the user) */
  unread_count: number;
  created_at: string;
  updated_at: string;
  last_message_preview?: string;
}

export interface ContactThreadListResponse {
  threads: ContactThreadResponse[];
  total_count: number;
}

export interface ContactMessageResponse {
  id: string;
  thread_id: string;
  message: string;
  message_type: 'user' | 'admin';
  is_read: boolean;
  created_at: string;
  sender_username: string;
}

export interface ContactMessageListResponse {
  messages: ContactMessageResponse[];
  total_count: number;
}

export interface CreateContactThreadRequest {
  message: string;
  message_type: 'bug_report' | 'feature_request';
}

export interface CreateContactMessageRequest {
  message: string;
}

/**
 * @deprecated Use CreateContactThreadRequest instead
 */
export interface CreateContactMessageRequestOld {
  message_type: 'bug_report' | 'feature_request';
  message: string;
}

// Coupon validation interfaces
export interface ValidateCouponRequest {
  coupon_code: string;
}

export interface ValidateCouponResponse {
  valid: boolean;
  coupon_type?: string;
  bonus_percent?: number;
  bonus_amount?: number;
  requires_registration: boolean;
  message?: string;
}

export interface ApplyCouponRequest {
  code: string;
}

/**
 * Response model for applying coupon to balance.
 * Corresponds to ApplyCouponToBalanceResponse Pydantic model in api/public/routers/billing.py
 */
export interface ApplyCouponToBalanceResponse {
  success: boolean;
  message: string;
  bonus_amount: number;
  new_balance: number;
}

export interface InvitationCodeResponse {
  invitation_code: string;
}

export interface InvitationStatsResponse {
  invitation_code: string;
  total_invited: number;
  total_bonus_earned: number;
}

// Authentication API
export const login = async (
  access_code: string
): Promise<{ access_token: string; token_type: string }> => {
  const response = await apiClient.post('/auth/login', {
    access_code,
  });
  return response.data;
};

export const register = async (couponCode?: string, invitationCode?: string): Promise<UserResponse> => {
  const body: any = {};
  if (couponCode) {
    body.coupon_code = couponCode;
  }
  if (invitationCode) {
    body.invitation_code = invitationCode;
  }
  const response = await apiClient.post('/auth/register', body);
  return response.data;
};

export const validateCoupon = async (couponCode: string): Promise<ValidateCouponResponse> => {
  const response = await apiClient.post<ValidateCouponResponse>('/auth/validate-coupon', {
    coupon_code: couponCode
  });
  return response.data;
};

export const applyCoupon = async (code: string): Promise<ApplyCouponToBalanceResponse> => {
  const response = await apiClient.post<ApplyCouponToBalanceResponse>('/billing/apply-coupon', {
    code: code.trim()
  });
  return response.data;
};

export const getInvitationCode = async (): Promise<InvitationCodeResponse> => {
  const response = await apiClient.get<InvitationCodeResponse>('/auth/invitation-code');
  return response.data;
};

export const getInvitationStats = async (): Promise<InvitationStatsResponse> => {
  const response = await apiClient.get<InvitationStatsResponse>('/auth/invitation-stats');
  return response.data;
};

export const getCurrentUser = async (): Promise<UserResponse> => {
  const response = await apiClient.get('/auth/me');
  return response.data;
};

export const updateProfile = async (data: {
  telegram?: string;
  jabber?: string;
  email?: string;
}): Promise<UserResponse> => {
  const response = await apiClient.patch('/auth/me', data);
  return response.data;
};

export const acceptInstantSSNRules = async (): Promise<{ success: boolean; message: string }> => {
  const response = await apiClient.post('/auth/accept-instant-ssn-rules');
  return response.data;
};

export const changePassword = async (
  currentPassword: string,
  newPassword: string
): Promise<{ message: string }> => {
  const response = await apiClient.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword
  });
  return response.data;
};

export const setPassword = async (newPassword: string): Promise<{ message: string }> => {
  const response = await apiClient.post('/auth/set-password', {
    new_password: newPassword
  });
  return response.data;
};

// Search API
export const searchByEmail = async (email: string, limit?: number): Promise<SSNRecord[]> => {
  const body: { email: string; limit?: number } = { email };
  if (limit !== undefined) {
    body.limit = limit;
  }
  const response = await apiClient.post('/search/email', body);
  return response.data;
};

export interface SearchByNameParams {
  firstname?: string;
  lastname?: string;
  zip?: string;
  state?: string;
  last4ssn?: string;
  limit?: number;
  middlename?: string;
  city?: string;
  dob?: string;
  email?: string;
  phone?: string;
}

export const searchByName = async (params: SearchByNameParams): Promise<SSNRecord[]> => {
  const body: {
    firstname?: string;
    lastname?: string;
    zip?: string;
    state?: string;
    last4ssn?: string;
    limit?: number;
    middlename?: string;
    city?: string;
    dob?: string;
    email?: string;
    phone?: string;
  } = {};

  // Trim and coerce empty strings to undefined for all fields
  if (params.firstname?.trim()) {
    body.firstname = params.firstname.trim();
  }
  if (params.lastname?.trim()) {
    body.lastname = params.lastname.trim();
  }
  if (params.zip?.trim()) {
    body.zip = params.zip.trim();
  }
  if (params.state?.trim()) {
    body.state = params.state.trim();
  }
  if (params.last4ssn?.trim()) {
    body.last4ssn = params.last4ssn.trim();
  }
  if (params.limit !== undefined) {
    body.limit = params.limit;
  }
  if (params.middlename?.trim()) {
    body.middlename = params.middlename.trim();
  }
  if (params.city?.trim()) {
    body.city = params.city.trim();
  }
  if (params.dob?.trim()) {
    body.dob = params.dob.trim();
  }
  if (params.email?.trim()) {
    body.email = params.email.trim();
  }
  if (params.phone?.trim()) {
    body.phone = params.phone.trim();
  }

  const response = await apiClient.post('/search/name', body);
  return response.data;
};

export const instantSSNSearch = async (params: InstantSSNParams): Promise<InstantSSNResponse> => {
  const body: {
    firstname: string;
    lastname: string;
    zip?: string;
    address?: string;
  } = {
    firstname: params.firstname.trim(),
    lastname: params.lastname.trim()
  };

  // Either zip or address must be provided
  if (params.zip?.trim()) {
    body.zip = params.zip.trim();
  }
  if (params.address?.trim()) {
    body.address = params.address.trim();
  }

  const response = await apiClient.post('/search/instant-ssn', body);
  return response.data;
};

export const getMaintenanceStatus = async (serviceName: string): Promise<MaintenanceStatusResponse> => {
  const response = await apiClient.get(`/maintenance/${serviceName}`);
  return response.data;
};

export const getRecord = async (ssn: string): Promise<SSNRecord> => {
  const response = await apiClient.get(`/search/record/${ssn}`);
  return response.data;
};

// Orders API
export const createOrder = async (): Promise<OrderResponse> => {
  const response = await apiClient.post('/ecommerce/orders/create');
  return response.data;
};

export const instantPurchase = async (
  ssn: string,
  table_name: string,
  price: number
): Promise<OrderResponse> => {
  const response = await apiClient.post('/ecommerce/orders/instant-purchase', {
    ssn,
    table_name,
    price,
  });
  return response.data;
};

export const instantPurchaseWithEnrichment = async (
  ssn: string,
  table_name: string
): Promise<OrderResponse> => {
  const response = await apiClient.post('/ecommerce/orders/instant-purchase-with-enrichment', {
    ssn,
    table_name,
    // Price removed - determined by enrichment result
  });
  return response.data;
};

export const enrichRecord = async (
  ssn: string,
  table_name: string
): Promise<EnrichRecordResponse> => {
  // Comment 7: Use correct base URL for enrichment endpoint
  const response = await enrichmentClient.post('/enrich-record', {
    ssn,
    table_name,
  });
  return response.data;
};

/**
 * Get orders with optional filtering
 * @param statusFilter - Optional status filter (pending, completed, failed, cancelled)
 * @param limit - Number of orders to fetch
 * @param offset - Offset for pagination
 * @param typeFilter - Optional order type filter (instant_ssn, manual_ssn, or 'all')
 *                     When 'all' or undefined: Returns ALL order types including instant_ssn, manual_ssn, and legacy reverse_ssn
 *                     When specific type: Returns only orders of that type
 * @returns List of order summaries
 */
export const getOrders = async (
  statusFilter?: string,
  limit: number = 50,
  offset: number = 0,
  typeFilter?: OrderTypeFilter
): Promise<OrderSummary[]> => {
  const params: any = { limit, offset };
  if (statusFilter) {
    params.status_filter = statusFilter;
  }
  // Important: When typeFilter is 'all' or undefined, we intentionally DO NOT send the type_filter param.
  // This causes the backend to return ALL order types including:
  // - instant_ssn (current)
  // - manual_ssn (current)
  // - reverse_ssn (deprecated but still present for historical orders)
  // This is the intended behavior for the "All Orders" filter.
  if (typeFilter && typeFilter !== 'all') {
    params.type_filter = typeFilter;
  }
  const response = await apiClient.get('/ecommerce/orders', {
    params,
  });
  return response.data;
};

export const getOrderDetails = async (order_id: string): Promise<OrderDetailResponse> => {
  const response = await apiClient.get(`/ecommerce/orders/${order_id}`);
  return response.data;
};

export const getUnviewedOrdersCount = async (): Promise<number> => {
  const response = await apiClient.get('/ecommerce/orders/unviewed-count');
  return response.data.count;
};

export const markOrdersAsViewed = async (): Promise<{ success: boolean; updated_count: number }> => {
  const response = await apiClient.post('/ecommerce/orders/mark-viewed');
  return response.data;
};

// Statistics API
export const getStatsOnline = async (): Promise<StatsOnlineResponse> => {
  const response = await apiClient.get('/stats/online');
  return response.data;
};

export const getStatsIPs = async (): Promise<StatsIPsResponse> => {
  const response = await apiClient.get('/stats/ips');
  return response.data;
};

export const getStatsLoyalty = async (): Promise<StatsLoyaltyResponse> => {
  const response = await apiClient.get('/stats/loyalty');
  return response.data;
};

export const getStatsData = async (filters?: {
  country?: string;
  state?: string;
  city?: string;
  zip?: string;
  type?: string;
  speed?: string;
}): Promise<ProxyDataItem[]> => {
  const response = await apiClient.get('/stats/data', { params: filters });
  return response.data;
};

// News API
export const getNews = async (params?: {
  limit?: number;
  offset?: number;
}): Promise<NewsListResponse> => {
  const response = await apiClient.get<NewsListResponse>('/news/', { params });
  return response.data;
};

// Billing API
export const createDeposit = async (
  amount: number,
  payment_method: string = 'crypto',
  currency?: string,
  network?: string,
  payment_provider?: string
): Promise<TransactionResponse> => {
  const requestBody: any = { amount, payment_method };
  if (currency) requestBody.currency = currency;
  if (network) requestBody.network = network;
  if (payment_provider) requestBody.payment_provider = payment_provider;

  const response = await apiClient.post('/billing/deposit', requestBody);
  return response.data;
};

export const getTransactions = async (
  status_filter?: string,
  limit: number = 50,
  offset: number = 0
): Promise<TransactionListResponse> => {
  const params: any = { limit, offset };
  if (status_filter) {
    params.status_filter = status_filter;
  }
  const response = await apiClient.get('/billing/transactions', { params });
  return response.data;
};

export const getTransactionDetails = async (transaction_id: string): Promise<TransactionResponse> => {
  const response = await apiClient.get(`/billing/transactions/${transaction_id}`);
  return response.data;
};

// Tickets API
/**
 * Create a manual SSN lookup ticket
 * @param data - Request data containing firstname, lastname, and address
 * @returns Created ticket response
 */
export const createManualSSNTicket = async (
  data: CreateManualSSNTicketRequest
): Promise<TicketResponse> => {
  const response = await adminCompatClient.post('/tickets', data);
  return response.data;
};

/**
 * Get user's tickets with optional filters
 * @param params - Optional query parameters (status_filter, limit, offset)
 * @returns List of tickets created by the current user
 */
export const getMyTickets = async (params?: {
  status_filter?: string;
  limit?: number;
  offset?: number;
}): Promise<TicketListResponse> => {
  // Use public API endpoint for users to get their own tickets
  const response = await apiClient.get('/tickets', { params });
  return response.data;
};

/**
 * Get detailed information for a specific ticket
 * @param ticket_id - The ticket ID
 * @returns Full ticket details including response_data when completed
 */
export const getTicketDetails = async (ticket_id: string): Promise<TicketResponse> => {
  // Use public API endpoint for users to get their own ticket details
  const response = await apiClient.get(`/tickets/${ticket_id}`);
  return response.data;
};

/**
 * Move a ticket to orders
 * @param ticket_id - The ticket ID
 * @returns Created order
 */
export const moveTicketToOrder = async (ticket_id: string): Promise<OrderResponse> => {
  const response = await apiClient.post(`/tickets/${ticket_id}/move-to-order`);
  return response.data;
};

/**
 * Get count of unviewed completed tickets
 * @returns Count of unviewed tickets
 */
export const getUnviewedTicketsCount = async (): Promise<number> => {
  const response = await apiClient.get('/tickets/unviewed-count');
  return response.data.count;
};

/**
 * Mark tickets as viewed
 * @param ticket_ids - Array of ticket IDs to mark as viewed
 * @returns Success status and count of updated tickets
 */
export const markTicketsAsViewed = async (
  ticket_ids: string[]
): Promise<{ success: boolean; updated_count: number }> => {
  const response = await apiClient.post('/tickets/mark-viewed', { ticket_ids });
  return response.data;
};

// Thread-based Support API
export const createSupportThread = async (
  data: CreateThreadRequest
): Promise<ThreadResponse> => {
  const response = await apiClient.post('/support/threads', data);
  return response.data;
};

export const getSupportThreads = async (params?: {
  status_filter?: string;
  limit?: number;
  offset?: number;
}): Promise<ThreadListResponse> => {
  const response = await apiClient.get('/support/threads', { params });
  return response.data;
};

export const getSupportThreadDetails = async (thread_id: string): Promise<ThreadResponse> => {
  const response = await apiClient.get(`/support/threads/${thread_id}`);
  return response.data;
};

export const getThreadMessages = async (
  thread_id: string,
  params?: {
    limit?: number;
    offset?: number;
  }
): Promise<MessageListResponse> => {
  const response = await apiClient.get(`/support/threads/${thread_id}/messages`, { params });
  return response.data;
};

export const addThreadMessage = async (
  thread_id: string,
  data: CreateMessageRequest
): Promise<MessageResponse> => {
  const response = await apiClient.post(`/support/threads/${thread_id}/messages`, data);
  return response.data;
};

export const markThreadMessagesAsRead = async (
  thread_id: string
): Promise<{ success: boolean; updated_count: number }> => {
  const response = await apiClient.patch(`/support/threads/${thread_id}/mark-read`);
  return response.data;
};

// DEPRECATED: Support Message API (legacy, use Thread-based API instead)
/**
 * @deprecated Use createSupportThread instead
 */
export const createSupportMessage = async (
  data: CreateSupportMessageRequest
): Promise<SupportMessageResponse> => {
  const response = await apiClient.post('/support/messages', data);
  return response.data;
};

/**
 * @deprecated Use getSupportThreads instead
 */
export const getSupportMessages = async (params?: {
  status_filter?: string;
  limit?: number;
  offset?: number;
}): Promise<SupportMessageListResponse> => {
  const response = await apiClient.get('/support/messages', { params });
  return response.data;
};

/**
 * @deprecated Use getSupportThreadDetails instead
 */
export const getSupportMessageDetails = async (message_id: string): Promise<SupportMessageResponse> => {
  const response = await apiClient.get(`/support/messages/${message_id}`);
  return response.data;
};

// Contact Thread API
export const createContactThread = async (
  data: CreateContactThreadRequest
): Promise<ContactThreadResponse> => {
  const response = await apiClient.post('/contact/threads', data);
  return response.data;
};

export const getContactThreads = async (params?: {
  status_filter?: string;
  limit?: number;
  offset?: number;
}): Promise<ContactThreadListResponse> => {
  const response = await apiClient.get('/contact/threads', { params });
  return response.data;
};

export const getContactThreadDetails = async (thread_id: string): Promise<ContactThreadResponse> => {
  const response = await apiClient.get(`/contact/threads/${thread_id}`);
  return response.data;
};

export const getContactThreadMessages = async (
  thread_id: string,
  params?: { limit?: number; offset?: number }
): Promise<ContactMessageListResponse> => {
  const response = await apiClient.get(`/contact/threads/${thread_id}/messages`, { params });
  return response.data;
};

export const addContactThreadMessage = async (
  thread_id: string,
  data: CreateContactMessageRequest
): Promise<ContactMessageResponse> => {
  const response = await apiClient.post(`/contact/threads/${thread_id}/messages`, data);
  return response.data;
};

export const markContactThreadMessagesAsRead = async (
  thread_id: string
): Promise<{ success: boolean; updated_count: number }> => {
  const response = await apiClient.patch(`/contact/threads/${thread_id}/mark-read`);
  return response.data;
};

/**
 * @deprecated Use createContactThread instead
 */
export const createContactMessage = async (
  data: CreateContactMessageRequestOld
): Promise<any> => {
  const response = await apiClient.post('/contact/messages', data);
  return response.data;
};

/**
 * @deprecated Use getContactThreads instead
 */
export const getContactMessages = async (params?: {
  message_type_filter?: string;
  status_filter?: string;
  limit?: number;
  offset?: number;
}): Promise<any> => {
  const response = await apiClient.get('/contact/messages', { params });
  return response.data;
};

/**
 * @deprecated Use getContactThreadDetails instead
 */
export const getContactMessageDetails = async (message_id: string): Promise<any> => {
  const response = await apiClient.get(`/contact/messages/${message_id}`);
  return response.data;
};

// Phone Lookup Interfaces
export interface DaisySMSService {
  code: string;
  name: string;
  price?: number;
  category?: string;
}

export interface DaisySMSServicesResponse {
  services: DaisySMSService[];
}

export interface PhoneLookupResult {
  firstname?: string;
  lastname?: string;
  middlename?: string;
  dob?: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  phone?: string;
  email?: string;
  ssn?: string;
  ssn_found: boolean;
}

export interface PhoneLookupResponse {
  success: boolean;
  phone_number?: string;
  rental_id?: string;
  daisysms_id?: string;
  person_data?: PhoneLookupResult;
  error?: string;
  message?: string;
  new_balance?: number;
  charged_amount?: number;
  order_id?: string;
}

export interface PhoneRentalResponse {
  id: string;
  daisysms_id: string;
  phone_number: string;
  service_code: string;
  service_name: string;
  status: 'active' | 'expired' | 'cancelled' | 'finished';
  auto_renew: boolean;
  ssn_found: boolean;
  person_data?: PhoneLookupResult;
  created_at: string;
  expires_at?: string;
  renewed_at?: string;
}

export interface PhoneRentalsListResponse {
  rentals: PhoneRentalResponse[];
  total_count: number;
}

export interface PhoneRentalRenewResponse {
  success: boolean;
  rental_id: string;
  new_expires_at?: string;
  message: string;
}

// Phone Lookup API
export const getPhoneLookupServices = async (): Promise<DaisySMSServicesResponse> => {
  const response = await apiClient.get<DaisySMSServicesResponse>('/phone-lookup/services');
  return response.data;
};

export const phoneLookupSearch = async (serviceCode: string): Promise<PhoneLookupResponse> => {
  const response = await apiClient.post<PhoneLookupResponse>('/phone-lookup/search', {
    service_code: serviceCode
  });
  return response.data;
};

export const getPhoneRentals = async (params?: {
  limit?: number;
  offset?: number;
}): Promise<PhoneRentalsListResponse> => {
  const response = await apiClient.get<PhoneRentalsListResponse>('/phone-lookup/rentals', { params });
  return response.data;
};

export const renewPhoneRental = async (rentalId: string): Promise<PhoneRentalRenewResponse> => {
  const response = await apiClient.post<PhoneRentalRenewResponse>(`/phone-lookup/rentals/${rentalId}/renew`);
  return response.data;
};

export const cancelPhoneRental = async (rentalId: string): Promise<{ success: boolean; message: string }> => {
  const response = await apiClient.post<{ success: boolean; message: string }>(`/phone-lookup/rentals/${rentalId}/cancel`);
  return response.data;
};

// Error handling helper
export const handleApiError = (error: unknown): string => {
  // Check if it's an AxiosError
  if (axios.isAxiosError(error)) {
    if (error.response?.data) {
      const data = error.response.data as any;
      if (data.detail) {
        return typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      }
    }
    return error.message || 'An unexpected error occurred';
  }
  // Handle other error types
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
};

// Subscription Types
export interface SubscriptionPlanResponse {
  id: string;
  name: string;
  duration_months: number;
  price: number;
  discount_percent: number;
}

export interface SubscriptionResponse {
  id: string;
  plan: SubscriptionPlanResponse;
  start_date: string;
  end_date: string;
  is_active: boolean;
}

export interface CheckAccessResponse {
  has_access: boolean;
  subscription?: SubscriptionResponse;
  message: string;
}

// Subscriptions API
export const getSubscriptionPlans = async (): Promise<SubscriptionPlanResponse[]> => {
  const response = await apiClient.get<SubscriptionPlanResponse[]>('/subscriptions/plans');
  return response.data;
};

export const purchaseSubscription = async (planId: string): Promise<SubscriptionResponse> => {
  const response = await apiClient.post<SubscriptionResponse>('/subscriptions/purchase', { plan_id: planId });
  return response.data;
};

export const getMySubscription = async (): Promise<SubscriptionResponse | null> => {
  const response = await apiClient.get<SubscriptionResponse | null>('/subscriptions/my-subscription');
  return response.data;
};

export const checkSubscriptionAccess = async (): Promise<CheckAccessResponse> => {
  const response = await apiClient.get<CheckAccessResponse>('/subscriptions/check-access');
  return response.data;
};

// Database Lookup Types and API
export interface LookupSearchRequest {
  firstname: string;
  lastname: string;
  street?: string;
  phone?: string;
  city?: string;
  state?: string;
}

export interface LookupSearchMatch {
  firstname?: string;
  middlename?: string;
  lastname?: string;
  ssn?: string;
  dob?: string;
  age?: number;
  gender?: string;
  phones?: any[];
  emails?: any[];
  addresses?: any[];
  address?: string;
  city?: string;
  state?: string;
  zip?: string;
  matched_by?: string;
}

export interface LookupSearchResponse {
  database_matches: LookupSearchMatch[];
  search_metadata: {
    search_timestamp: string;
    database_matches_count: number;
    user_id?: string;
    search_params?: {
      firstname: string;
      lastname: string;
      street?: string;
      city?: string;
      state?: string;
      phone?: string;
    };
  };
}

export const searchDatabase = async (request: LookupSearchRequest): Promise<LookupSearchResponse> => {
  const response = await apiClient.post<LookupSearchResponse>('/lookup/search', request);
  return response.data;
};

export default apiClient;
