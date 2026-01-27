import axios, { type AxiosError } from 'axios';
import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import { toast } from 'svelte-sonner';
import { env } from '$env/dynamic/public';

// Admin API base URL
// In browser: use relative path through nginx proxy
// In SSR: use internal docker service URL
const ADMIN_API_URL = browser
	? '/api/admin'
	: (env.PUBLIC_ADMIN_API_URL || process.env.ADMIN_API_URL || 'http://admin_api:8002');

// Create axios instance
export const adminClient = axios.create({
	baseURL: ADMIN_API_URL,
	timeout: 30000,
	headers: {
		'Content-Type': 'application/json'
	}
});

// Request interceptor - add auth token
adminClient.interceptors.request.use(
	(config) => {
		if (browser) {
			const token = localStorage.getItem('admin_access_token');
			if (token) {
				config.headers.Authorization = `Bearer ${token}`;
			}
		}
		return config;
	},
	(error) => Promise.reject(error)
);

// Response interceptor - handle auth errors
adminClient.interceptors.response.use(
	(response) => response,
	(error: AxiosError) => {
		if (browser) {
			const url = error.config?.url || '';

			// Don't redirect to login for auth-related endpoints
			const authEndpoints = [
				'/auth/login',
				'/auth/verify-2fa',
				'/auth/setup-2fa',
				'/auth/confirm-2fa',
				'/auth/disable-2fa'
			];

			const isAuthEndpoint = authEndpoints.some(endpoint => url.includes(endpoint));

			if (error.response?.status === 401 && !isAuthEndpoint) {
				// Clear tokens and redirect to login
				localStorage.removeItem('admin_access_token');
				localStorage.removeItem('admin_temp_token');
				goto('/login');
			} else if (error.response?.status === 403) {
				// Forbidden - show error but don't redirect
				toast.error('Admin access required');
			}
		}
		return Promise.reject(error);
	}
);

// TypeScript interfaces
export interface AdminLoginRequest {
	username: string;
	password: string;
}

export interface TwoFactorSetupResponse {
	secret: string;
	provisioning_uri: string;
	message?: string;
}

export interface TwoFactorVerifyRequest {
	totp_code: string;
}

export interface TokenResponse {
	access_token: string;
	token_type: string;
	requires_2fa?: boolean;
}

export interface UserStatsResponse {
	total_users: number;
	new_users_1_day: number;
	new_users_30_days: number;
	new_users_all_time: number;
}

export interface FinancialStatsResponse {
	total_deposited: number;
	total_spent: number;
	usage_percentage: number;
	usage_amount: number;
}

export interface TransactionStatsResponse {
	total_transactions: number;
	pending: number;
	paid: number;
	expired: number;
	failed: number;
}

export interface ProductStatsResponse {
	total_orders: number;
	instant_ssn_purchases: number;
	cart_purchases: number;
	enrichment_operations: number;
}

export interface CouponUsageStats {
	coupon_code: string;
	bonus_percent: number;
	times_used: number;
	total_bonus_given: number;
}

export type CouponType = 'percentage' | 'fixed_amount' | 'registration' | 'registration_bonus';

export interface CouponResponse {
	id: string;
	code: string;
	bonus_percent: number;
	coupon_type: string;
	bonus_amount: number | null;
	requires_registration: boolean;
	max_uses: number;
	current_uses: number;
	is_active: boolean;
	created_at: string;
	usage_percentage: number;
}

export interface CreateCouponRequest {
	code?: string;
	bonus_percent?: number;
	coupon_type?: string;
	bonus_amount?: number;
	requires_registration?: boolean;
	max_uses: number;
	is_active?: boolean;
}

export interface UpdateCouponRequest {
	bonus_percent?: number;
	coupon_type?: string;
	bonus_amount?: number;
	requires_registration?: boolean;
	max_uses?: number;
	is_active?: boolean;
}

export interface UserTableItem {
	id: string;
	username: string;
	balance: number;
	total_spent: number;
	total_deposited: number;
	applied_coupons: string[];
	created_at: string;
	is_banned: boolean;
}

export interface UserTableResponse {
	users: UserTableItem[];
	total_count: number;
	page: number;
	page_size: number;
}

export interface BannedUserResponse {
	id: string;
	username: string;
	ban_reason: string;
	banned_at: string;
	created_at: string;
}

export interface BannedUsersListResponse {
	users: BannedUserResponse[];
	total_count: number;
}

export interface UnbanUserResponse {
	message: string;
	user_id: string;
	username: string;
}

export interface BanUserRequest {
	reason: string;
}

