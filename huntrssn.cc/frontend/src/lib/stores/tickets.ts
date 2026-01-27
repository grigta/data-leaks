import { writable } from 'svelte/store';
import { browser } from '$app/environment';
import {
	getUnviewedTicketsCount,
	markTicketsAsViewed as apiMarkTicketsAsViewed
} from '$lib/api/client';

// Helper functions for safe localStorage operations
function safeLocalStorageSet(key: string, value: string): boolean {
	if (!browser) return false;
	try {
		localStorage.setItem(key, value);
		return true;
	} catch (error) {
		if (error instanceof DOMException && error.name === 'QuotaExceededError') {
			console.error('localStorage quota exceeded for tickets cache, attempting cleanup:', error);
			// Try to clear tickets cache and retry once
			try {
				const cacheKey = getTicketsCacheKey(currentUserId);
				localStorage.removeItem(cacheKey);
				localStorage.setItem(key, value);
				return true;
			} catch (retryError) {
				console.error('Failed to save to localStorage even after cleanup:', retryError);
				return false;
			}
		}
		console.error('Failed to write tickets count to localStorage:', error);
		return false;
	}
}

function safeLocalStorageGet(key: string): string | null {
	if (!browser) return null;
	try {
		return localStorage.getItem(key);
	} catch (error) {
		console.error('Failed to read tickets count from localStorage:', error);
		return null;
	}
}

function safeLocalStorageRemove(key: string): void {
	if (!browser) return;
	try {
		localStorage.removeItem(key);
	} catch (error) {
		console.error('Failed to remove tickets count from localStorage:', error);
	}
}

// Constants for caching
const TICKETS_COUNT_CACHE_KEY_PREFIX = 'tickets-count-cache';
const TICKETS_COUNT_CACHE_TTL = 2 * 60 * 1000; // 2 minutes in milliseconds

// Get user-scoped cache key
function getTicketsCacheKey(userId?: string): string {
	if (!userId) return TICKETS_COUNT_CACHE_KEY_PREFIX;
	return `${TICKETS_COUNT_CACHE_KEY_PREFIX}:${userId}`;
}

// Interface for cached data
interface TicketsCountCache {
	count: number;
	timestamp: number;
}

// Internal state to track current user
let currentUserId: string | undefined;

export function setTicketsUserId(userId: string | undefined): void {
	currentUserId = userId;
}

const unviewedTicketsCount = writable<number>(0);

// BroadcastChannel for cross-tab synchronization
const ticketsChannel =
	typeof BroadcastChannel !== 'undefined' && browser ? new BroadcastChannel('tickets-sync') : null;

// Types for broadcast messages
type TicketsMessage = { type: 'count-updated'; count: number } | { type: 'marked-viewed' };

// Listen for messages from other tabs
if (ticketsChannel) {
	ticketsChannel.onmessage = (event: MessageEvent<TicketsMessage>) => {
		const message = event.data;
		if (message.type === 'count-updated') {
			unviewedTicketsCount.set(message.count);
			saveCountToCache(message.count);
		} else if (message.type === 'marked-viewed') {
			unviewedTicketsCount.set(0);
			saveCountToCache(0);
		}
	};
}

// Cache management functions
function saveCountToCache(count: number): void {
	const cache: TicketsCountCache = {
		count,
		timestamp: Date.now()
	};
	const cacheKey = getTicketsCacheKey(currentUserId);
	const saved = safeLocalStorageSet(cacheKey, JSON.stringify(cache));
	if (!saved) {
		console.warn('Failed to cache tickets count');
	}
}

function loadCountFromCache(): number | null {
	const cacheKey = getTicketsCacheKey(currentUserId);
	const cached = safeLocalStorageGet(cacheKey);
	if (!cached) return null;

	try {
		const cache: TicketsCountCache = JSON.parse(cached);
		const age = Date.now() - cache.timestamp;

		if (age > TICKETS_COUNT_CACHE_TTL) {
			console.debug('Tickets count cache expired');
			return null;
		}

		console.debug('Loaded tickets count from cache');
		return cache.count;
	} catch (error) {
		console.error('Failed to parse tickets count cache:', error);
		return null;
	}
}

export function clearTicketsCache(): void {
	const cacheKey = getTicketsCacheKey(currentUserId);
	safeLocalStorageRemove(cacheKey);
}

// Load unviewed tickets count
export async function loadUnviewedTicketsCount(): Promise<void> {
	try {
		const count = await getUnviewedTicketsCount();
		unviewedTicketsCount.set(count);
		saveCountToCache(count);
		// Broadcast update to other tabs
		ticketsChannel?.postMessage({ type: 'count-updated', count });
	} catch (error) {
		console.error('Failed to load unviewed tickets count from server:', error);
		// Try to load from cache as fallback
		const cachedCount = loadCountFromCache();
		if (cachedCount !== null) {
			console.debug('Using cached tickets count as fallback');
			unviewedTicketsCount.set(cachedCount);
		} else {
			// No cache available - set 0
			console.warn('No cache available, using count 0');
			unviewedTicketsCount.set(0);
		}
	}
}

// Mark tickets as viewed
export async function markTicketsAsViewed(ticketIds: string[]): Promise<void> {
	try {
		await apiMarkTicketsAsViewed(ticketIds);
		// Reload count from server to get accurate count
		await loadUnviewedTicketsCount();
	} catch (error) {
		console.error('Failed to mark tickets as viewed:', error);
		// Don't update cache on error - keep current value
	}
}

// Increment unviewed count (for use when a ticket is completed by admin)
export function incrementUnviewedTicketsCount(): void {
	unviewedTicketsCount.update((count) => {
		const newCount = count + 1;
		saveCountToCache(newCount);
		// Broadcast update to other tabs
		ticketsChannel?.postMessage({ type: 'count-updated', count: newCount });
		return newCount;
	});
}

// Force sync count from server
export async function syncUnviewedTicketsCount(): Promise<void> {
	try {
		const count = await getUnviewedTicketsCount();
		unviewedTicketsCount.set(count);
		saveCountToCache(count);
		// Broadcast update to other tabs
		ticketsChannel?.postMessage({ type: 'count-updated', count });
	} catch (error) {
		console.error('Failed to sync unviewed tickets count:', error);
		throw error;
	}
}

// Export store
export { unviewedTicketsCount };
