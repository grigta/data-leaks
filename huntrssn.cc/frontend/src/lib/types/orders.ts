// Order type filter union type
// Note: 'reverse_ssn' is deprecated but kept for displaying historical orders
export type OrderTypeFilter = 'instant_ssn' | 'manual_ssn' | 'reverse_ssn' | 'all';

// Constants for pagination
export const ORDERS_PAGE_SIZE = 50;
export const ORDERS_FETCH_LIMIT = 50;
export const ORDERS_EXPORT_PAGE_SIZE = 100;