export interface BanUserResponse {
	message: string;
	user_id: string;
	username: string;
	ban_reason: string;
	banned_at: string;
}

export interface NewsResponse {
	id: string;
	title: string;
	content: string;
	author_id: string;
	author_username: string;
	created_at: string;
	updated_at: string;
}

export interface CreateNewsRequest {
	title: string;
	content: string;
}

export interface UpdateNewsRequest {
	title?: string;
	content?: string;
}

export interface NewsListResponse {
	news: NewsResponse[];
	total_count: number;
}

// Worker Management Interfaces
export interface WorkerResponse {
	id: string;
	username: string;
	email: string;
	worker_role: boolean;
	is_admin: boolean;
	access_code: string;
	created_at: string;
}

export interface WorkerListResponse {
	workers: WorkerResponse[];
	total_count: number;
}

export interface WorkerRequestResponse {
	id: string;
	username: string;
	email: string;
	access_code: string;
	status: string; // pending/approved/rejected
	created_at: string;
}

export interface WorkerRequestListResponse {
	requests: WorkerRequestResponse[];
	total_count: number;
}

export interface ApproveWorkerResponse {
	message: string;
	user_id: string;
	username: string;
	access_code: string;
}

export interface WorkerRegisterRequest {
	username: string;
	email: string;
	password: string;
}

export interface WorkerRegisterResponse {
	message: string;
	access_code: string;
	status: string;
}

// Ticket Interfaces
export interface TicketResponse {
	id: string;
	user_id: string;
	username: string;
	firstname: string;
	lastname: string;
	address: string;
	status: string; // pending/processing/completed/rejected
	worker_id: string | null;
	worker_username: string | null;
	response_data: any | null;
	created_at: string;
	updated_at: string;
}

export interface TicketListResponse {
	tickets: TicketResponse[];
	total_count: number;
}

export interface CreateTicketRequest {
	firstname: string;
	lastname: string;
	address: string;
}

export interface UpdateTicketRequest {
	status?: string;
	response_data?: any;
}

export interface AssignTicketRequest {
	worker_id: string;
}

export interface MoveTicketToOrderResponse {
	id: string;
	user_id: string;
	items: any;
	total_price: string;
	status: string;
	is_viewed: boolean;
	created_at: string;
	updated_at: string;
}

// Stats Interfaces
export interface StatsTickets {
	total: number;
	pending: number;
	processing: number;
	completed: number;
	avg_time?: number; // in minutes
}

export interface StatsWorkers {
	total: number;
	active: number;
	pending_requests?: number;
}

export interface StatsResponse {
	tickets: StatsTickets;
	workers: StatsWorkers;
}

// Authentication API

export interface AdminUserResponse {
	username: string;
	email: string;
	has_totp: boolean;
	is_admin?: boolean;
	worker_role?: boolean;
}

export async function getCurrentAdminUser(): Promise<AdminUserResponse> {
	const response = await adminClient.get<AdminUserResponse>('/auth/me');
	return response.data;
}

export async function adminLogin(
	username: string,
	password: string
): Promise<TokenResponse> {
	const formData = new URLSearchParams();
	formData.append('username', username);
	formData.append('password', password);

	const response = await adminClient.post<TokenResponse>('/auth/login', formData, {
		headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
	});

	return response.data;
}

export async function verifyTwoFactor(totp_code: string): Promise<TokenResponse> {
	// Use temp token for verification
	const tempToken = browser ? localStorage.getItem('admin_temp_token') : null;

	if (!tempToken) {
		throw new Error('Session expired. Please login again.');
	}

	const response = await adminClient.post<TokenResponse>(
		'/auth/verify-2fa',
		{
			token: tempToken,
			code: totp_code
		}
	);

	return response.data;
}

export async function setupTwoFactor(): Promise<TwoFactorSetupResponse> {
	const response = await adminClient.post<TwoFactorSetupResponse>('/auth/setup-2fa');
	return response.data;
}

export async function confirmTwoFactor(totp_code: string): Promise<{ message: string }> {
	const response = await adminClient.post<{ message: string }>('/auth/confirm-2fa', {
		code: totp_code
	});
	return response.data;
}

export async function disableTwoFactor(password: string): Promise<{ message: string }> {
	const response = await adminClient.post<{ message: string }>('/auth/disable-2fa', {
		password
	});
	return response.data;
}

// Analytics API

export async function getUserStats(): Promise<UserStatsResponse> {
	const response = await adminClient.get<UserStatsResponse>('/analytics/stats/users');
	return response.data;
}

