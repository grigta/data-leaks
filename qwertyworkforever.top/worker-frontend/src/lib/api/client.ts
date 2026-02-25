import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api/worker',
  headers: { 'Content-Type': 'application/json' }
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('worker_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('worker_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export interface LoginParams {
  access_code: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface WorkerUser {
  username: string;
  email: string;
  worker_role: boolean;
  wallet_address: string | null;
  wallet_network: string | null;
}

export interface Ticket {
  id: string;
  user_id: string;
  username: string;
  firstname: string;
  lastname: string;
  address: string;
  status: string;
  worker_id: string | null;
  worker_username: string | null;
  response_data: Record<string, string> | null;
  created_at: string;
  updated_at: string;
}

export interface TicketListResponse {
  tickets: Ticket[];
  total_count: number;
}

export interface HistoryStats {
  total: number;
  completed: number;
  rejected: number;
  success_rate: number;
  avg_time: string;
  payout: string;
}

export interface HistoryResponse {
  tickets: Ticket[];
  total_count: number;
  stats: HistoryStats;
}

export interface UpdateTicketParams {
  status?: string;
  response_data?: Record<string, string>;
}

export const login = async (params: LoginParams): Promise<TokenResponse> => {
  const response = await apiClient.post<TokenResponse>('/auth/login', {
    access_code: params.access_code
  });
  return response.data;
};

export const getMe = async (): Promise<WorkerUser> => {
  const response = await apiClient.get<WorkerUser>('/auth/me');
  return response.data;
};

export const getMyTickets = async (
  statusFilter?: string,
  limit = 50,
  offset = 0
): Promise<TicketListResponse> => {
  const response = await apiClient.get<TicketListResponse>('/tickets/my', {
    params: { status_filter: statusFilter, limit, offset }
  });
  return response.data;
};

export const getHistory = async (
  period?: string,
  limit = 50,
  offset = 0
): Promise<HistoryResponse> => {
  const response = await apiClient.get<HistoryResponse>('/tickets/history', {
    params: { period, limit, offset }
  });
  return response.data;
};

export const getTicket = async (ticketId: string): Promise<Ticket> => {
  const response = await apiClient.get<Ticket>(`/tickets/${ticketId}`);
  return response.data;
};

export const updateTicket = async (
  ticketId: string,
  params: UpdateTicketParams
): Promise<Ticket> => {
  const response = await apiClient.patch<Ticket>(`/tickets/${ticketId}`, params);
  return response.data;
};

export const respondToTicket = async (ticketId: string, text: string): Promise<Ticket> => {
  const response = await apiClient.post<Ticket>(`/tickets/${ticketId}/respond`, { text });
  return response.data;
};

export const rejectTicket = async (ticketId: string): Promise<Ticket> => {
  const response = await apiClient.post<Ticket>(`/tickets/${ticketId}/reject`);
  return response.data;
};

// Wallet & Withdraw

export interface WalletInfo {
  wallet_address: string | null;
  wallet_network: string | null;
  total_earned: string;
  total_paid: string;
  available_balance: string;
}

export interface InvoiceItem {
  id: string;
  amount: string;
  wallet_address: string;
  wallet_network: string;
  status: string;
  paid_at: string | null;
  created_at: string;
}

export interface InvoiceListResponse {
  invoices: InvoiceItem[];
  total_count: number;
}

export const getWallet = async (): Promise<WalletInfo> => {
  const response = await apiClient.get<WalletInfo>('/wallet/me');
  return response.data;
};

export const updateWallet = async (params: {
  wallet_address: string;
  wallet_network: string;
}): Promise<WalletInfo> => {
  const response = await apiClient.put<WalletInfo>('/wallet/me', params);
  return response.data;
};

export const createWithdraw = async (params: { amount: number }): Promise<InvoiceItem> => {
  const response = await apiClient.post<InvoiceItem>('/wallet/withdraw', params);
  return response.data;
};

export const getInvoices = async (
  limit = 50,
  offset = 0
): Promise<InvoiceListResponse> => {
  const response = await apiClient.get<InvoiceListResponse>('/wallet/invoices', {
    params: { limit, offset }
  });
  return response.data;
};

// Shift

export interface ShiftResponse {
  id: string | null;
  worker_status: 'idle' | 'active' | 'paused';
  started_at: string | null;
  elapsed_seconds: number;
  pause_duration_seconds: number;
  tickets_completed: number;
  tickets_rejected: number;
}

export interface ShiftHistoryItem {
  id: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  pause_duration_seconds: number;
  tickets_completed: number;
  tickets_rejected: number;
}

export interface ShiftHistoryResponse {
  shifts: ShiftHistoryItem[];
  total_count: number;
}

export const getCurrentShift = async (): Promise<ShiftResponse> => {
  const response = await apiClient.get<ShiftResponse>('/shift/current');
  return response.data;
};

export const startShift = async (): Promise<ShiftResponse> => {
  const response = await apiClient.post<ShiftResponse>('/shift/start');
  return response.data;
};

export const pauseShift = async (): Promise<ShiftResponse> => {
  const response = await apiClient.post<ShiftResponse>('/shift/pause');
  return response.data;
};

export const resumeShift = async (): Promise<ShiftResponse> => {
  const response = await apiClient.post<ShiftResponse>('/shift/resume');
  return response.data;
};

export const stopShift = async (): Promise<ShiftResponse> => {
  const response = await apiClient.post<ShiftResponse>('/shift/stop');
  return response.data;
};

export const getShiftHistory = async (
  limit = 50,
  offset = 0
): Promise<ShiftHistoryResponse> => {
  const response = await apiClient.get<ShiftHistoryResponse>('/shift/history', {
    params: { limit, offset }
  });
  return response.data;
};

export default apiClient;
