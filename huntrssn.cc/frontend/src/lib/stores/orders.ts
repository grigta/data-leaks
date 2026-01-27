import { writable } from 'svelte/store';
import { browser } from '$app/environment';
import {
	getUnviewedOrdersCount,
	markOrdersAsViewed as apiMarkOrdersAsViewed
} from '$lib/api/client';

// Helper functions for safe localStorage operations
function safeLocalStorageSet(key: string, value: string): boolean {
	if (!browser) return false;
	try {
		localStorage.setItem(key, value);
		return true;
	} catch (error) {
		if (error instanceof DOMException && error.name === 'QuotaExceededError') {
			console.error('localStorage quota exceeded for orders cache, attempting cleanup:', error);
			// Try to clear orders cache and retry once
			try {
				const cacheKey = getOrdersCacheKey(currentUserId);
				localStorage.removeItem(cacheKey);
				localStorage.setItem(key, value);
				return true;
			} catch (retryError) {
				console.error('Failed to save to localStorage even after cleanup:', retryError);
				return false;
			}
		}
		console.error('Failed to write orders count to localStorage:', error);
		return false;
	}
}

function safeLocalStorageGet(key: string): string | null {
	if (!browser) return null;
	try {
		return localStorage.getItem(key);
	} catch (error) {
		console.error('Failed to read orders count from localStorage:', error);
		return null;
	}
}

function safeLocalStorageRemove(key: string): void {
	if (!browser) return;
	try {
		localStorage.removeItem(key);
	} catch (error) {
		console.error('Failed to remove orders count from localStorage:', error);
	}
}

// Constants for caching
const ORDERS_COUNT_CACHE_KEY_PREFIX = 'orders-count-cache';
const ORDERS_COUNT_CACHE_TTL = 2 * 60 * 1000; // 2 minutes in milliseconds

// Get user-scoped cache key
function getOrdersCacheKey(userId?: string): string {
	if (!userId) return ORDERS_COUNT_CACHE_KEY_PREFIX;
	return `${ORDERS_COUNT_CACHE_KEY_PREFIX}:${userId}`;
}

// Interface for cached data
interface OrdersCountCache {
	count: number;
	timestamp: number;
}

// Internal state to track current user
let currentUserId: string | undefined;

export function setOrdersUserId(userId: string | undefined): void {
	currentUserId = userId;
}

const unviewedOrdersCount = writable<number>(0);

// BroadcastChannel for cross-tab synchronization
const ordersChannel =
	typeof BroadcastChannel !== 'undefined' && browser ? new BroadcastChannel('orders-sync') : null;

// Types for broadcast messages
type OrdersMessage = { type: 'count-updated'; count: number } | { type: 'marked-viewed' };

// Listen for messages from other tabs
if (ordersChannel) {
	ordersChannel.onmessage = (event: MessageEvent<OrdersMessage>) => {
		const message = event.data;
		if (message.type === 'count-updated') {
			unviewedOrdersCount.set(message.count);
			saveCountToCache(message.count);
		} else if (message.type === 'marked-viewed') {
			unviewedOrdersCount.set(0);
			saveCountToCache(0);
		}
	};
}

// Cache management functions
function saveCountToCache(count: number): void {
	const cache: OrdersCountCache = {
		count,
		timestamp: Date.now()
	};
	const cacheKey = getOrdersCacheKey(currentUserId);
	const saved = safeLocalStorageSet(cacheKey, JSON.stringify(cache));
	if (!saved) {
		console.warn('Failed to cache orders count');
	}
}

function loadCountFromCache(): number | null {
	const cacheKey = getOrdersCacheKey(currentUserId);
	const cached = safeLocalStorageGet(cacheKey);
	if (!cached) return null;

	try {
		const cache: OrdersCountCache = JSON.parse(cached);
		const age = Date.now() - cache.timestamp;

		if (age > ORDERS_COUNT_CACHE_TTL) {
			console.debug('Orders count cache expired');
			return null;
		}

		console.debug('Loaded orders count from cache');
		return cache.count;
	} catch (error) {
		console.error('Failed to parse orders count cache:', error);
		return null;
	}
}

export function clearOrdersCache(): void {
	const cacheKey = getOrdersCacheKey(currentUserId);
	safeLocalStorageRemove(cacheKey);
}

// Load unviewed orders count
export async function loadUnviewedOrdersCount(): Promise<void> {
	try {
		const count = await getUnviewedOrdersCount();
		unviewedOrdersCount.set(count);
		saveCountToCache(count);
		// Broadcast update to other tabs
		ordersChannel?.postMessage({ type: 'count-updated', count });
	} catch (error) {
		console.error('Failed to load unviewed orders count from server:', error);
		// Try to load from cache as fallback
		const cachedCount = loadCountFromCache();
		if (cachedCount !== null) {
			console.debug('Using cached orders count as fallback');
			unviewedOrdersCount.set(cachedCount);
		} else {
			// No cache available - set 0
			console.warn('No cache available, using count 0');
			unviewedOrdersCount.set(0);
		}
	}
}

// Mark all orders as viewed
export async function markOrdersAsViewed(): Promise<void> {
	try {
		await apiMarkOrdersAsViewed();
		unviewedOrdersCount.set(0);
		saveCountToCache(0);
		// Broadcast update to other tabs
		ordersChannel?.postMessage({ type: 'marked-viewed' });
	} catch (error) {
		console.error('Failed to mark orders as viewed:', error);
		// Don't update cache on error - keep current value
	}
}

// Increment unviewed count (for use after creating an order)
export function incrementUnviewedCount(): void {
	unviewedOrdersCount.update((count) => {
		const newCount = count + 1;
		saveCountToCache(newCount);
		// Broadcast update to other tabs
		ordersChannel?.postMessage({ type: 'count-updated', count: newCount });
		return newCount;
	});
}

// Force sync count from server
export async function syncUnviewedCount(): Promise<void> {
	try {
		const count = await getUnviewedOrdersCount();
		unviewedOrdersCount.set(count);
		saveCountToCache(count);
		// Broadcast update to other tabs
		ordersChannel?.postMessage({ type: 'count-updated', count });
	} catch (error) {
		console.error('Failed to sync unviewed orders count:', error);
		throw error;
	}
}

// Export store
export { unviewedOrdersCount };

// Removed auto-load to prevent race conditions during initialization
// Orders count should be loaded explicitly after auth initialization