export async function getFinancialStats(): Promise<FinancialStatsResponse> {
	const response = await adminClient.get<FinancialStatsResponse>('/analytics/stats/financial');
	return response.data;
}

export async function getTransactionStats(): Promise<TransactionStatsResponse> {
	const response = await adminClient.get<TransactionStatsResponse>('/analytics/stats/transactions');
	return response.data;
}

export async function getProductStats(): Promise<ProductStatsResponse> {
	const response = await adminClient.get<ProductStatsResponse>('/analytics/stats/products');
	return response.data;
}

export async function getCouponStats(): Promise<CouponUsageStats[]> {
	const response = await adminClient.get<CouponUsageStats[]>('/analytics/stats/coupons');
	return response.data;
}

export async function getUserTable(params?: {
	limit?: number;
	offset?: number;
	search?: string;
	sort_by?: string;
	sort_order?: string;
	coupon_code?: string;
}): Promise<UserTableResponse> {
	const response = await adminClient.get<UserTableResponse>('/analytics/users/table', {
		params
	});
	return response.data;
}

// Coupons API

export async function getCoupons(params?: {
	is_active?: boolean;
	limit?: number;
	offset?: number;
}): Promise<{ coupons: CouponResponse[]; total_count: number }> {
	const response = await adminClient.get<{ coupons: CouponResponse[]; total_count: number }>(
		'/coupons/',
		{ params }
	);

	// Validate response structure
	if (!response.data || !Array.isArray(response.data.coupons)) {
		console.warn('Invalid response structure from getCoupons API:', response.data);
		return { coupons: [], total_count: 0 };
	}

	// Validate total_count is a number
	if (typeof response.data.total_count !== 'number') {
		console.warn('Invalid total_count from getCoupons API:', response.data.total_count);
		return { coupons: response.data.coupons, total_count: 0 };
	}

	return response.data;
}

export async function getCoupon(coupon_id: string): Promise<CouponResponse> {
	const response = await adminClient.get<CouponResponse>(`/coupons/${coupon_id}`);
	return response.data;
}

export async function createCoupon(data: CreateCouponRequest): Promise<CouponResponse> {
	const response = await adminClient.post<CouponResponse>('/coupons/', data);
	return response.data;
}

export async function updateCoupon(
	coupon_id: string,
	data: UpdateCouponRequest
): Promise<CouponResponse> {
	const response = await adminClient.patch<CouponResponse>(`/coupons/${coupon_id}`, data);
	return response.data;
}

export async function deleteCoupon(coupon_id: string): Promise<{ message: string }> {
	const response = await adminClient.delete<{ message: string }>(`/coupons/${coupon_id}`);
	return response.data;
}

export async function deactivateCoupon(coupon_id: string): Promise<CouponResponse> {
	const response = await adminClient.post<CouponResponse>(`/coupons/${coupon_id}/deactivate`);
	return response.data;
}

// News API

export async function getNews(params?: {
	limit?: number;
	offset?: number;
}): Promise<NewsListResponse> {
	const response = await adminClient.get<NewsListResponse>('/news/', { params });

	// Handle case where response.data is directly an array
	if (Array.isArray(response.data)) {
		console.warn('getNews API returned array format, normalizing to {news, total_count}');
		return {
			news: response.data as NewsResponse[],
			total_count: response.data.length
		};
	}

	// Handle case where response.data is an object but without 'news' field
	if (response.data && typeof response.data === 'object' && !Array.isArray(response.data.news)) {
		// Check for alternative field names like 'items'
		const dataObj = response.data as any;
		if (Array.isArray(dataObj.items)) {
			console.warn('getNews API returned {items} format, normalizing to {news, total_count}');
			return {
				news: dataObj.items as NewsResponse[],
				total_count: typeof dataObj.total_count === 'number' ? dataObj.total_count : dataObj.items.length
			};
		}

		console.warn('Invalid response structure from getNews API (no news or items field):', response.data);
		return { news: [], total_count: 0 };
	}

	// Validate standard response structure
	if (!response.data || !Array.isArray(response.data.news)) {
		console.warn('Invalid response structure from getNews API:', response.data);
		return { news: [], total_count: 0 };
	}

	// Validate total_count is a number
	if (typeof response.data.total_count !== 'number') {
		console.warn('Invalid total_count from getNews API, using array length:', response.data.total_count);
		return { news: response.data.news, total_count: response.data.news.length };
	}

	return response.data;
}

export async function getNewsItem(news_id: string): Promise<NewsResponse> {
	const response = await adminClient.get<NewsResponse>(`/news/${news_id}`);
	return response.data;
}

