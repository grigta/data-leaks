import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind CSS classes intelligently, resolving conflicts
 * @param inputs - Class values to merge
 * @returns Merged class string
 */
export function cn(...inputs: ClassValue[]): string {
	return twMerge(clsx(inputs));
}

/**
 * Format number as USD currency
 * @param amount - Numeric amount
 * @returns Formatted currency string (e.g., "$1,234.56")
 */
export function formatCurrency(amount: number): string {
	return new Intl.NumberFormat('en-US', {
		style: 'currency',
		currency: 'USD'
	}).format(amount);
}

/**
 * Format date in readable format
 * @param date - Date string or Date object
 * @returns Formatted date string (e.g., "Jan 15, 2024")
 */
export function formatDate(date: string | Date): string {
	if (!date) return '';

	const dateObj = typeof date === 'string' ? new Date(date) : date;

	// Check if date is valid
	if (isNaN(dateObj.getTime())) {
		return date.toString();
	}

	return new Intl.DateTimeFormat('en-US', {
		month: 'short',
		day: 'numeric',
		year: 'numeric'
	}).format(dateObj);
}

/**
 * Format date with time in readable format
 * @param date - Date string or Date object
 * @returns Formatted date and time string (e.g., "Jan 15, 2024 at 10:30 AM")
 */
export function formatDateTime(date: string | Date): string {
	if (!date) return '';

	const dateObj = typeof date === 'string' ? new Date(date) : date;

	// Check if date is valid
	if (isNaN(dateObj.getTime())) {
		return date.toString();
	}

	return new Intl.DateTimeFormat('en-US', {
		month: 'short',
		day: 'numeric',
		year: 'numeric',
		hour: 'numeric',
		minute: '2-digit',
		hour12: true
	}).format(dateObj);
}

/**
 * Format percentage with 2 decimal places
 * @param value - Numeric value (e.g., 0.75 for 75%)
 * @returns Formatted percentage string (e.g., "75.00%")
 */
export function formatPercentage(value: number): string {
	return `${(value * 100).toFixed(2)}%`;
}

/**
 * Format large numbers with commas
 * @param value - Numeric value
 * @returns Formatted number string (e.g., "1,234,567")
 */
export function formatNumber(value: number): string {
	return new Intl.NumberFormat('en-US').format(value);
}

/**
 * Get Tailwind CSS color class for transaction/order status
 * @param status - Status string (pending, paid, expired, failed, completed, cancelled)
 * @returns Tailwind CSS color class
 */
export function getStatusColor(status: string): string {
	switch (status.toLowerCase()) {
		case 'pending':
			return 'text-yellow-600 bg-yellow-50 border-yellow-200';
		case 'paid':
		case 'completed':
			return 'text-green-600 bg-green-50 border-green-200';
		case 'expired':
		case 'cancelled':
			return 'text-gray-600 bg-gray-50 border-gray-200';
		case 'failed':
			return 'text-red-600 bg-red-50 border-red-200';
		default:
			return 'text-gray-600 bg-gray-50 border-gray-200';
	}
}

/**
 * Truncate text with ellipsis
 * @param text - Text to truncate
 * @param maxLength - Maximum length before truncation
 * @returns Truncated text with ellipsis if needed
 */
export function truncate(text: string, maxLength: number): string {
	if (!text || text.length <= maxLength) return text;
	return `${text.slice(0, maxLength)}...`;
}

/**
 * Calculate processing time between two dates in minutes
 * @param created_at - Start date (ISO string or Date)
 * @param updated_at - End date (ISO string or Date)
 * @returns Formatted time string (e.g., "15 мин", "2 ч 30 мин", "1 д 3 ч")
 */
export function calculateProcessingTime(
	created_at: string | Date,
	updated_at: string | Date
): string {
	if (!created_at || !updated_at) return 'N/A';

	const start = typeof created_at === 'string' ? new Date(created_at) : created_at;
	const end = typeof updated_at === 'string' ? new Date(updated_at) : updated_at;

	// Check if dates are valid
	if (isNaN(start.getTime()) || isNaN(end.getTime())) {
		return 'N/A';
	}

	const diffMs = end.getTime() - start.getTime();
	const diffMinutes = Math.floor(diffMs / 60000);

	if (diffMinutes < 1) {
		return '< 1 мин';
	} else if (diffMinutes < 60) {
		return `${diffMinutes} мин`;
	} else if (diffMinutes < 1440) {
		// Less than 24 hours
		const hours = Math.floor(diffMinutes / 60);
		const minutes = diffMinutes % 60;
		return minutes > 0 ? `${hours} ч ${minutes} мин` : `${hours} ч`;
	} else {
		// 24+ hours
		const days = Math.floor(diffMinutes / 1440);
		const hours = Math.floor((diffMinutes % 1440) / 60);
		return hours > 0 ? `${days} д ${hours} ч` : `${days} д`;
	}
}

/**
 * Calculate waiting time from creation until now
 * @param created_at - Creation date (ISO string or Date)
 * @returns Formatted time string (e.g., "15 мин", "2 ч 30 мин", "1 д 3 ч")
 */
export function calculateWaitingTime(created_at: string | Date): string {
	if (!created_at) return 'N/A';

	const start = typeof created_at === 'string' ? new Date(created_at) : created_at;
	const now = new Date();

	// Check if date is valid
	if (isNaN(start.getTime())) {
		return 'N/A';
	}

	const diffMs = now.getTime() - start.getTime();
	const diffMinutes = Math.floor(diffMs / 60000);

	if (diffMinutes < 1) {
		return '< 1 мин';
	} else if (diffMinutes < 60) {
		return `${diffMinutes} мин`;
	} else if (diffMinutes < 1440) {
		// Less than 24 hours
		const hours = Math.floor(diffMinutes / 60);
		const minutes = diffMinutes % 60;
		return minutes > 0 ? `${hours} ч ${minutes} мин` : `${hours} ч`;
	} else {
		// 24+ hours
		const days = Math.floor(diffMinutes / 1440);
		const hours = Math.floor((diffMinutes % 1440) / 60);
		return hours > 0 ? `${days} д ${hours} ч` : `${days} д`;
	}
}