export async function createNews(data: CreateNewsRequest): Promise<NewsResponse> {
	const response = await adminClient.post<NewsResponse>('/news/', data);
	return response.data;
}

export async function updateNews(
	news_id: string,
	data: UpdateNewsRequest
): Promise<NewsResponse> {
	const response = await adminClient.patch<NewsResponse>(`/news/${news_id}`, data);
	return response.data;
}

export async function deleteNews(news_id: string): Promise<{ message: string }> {
	const response = await adminClient.delete<{ message: string }>(`/news/${news_id}`);
	return response.data;
}

// Worker Management API

/**
 * Get list of workers
 * Note: This endpoint doesn't exist yet in backend - uses getUserTable with client-side filtering
 */
export async function getWorkers(params?: {
	limit?: number;
	offset?: number;
}): Promise<WorkerListResponse> {
	// Use getUserTable and filter for worker_role=true
	const response = await getUserTable(params);
	const workers = response.users.filter((user: any) => user.worker_role === true);

	return {
		workers: workers as WorkerResponse[],
		total_count: workers.length
	};
}

/**
 * Remove worker role from user
 * Note: This endpoint doesn't exist yet in backend - needs to be added first
 */
export async function removeWorkerRole(user_id: string): Promise<{ message: string }> {
	const response = await adminClient.patch<{ message: string }>(
		`/workers/${user_id}/remove-role`
	);
	return response.data;
}

// Worker Registration Request API

/**
 * Get worker registration requests
 */
export async function getWorkerRequests(params?: {
	status_filter?: string;
	limit?: number;
	offset?: number;
}): Promise<WorkerRequestListResponse> {
	const response = await adminClient.get<WorkerRequestListResponse>('/worker-requests', {
		params
	});
	return response.data;
}

/**
 * Approve worker registration request
 */
export async function approveWorkerRequest(request_id: string): Promise<ApproveWorkerResponse> {
	const response = await adminClient.post<ApproveWorkerResponse>(
		`/worker-requests/${request_id}/approve`
	);
	return response.data;
}

/**
 * Reject worker registration request
 */
export async function rejectWorkerRequest(
	request_id: string
): Promise<{ message: string; username: string }> {
	const response = await adminClient.post<{ message: string; username: string }>(
		`/worker-requests/${request_id}/reject`
	);
	return response.data;
}

/**
 * Register as a worker (public endpoint)
 */
export async function registerWorker(data: WorkerRegisterRequest): Promise<WorkerRegisterResponse> {
	const response = await adminClient.post<WorkerRegisterResponse>('/auth/register-worker', data);
	return response.data;
}

// Tickets API

/**
 * Get count of pending tickets
 */
export async function getPendingTicketsCount(): Promise<number> {
	const response = await adminClient.get<{ count: number }>('/tickets/pending-count');
	return response.data.count;
}

/**
 * Get tickets list with optional filters
 */
export async function getTickets(params?: {
	status_filter?: string;
	limit?: number;
	offset?: number;
}): Promise<TicketListResponse> {
	const response = await adminClient.get<TicketListResponse>('/tickets', { params });
	return response.data;
}

/**
 * Get single ticket by ID
 */
export async function getTicket(ticket_id: string): Promise<TicketResponse> {
	const response = await adminClient.get<TicketResponse>(`/tickets/${ticket_id}`);
	return response.data;
}

/**
 * Create new ticket
 */
export async function createTicket(data: CreateTicketRequest): Promise<TicketResponse> {
	const response = await adminClient.post<TicketResponse>('/tickets', data);
	return response.data;
}

/**
 * Update ticket
 */
export async function updateTicket(
	ticket_id: string,
	data: UpdateTicketRequest
): Promise<TicketResponse> {
	const response = await adminClient.patch<TicketResponse>(`/tickets/${ticket_id}`, data);
	return response.data;
}

/**
 * Assign ticket to worker
 */
export async function assignTicket(ticket_id: string, worker_id: string): Promise<TicketResponse> {
	const response = await adminClient.post<TicketResponse>(`/tickets/${ticket_id}/assign`, {
		worker_id
	});
	return response.data;
}

/**
 * Move ticket to orders (worker/admin only)
 * Creates order on behalf of ticket owner and deletes ticket
 */
export async function moveTicketToOrder(ticket_id: string): Promise<MoveTicketToOrderResponse> {
	const response = await adminClient.post<MoveTicketToOrderResponse>(
		`/tickets/${ticket_id}/move-to-order`
	);
	return response.data;
}

/**
 * Get unassigned tickets (available for claiming)
 */
export async function getUnassignedTickets(params?: {
	limit?: number;
	offset?: number;
}): Promise<TicketListResponse> {
	const response = await adminClient.get<TicketListResponse>('/tickets/unassigned', { params });
	return response.data;
}

/**
 * Claim an unassigned ticket for current worker
 */
export async function claimTicket(ticket_id: string): Promise<TicketResponse> {
	const response = await adminClient.post<TicketResponse>(`/tickets/${ticket_id}/claim`);
	return response.data;
}

// Stats API

/**
 * Get ticket statistics by period
 */
export async function getStatsTickets(params?: { period?: string }): Promise<StatsTickets> {
	const response = await adminClient.get<StatsTickets>('/stats/tickets', { params });
	return response.data;
}

/**
 * Get worker statistics by period
 */
export async function getStatsWorkers(params?: { period?: string }): Promise<StatsWorkers> {
	const response = await adminClient.get<StatsWorkers>('/stats/workers', { params });
	return response.data;
}

// Transactions API

export interface TransactionItemResponse {
	id: string;
	user_id: string;
	username: string;
	amount: number;
	payment_method: string;
	status: string;
	payment_provider?: string;
	external_transaction_id?: string;
	currency?: string;
	network?: string;
	created_at: string;
	updated_at: string;
}

export interface TransactionListResponse {
	transactions: TransactionItemResponse[];
	total_count: number;
	page: number;
	page_size: number;
}

/**
 * Get transactions list
 */
export async function getTransactions(params?: {
	status_filter?: string;
	limit?: number;
	offset?: number;
}): Promise<TransactionListResponse> {
	const response = await adminClient.get<TransactionListResponse>('/transactions/', { params });
	return response.data;
}

/**
 * Get transaction by ID
 */
export async function getTransaction(transaction_id: string): Promise<TransactionItemResponse> {
	const response = await adminClient.get<TransactionItemResponse>(`/transactions/${transaction_id}`);
	return response.data;
}

// Orders API

export interface OrderItemResponse {
	id: string;
	user_id: string;
	username: string;
	items: any;
	total_price: number;
	status: string;
	is_viewed: boolean;
	created_at: string;
	updated_at: string;
}

export interface OrderListResponse {
	orders: OrderItemResponse[];
	total_count: number;
	page: number;
	page_size: number;
}

export interface InstantSSNStatsResponse {
	total_attempts: number;
	successful_searches: number;
	failed_searches: number;
	success_rate: number;
	failure_rate: number;
	total_revenue: number;
	total_api_cost: number;
	net_profit: number;
	profit_per_search: number;
	period: string;
	telegram_total_attempts: number;
	telegram_successful: number;
	telegram_failed: number;
	telegram_success_rate: number;
}

export interface ManualSSNStatsResponse {
	total_attempts: number;
	successful_searches: number;
	failed_searches: number;
	pending_tickets: number;
	processing_tickets: number;
	success_rate: number;
	failure_rate: number;
	total_revenue: number;
	processing_cost: number;
	net_profit: number;
	profit_per_search: number;
	avg_response_time: number | null;
	period: string;
	telegram_total_attempts: number;
	telegram_successful: number;
	telegram_failed: number;
	telegram_success_rate: number;
}

// Thread-based Support interfaces
export interface ThreadResponse {
	id: string;
	user_id: string;
	username: string;
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
	responded_by_username?: string | null;
}

export interface MessageListResponse {
	messages: MessageResponse[];
	total_count: number;
}

export interface CreateMessageRequest {
	message: string;
}

export interface UpdateThreadStatusRequest {
	status: string;
}

// DEPRECATED: Support & Contact Messages (legacy, use Thread-based instead)
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
	responded_by_username: string | null;
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

// Contact Thread interfaces
/**
 * Contact thread response from Admin API (admin perspective).
 *
 * **Note on unread_count**: For admin API, this field counts unread messages
 * from **user** (i.e., user messages that the admin has not yet read).
 * This is opposite to the Public API where unread_count tracks unread admin messages.
 */
export interface ContactThreadResponse {
	id: string;
	user_id: string;
	username: string;
	message_type: 'bug_report' | 'feature_request';
	status: 'pending' | 'answered' | 'closed';
	last_message_at: string;
	/** Number of unread user messages (user messages not yet read by admin) */
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
	responded_by_username?: string;
}

export interface ContactMessageListResponse {
	messages: ContactMessageResponse[];
	total_count: number;
}

export interface CreateContactMessageRequest {
	message: string;
}

export interface UpdateContactThreadStatusRequest {
	status: 'pending' | 'answered' | 'closed';
}

/**
 * @deprecated Use CreateContactMessageRequest instead
 */
export interface RespondToMessageRequest {
	admin_response: string;
	status?: string;
}

/**
 * Get orders list
 */
export async function getOrders(params?: {
	status_filter?: string;
	limit?: number;
	offset?: number;
}): Promise<OrderListResponse> {
	const response = await adminClient.get<OrderListResponse>('/orders/', { params });
	return response.data;
}

/**
 * Get order by ID
 */
export async function getOrder(order_id: string): Promise<OrderItemResponse> {
	const response = await adminClient.get<OrderItemResponse>(`/orders/${order_id}`);
	return response.data;
}

/**
 * Get Instant SSN statistics
 */
export async function getInstantSSNStats(params?: {
	period?: string;
}): Promise<InstantSSNStatsResponse> {
	const response = await adminClient.get<InstantSSNStatsResponse>('/analytics/stats/instant-ssn', { params });
	return response.data;
}

/**
 * Get Manual SSN statistics
 */
export async function getManualSSNStats(params?: {
	period?: string;
}): Promise<ManualSSNStatsResponse> {
	const response = await adminClient.get<ManualSSNStatsResponse>('/analytics/stats/manual-ssn', { params });
	return response.data;
}

// Thread-based Support API
export async function getSupportThreads(params?: {
	status_filter?: string;
	unread_only?: boolean;
	limit?: number;
	offset?: number;
}): Promise<ThreadListResponse> {
	const response = await adminClient.get<ThreadListResponse>('/support/threads', { params });
	return response.data;
}

export async function getSupportThreadDetails(thread_id: string): Promise<ThreadResponse> {
	const response = await adminClient.get<ThreadResponse>(`/support/threads/${thread_id}`);
	return response.data;
}

export async function getThreadMessages(
	thread_id: string,
	params?: {
		limit?: number;
		offset?: number;
	}
): Promise<MessageListResponse> {
	const response = await adminClient.get<MessageListResponse>(`/support/threads/${thread_id}/messages`, { params });
	return response.data;
}

export async function replyToThread(
	thread_id: string,
	data: CreateMessageRequest
): Promise<MessageResponse> {
	const response = await adminClient.post<MessageResponse>(`/support/threads/${thread_id}/messages`, data);
	return response.data;
}

export async function updateThreadStatus(
	thread_id: string,
	data: UpdateThreadStatusRequest
): Promise<ThreadResponse> {
	const response = await adminClient.patch<ThreadResponse>(`/support/threads/${thread_id}/status`, data);
	return response.data;
}

export async function markThreadMessagesAsRead(
	thread_id: string
): Promise<{ success: boolean; updated_count: number }> {
	const response = await adminClient.patch<{ success: boolean; updated_count: number }>(`/support/threads/${thread_id}/mark-read`);
	return response.data;
}

export async function getUnreadThreadsCount(): Promise<number> {
	const response = await adminClient.get<{ count: number }>('/support/threads/unread-count');
	return response.data.count;
}

// DEPRECATED: Support Messages API (legacy, use Thread-based API instead)
/**
 * @deprecated Use getSupportThreads instead
 */
export async function getSupportMessages(params?: {
	status_filter?: string;
	limit?: number;
	offset?: number;
}): Promise<SupportMessageListResponse> {
	const response = await adminClient.get<SupportMessageListResponse>('/support/messages', { params });
	return response.data;
}

/**
 * @deprecated Use getSupportThreadDetails instead
 */
export async function getSupportMessageDetails(message_id: string): Promise<SupportMessageResponse> {
	const response = await adminClient.get<SupportMessageResponse>(`/support/messages/${message_id}`);
	return response.data;
}

/**
 * @deprecated Use replyToThread instead
 */
export async function respondToSupportMessage(
	message_id: string,
	data: RespondToMessageRequest
): Promise<SupportMessageResponse> {
	const response = await adminClient.post<SupportMessageResponse>(`/support/messages/${message_id}/respond`, data);
	return response.data;
}

/**
 * @deprecated Use updateThreadStatus instead
 */
export async function updateSupportMessageStatus(
	message_id: string,
	status: string
): Promise<SupportMessageResponse> {
	const response = await adminClient.patch<SupportMessageResponse>(`/support/messages/${message_id}/status`, null, {
		params: { status_value: status }
	});
	return response.data;
}

// Contact Thread API
export async function getContactThreads(params?: {
	status_filter?: string;
	message_type_filter?: string;
	unread_only?: boolean;
	limit?: number;
	offset?: number;
}): Promise<ContactThreadListResponse> {
	const response = await adminClient.get<ContactThreadListResponse>('/contact/threads', { params });
	return response.data;
}

export async function getContactThreadUnreadCount(): Promise<{ count: number }> {
	const response = await adminClient.get<{ count: number }>('/contact/threads/unread-count');
	return response.data;
}

export async function getContactThreadDetails(thread_id: string): Promise<ContactThreadResponse> {
	const response = await adminClient.get<ContactThreadResponse>(`/contact/threads/${thread_id}`);
	return response.data;
}

export async function getContactThreadMessages(
	thread_id: string,
	params?: { limit?: number; offset?: number }
): Promise<ContactMessageListResponse> {
	const response = await adminClient.get<ContactMessageListResponse>(`/contact/threads/${thread_id}/messages`, { params });
	return response.data;
}

export async function replyToContactThread(
	thread_id: string,
	data: CreateContactMessageRequest
): Promise<ContactMessageResponse> {
	const response = await adminClient.post<ContactMessageResponse>(`/contact/threads/${thread_id}/messages`, data);
	return response.data;
}

export async function updateContactThreadStatus(
	thread_id: string,
	data: UpdateContactThreadStatusRequest
): Promise<ContactThreadResponse> {
	const response = await adminClient.patch<ContactThreadResponse>(`/contact/threads/${thread_id}/status`, data);
	return response.data;
}

export async function markContactThreadMessagesAsRead(
	thread_id: string
): Promise<{ success: boolean; updated_count: number }> {
	const response = await adminClient.patch<{ success: boolean; updated_count: number }>(`/contact/threads/${thread_id}/mark-read`);
	return response.data;
}

/**
 * @deprecated Use getContactThreads instead
 */
export async function getContactMessages(params?: {
	status_filter?: string;
	message_type_filter?: string;
	limit?: number;
	offset?: number;
}): Promise<any> {
	const response = await adminClient.get('/contact/messages', { params });
	return response.data;
}

/**
 * @deprecated Use getContactThreadDetails instead
 */
export async function getContactMessageDetails(message_id: string): Promise<any> {
	const response = await adminClient.get(`/contact/messages/${message_id}`);
	return response.data;
}

/**
 * @deprecated Use replyToContactThread instead
 */
export async function respondToContactMessage(
	message_id: string,
	data: RespondToMessageRequest
): Promise<any> {
	const response = await adminClient.post(`/contact/messages/${message_id}/respond`, data);
	return response.data;
}

export async function updateContactMessageStatus(
	message_id: string,
	status: string
): Promise<ContactMessageResponse> {
	const response = await adminClient.patch<ContactMessageResponse>(`/contact/messages/${message_id}/status`, null, {
		params: { status_value: status }
	});
	return response.data;
}

// Maintenance Mode API

export interface MaintenanceModeResponse {
	id: string;
	service_name: string;
	is_active: boolean;
	message: string | null;
	created_at: string;
	updated_at: string;
}

export interface CreateMaintenanceModeRequest {
	service_name: string;
	is_active?: boolean;
	message?: string;
}

export interface UpdateMaintenanceModeRequest {
	is_active?: boolean;
	message?: string;
}

export interface MaintenanceModeListResponse {
	maintenance_modes: MaintenanceModeResponse[];
	total_count: number;
}

export async function getMaintenanceModes(isActive?: boolean): Promise<MaintenanceModeListResponse> {
	const response = await adminClient.get<MaintenanceModeListResponse>('/maintenance/', {
		params: isActive !== undefined ? { is_active: isActive } : {}
	});
	return response.data;
}

export async function getMaintenanceMode(serviceName: string): Promise<MaintenanceModeResponse> {
	const response = await adminClient.get<MaintenanceModeResponse>(`/maintenance/${serviceName}`);
	return response.data;
}

export async function createMaintenanceMode(data: CreateMaintenanceModeRequest): Promise<MaintenanceModeResponse> {
	const response = await adminClient.post<MaintenanceModeResponse>('/maintenance/', data);
	return response.data;
}

export async function updateMaintenanceMode(serviceName: string, data: UpdateMaintenanceModeRequest): Promise<MaintenanceModeResponse> {
	const response = await adminClient.patch<MaintenanceModeResponse>(`/maintenance/${serviceName}`, data);
	return response.data;
}

export async function deleteMaintenanceMode(serviceName: string): Promise<{ message: string }> {
	const response = await adminClient.delete<{ message: string }>(`/maintenance/${serviceName}`);
	return response.data;
}

export async function toggleMaintenanceMode(serviceName: string): Promise<MaintenanceModeResponse> {
	const response = await adminClient.post<MaintenanceModeResponse>(`/maintenance/${serviceName}/toggle`);
	return response.data;
}

// Custom Pricing API

export interface CustomPricingResponse {
	id: string;
	access_code?: string;
	user_id?: string;
	username?: string;
	service_name: string;
	price: string;
	is_active: boolean;
	created_at: string;
	updated_at: string;
}

export interface CreateCustomPricingRequest {
	access_code?: string;
	user_id?: string;
	service_name: string;
	price: string;
	is_active?: boolean;
}

export interface UpdateCustomPricingRequest {
	price?: string;
	is_active?: boolean;
}

export interface CustomPricingListResponse {
	custom_pricing: CustomPricingResponse[];
	total_count: number;
}

export async function getCustomPricing(params?: {
	access_code?: string;
	user_id?: string;
	service_name?: string;
	is_active?: boolean;
	limit?: number;
	offset?: number;
}): Promise<CustomPricingListResponse> {
	const response = await adminClient.get<CustomPricingListResponse>('/custom-pricing/', { params });
	return response.data;
}

export async function getCustomPricingById(id: string): Promise<CustomPricingResponse> {
	const response = await adminClient.get<CustomPricingResponse>(`/custom-pricing/${id}`);
	return response.data;
}

export async function getCustomPricingByCode(accessCode: string): Promise<CustomPricingResponse[]> {
	const response = await adminClient.get<CustomPricingResponse[]>(`/custom-pricing/by-code/${accessCode}`);
	return response.data;
}

export async function getCustomPricingByUserId(userId: string): Promise<CustomPricingResponse[]> {
	const response = await adminClient.get<CustomPricingResponse[]>(`/custom-pricing/by-user/${userId}`);
	return response.data;
}

export async function searchUsers(query: string): Promise<UserTableItem[]> {
	const response = await getUserTable({ search: query, limit: 10 });
	return response.users;
}

export async function createCustomPricing(data: CreateCustomPricingRequest): Promise<CustomPricingResponse> {
	const response = await adminClient.post<CustomPricingResponse>('/custom-pricing/', data);
	return response.data;
}

export async function updateCustomPricing(id: string, data: UpdateCustomPricingRequest): Promise<CustomPricingResponse> {
	const response = await adminClient.patch<CustomPricingResponse>(`/custom-pricing/${id}`, data);
	return response.data;
}

export async function deleteCustomPricing(id: string): Promise<{ message: string }> {
	const response = await adminClient.delete<{ message: string }>(`/custom-pricing/${id}`);
	return response.data;
}

export async function toggleCustomPricing(id: string): Promise<CustomPricingResponse> {
	const response = await adminClient.post<CustomPricingResponse>(`/custom-pricing/${id}/toggle`);
	return response.data;
}

// Error handling helper
export function handleApiError(error: AxiosError): string {
	if (error.response) {
		const status = error.response.status;
		const data = error.response.data as { detail?: string; message?: string };

		// Handle specific HTTP status codes
		if (status === 401) {
			return 'Authentication failed. Please login again.';
		} else if (status === 403) {
			return 'Access denied. Insufficient permissions.';
		} else if (status === 404) {
			return 'Resource not found.';
		} else if (status >= 500) {
			return 'Server error occurred. Please try again later.';
		}

		// Return specific error message from response
		if (data) {
			return data.detail || data.message || 'Unknown error occurred';
		}

		return `Request failed with status ${status}`;
	}

	// Network or timeout error
	if (error.code === 'ECONNABORTED') {
		return 'Request timeout. Please try again.';
	} else if (error.code === 'ERR_NETWORK') {
		return 'Network error. Please check your connection.';
	}

	return error.message || 'Network error occurred';
}

// User Ban Management API

/**
 * Get list of banned users
 */
export async function getBannedUsers(params?: {
	limit?: number;
	offset?: number;
	search?: string;
}): Promise<BannedUsersListResponse> {
	const response = await adminClient.get<BannedUsersListResponse>('/users/banned', { params });
	return response.data;
}

/**
 * Unban a user
 */
export async function unbanUser(user_id: string): Promise<UnbanUserResponse> {
	const response = await adminClient.patch<UnbanUserResponse>(`/users/${user_id}/unban`);
	return response.data;
}

/**
 * Ban a user
 */
export async function banUser(user_id: string, reason: string): Promise<BanUserResponse> {
	const response = await adminClient.post<BanUserResponse>(`/users/${user_id}/ban`, {
		reason
	});
	return response.data;
}
