/**
 * High-level abstraction for creating persistent Svelte stores with automatic
 * localStorage synchronization, BroadcastChannel cross-tab sync, retry logic,
 * and graceful degradation.
 *
 * @module persistent-store
 * @example
 * import { createPersistentStore } from '$lib/utils/persistent-store';
 *
 * const userStore = createPersistentStore('user', null, {
 *   ttl: 3600000, // 1 hour
 *   broadcastChannel: 'user-sync',
 *   onError: (error) => console.error('Store error:', error)
 * });
 *
 * userStore.set({ id: 1, name: 'John' });
 * const user = userStore.get();
 */

import { writable, type Writable } from 'svelte/store';
import { browser } from '$app/environment';
import {
	createVersionedStorage,
	setWithTTL,
	getWithTTL,
	cleanupExpired,
	isStorageAvailable,
	type MigrationFunction
} from './storage';

/**
 * Message types for BroadcastChannel synchronization
 */
export type BroadcastMessage<T> =
	| { type: 'update'; data: T; timestamp: number }
	| { type: 'clear' }
	| { type: 'reset' };

/**
 * Options for creating a persistent store
 */
export type PersistentStoreOptions<T> = {
	/** Storage key for localStorage */
	key: string;
	/** Time to live in milliseconds */
	ttl?: number;
	/** BroadcastChannel name for cross-tab sync */
	broadcastChannel?: string;
	/** Data schema version */
	version?: number;
	/** Migration functions for version upgrades */
	migrations?: Record<number, MigrationFunction<T>>;
	/** Error handler callback */
	onError?: (error: Error) => void;
	/** Debounce delay before saving (ms) */
	debounceMs?: number;
	/** Sync on initialization */
	syncOnInit?: boolean;
	/** Fallback value when storage read fails or throws an error (not used when cached data is missing) */
	fallbackValue?: T;
};

/**
 * Enhanced Svelte store with persistence capabilities
 */
export interface PersistentStore<T> extends Writable<T> {
	/** Force synchronization with localStorage */
	sync(): Promise<void>;
	/** Clear store and localStorage */
	clear(): void;
	/** Reset to fallback value */
	reset(): void;
	/** Cleanup resources (close BroadcastChannel, unsubscribe) */
	destroy(): void;
	/** Check if localStorage is available */
	isAvailable(): boolean;
}

/**
 * Create a debounced save function
 */
function createDebouncedSave<T>(saveFn: (value: T) => void, delayMs: number) {
	let timeoutId: ReturnType<typeof setTimeout> | null = null;

	function debounced(value: T) {
		if (timeoutId !== null) {
			clearTimeout(timeoutId);
		}
		timeoutId = setTimeout(() => {
			saveFn(value);
			timeoutId = null;
		}, delayMs);
	}

	function cancel() {
		if (timeoutId !== null) {
			clearTimeout(timeoutId);
			timeoutId = null;
		}
	}

	return { debounced, cancel };
}

/**
 * Create BroadcastChannel sync helper
 */
function createBroadcastSync<T>(
	channelName: string,
	onMessage: (message: BroadcastMessage<T>) => void
) {
	if (!browser) {
		return {
			send: () => {},
			close: () => {}
		};
	}

	const channel = new BroadcastChannel(channelName);
	channel.onmessage = (event: MessageEvent<BroadcastMessage<T>>) => {
		onMessage(event.data);
	};

	return {
		send: (message: BroadcastMessage<T>) => {
			channel.postMessage(message);
		},
		close: () => {
			channel.close();
		}
	};
}

/**
 * Create a persistent Svelte store with automatic localStorage synchronization,
 * cross-tab sync via BroadcastChannel, and graceful degradation.
 *
 * @template T - Type of data stored
 * @param initialValue - Initial value if no cached data exists
 * @param options - Configuration options
 * @returns Enhanced Svelte store with persistence capabilities
 *
 * @example
 * ```typescript
 * // Simple persistent store
 * const themeStore = createPersistentStore('dark', {
 *   key: 'theme',
 *   broadcastChannel: 'theme-sync'
 * });
 *
 * // With versioning and migrations
 * const userStore = createPersistentStore(null, {
 *   key: 'user',
 *   version: 2,
 *   migrations: {
 *     1: (data) => ({ ...data, newField: 'default' })
 *   },
 *   ttl: 3600000,
 *   broadcastChannel: 'user-sync'
 * });
 *
 * // Usage in component
 * import { onDestroy } from 'svelte';
 * const store = createPersistentStore(...);
 * onDestroy(() => store.destroy());
 * ```
 *
 * @see {@link createCachedStore} for server data caching
 * @see {@link storage} for low-level storage utilities
 */
export function createPersistentStore<T>(
	initialValue: T,
	options: PersistentStoreOptions<T>
): PersistentStore<T> {
	const {
		key,
		ttl,
		broadcastChannel,
		version = 1,
		migrations = {},
		onError,
		debounceMs,
		syncOnInit = true,
		fallbackValue
	} = options;

	// Check localStorage availability
	const storageAvailable = isStorageAvailable();

	// Create versioned storage handler
	const versionedStorage = createVersionedStorage<T>(key, version, migrations);

	// Load initial value from storage
	let loadedValue: T | null = null;
	let loadFailed = false;
	if (storageAvailable && syncOnInit) {
		try {
			if (ttl) {
				loadedValue = getWithTTL<T>(key);
			} else {
				loadedValue = versionedStorage.get();
			}
		} catch (error) {
			loadFailed = true;
			if (onError) {
				onError(error as Error);
			}
			console.warn(`Failed to load "${key}" from storage:`, error);
		}
	}

	const startValue = loadedValue ?? (loadFailed ? (fallbackValue ?? initialValue) : initialValue);

	// Create base writable store
	const store = writable<T>(startValue);

	// Flag to prevent broadcast loops
	let isExternalUpdate = false;

	// Track last applied timestamp to filter out-of-order updates
	let lastAppliedTs = 0;

	// Setup BroadcastChannel sync
	let broadcastSync: ReturnType<typeof createBroadcastSync<T>> | null = null;
	if (broadcastChannel && browser) {
		broadcastSync = createBroadcastSync<T>(broadcastChannel, (message) => {
			isExternalUpdate = true;

			switch (message.type) {
				case 'update':
					// Filter out outdated messages
					if (message.timestamp && message.timestamp <= lastAppliedTs) {
						isExternalUpdate = false;
						return;
					}
					if (message.timestamp) {
						lastAppliedTs = message.timestamp;
					}

					store.set(message.data);
					// Also save to localStorage
					if (storageAvailable) {
						try {
							if (ttl) {
								setWithTTL(key, message.data, ttl);
							} else {
								versionedStorage.set(message.data);
							}
						} catch (error) {
							if (onError) {
								onError(error as Error);
							}
						}
					}
					break;
				case 'clear':
					store.set(initialValue);
					if (storageAvailable) {
						versionedStorage.remove();
					}
					break;
				case 'reset':
					store.set(fallbackValue ?? initialValue);
					if (storageAvailable) {
						try {
							if (ttl) {
								setWithTTL(key, fallbackValue ?? initialValue, ttl);
							} else {
								versionedStorage.set(fallbackValue ?? initialValue);
							}
						} catch (error) {
							if (onError) {
								onError(error as Error);
							}
						}
					}
					break;
			}

			isExternalUpdate = false;
		});
	}

	// Save function with retry logic
	function saveToStorage(value: T): boolean {
		if (!storageAvailable) return false;

		try {
			if (ttl) {
				return setWithTTL(key, value, ttl);
			} else {
				return versionedStorage.set(value);
			}
		} catch (error) {
			if (onError) {
				onError(error as Error);
			}
			console.warn(`Failed to save "${key}" to storage, continuing in-memory only:`, error);
			return false;
		}
	}

	// Setup debounced save if needed
	let debouncedSave: ReturnType<typeof createDebouncedSave<T>> | null = null;
	if (debounceMs) {
		debouncedSave = createDebouncedSave(saveToStorage, debounceMs);
	}

	// Subscribe to store changes for auto-save
	const unsubscribe = store.subscribe((value) => {
		// Skip saving if this is an external update from BroadcastChannel
		if (isExternalUpdate) return;

		// Save to storage
		if (debouncedSave) {
			debouncedSave.debounced(value);
		} else {
			saveToStorage(value);
		}

		// Broadcast to other tabs
		if (broadcastSync && browser) {
			broadcastSync.send({
				type: 'update',
				data: value,
				timestamp: Date.now()
			});
		}
	});

	// Enhanced store methods
	const persistentStore: PersistentStore<T> = {
		subscribe: store.subscribe,
		set: store.set,
		update: store.update,

		async sync() {
			if (!storageAvailable) return;

			try {
				let value: T | null = null;
				if (ttl) {
					value = getWithTTL<T>(key);
				} else {
					value = versionedStorage.get();
				}

				if (value !== null) {
					isExternalUpdate = true;
					store.set(value);
					isExternalUpdate = false;

					// Broadcast sync
					if (broadcastSync) {
						broadcastSync.send({
							type: 'update',
							data: value,
							timestamp: Date.now()
						});
					}
				}
			} catch (error) {
				if (onError) {
					onError(error as Error);
				}
				console.error(`Failed to sync "${key}":`, error);
			}
		},

		clear() {
			store.set(initialValue);
			if (storageAvailable) {
				versionedStorage.remove();
			}
			if (broadcastSync) {
				broadcastSync.send({ type: 'clear' });
			}
		},

		reset() {
			const resetValue = fallbackValue ?? initialValue;
			store.set(resetValue);
			if (storageAvailable) {
				saveToStorage(resetValue);
			}
			if (broadcastSync) {
				broadcastSync.send({ type: 'reset' });
			}
		},

		destroy() {
			// Cancel debounced saves
			if (debouncedSave) {
				debouncedSave.cancel();
			}

			// Close BroadcastChannel
			if (broadcastSync) {
				broadcastSync.close();
			}

			// Unsubscribe from store
			unsubscribe();
		},

		isAvailable() {
			return storageAvailable;
		}
	};

	return persistentStore;
}

/**
 * Options for cached store
 */
export type CachedStoreOptions<T> = Omit<PersistentStoreOptions<T>, 'key'> & {
	/** Refetch data when window gains focus */
	refetchOnFocus?: boolean;
	/** Refetch data on interval (ms) */
	refetchInterval?: number;
	/** Retry failed fetches */
	retryOnError?: boolean;
	/** Number of retry attempts */
	maxRetries?: number;
	/** Delay between retries (ms) */
	retryDelay?: number;
};

/**
 * Create a cached store for server data with automatic refetching.
 * Combines persistent storage with async data fetching.
 *
 * @template T - Type of data stored
 * @param key - Storage key
 * @param fetchFn - Async function to fetch fresh data
 * @param options - Configuration options
 * @returns Persistent store with caching capabilities
 *
 * @example
 * ```typescript
 * const cartStore = createCachedStore('cart',
 *   () => getCart(),
 *   {
 *     ttl: 5 * 60 * 1000,
 *     broadcastChannel: 'cart-sync',
 *     refetchOnFocus: true
 *   }
 * );
 * ```
 *
 * @see {@link createPersistentStore} for basic persistent stores
 */
export function createCachedStore<T>(
	key: string,
	fetchFn: () => Promise<T>,
	options: CachedStoreOptions<T> & { initialValue: T }
): PersistentStore<T> {
	const {
		refetchOnFocus = false,
		refetchInterval,
		retryOnError = true,
		maxRetries = 3,
		retryDelay = 1000,
		initialValue,
		...persistentOptions
	} = options;

	// Create base persistent store
	const store = createPersistentStore<T>(initialValue, {
		...persistentOptions,
		key
	});

	let isFetching = false;
	let fetchIntervalId: ReturnType<typeof setInterval> | null = null;

	// Fetch with retry logic
	async function fetchWithRetry(retries = 0): Promise<T | null> {
		try {
			const data = await fetchFn();
			return data;
		} catch (error) {
			if (retryOnError && retries < maxRetries) {
				console.warn(`Fetch failed, retrying (${retries + 1}/${maxRetries})...`);
				await new Promise(resolve => setTimeout(resolve, retryDelay));
				return fetchWithRetry(retries + 1);
			}

			if (options.onError) {
				options.onError(error as Error);
			}
			console.error(`Failed to fetch "${key}" after ${retries} retries:`, error);
			return null;
		}
	}

	// Fetch and update store
	async function refresh() {
		if (isFetching) return;
		isFetching = true;

		try {
			const data = await fetchWithRetry();
			if (data !== null) {
				store.set(data);
			}
		} finally {
			isFetching = false;
		}
	}

	// Initial fetch
	if (browser) {
		refresh();
	}

	// Setup refetch on focus
	if (refetchOnFocus && browser) {
		const handleFocus = () => refresh();
		window.addEventListener('focus', handleFocus);

		// Cleanup on destroy
		const originalDestroy = store.destroy;
		store.destroy = () => {
			window.removeEventListener('focus', handleFocus);
			originalDestroy();
		};
	}

	// Setup periodic refetch
	if (refetchInterval && browser) {
		fetchIntervalId = setInterval(refresh, refetchInterval);

		// Cleanup on destroy
		const originalDestroy = store.destroy;
		store.destroy = () => {
			if (fetchIntervalId !== null) {
				clearInterval(fetchIntervalId);
			}
			originalDestroy();
		};
	}

	return store;
}

/**
 * MIGRATION EXAMPLE: Refactoring existing cart store
 *
 * Before:
 * ```typescript
 * const cartStore = writable<CartResponse>({ items: [], total_price: 0 });
 * // Manual localStorage operations
 * // Manual BroadcastChannel setup
 * // Manual error handling
 * ```
 *
 * After:
 * ```typescript
 * const cartStore = createCachedStore('cart',
 *   () => getCart(),
 *   {
 *     ttl: 5 * 60 * 1000,
 *     broadcastChannel: 'cart-sync',
 *     onError: (error) => console.error('Cart error:', error)
 *   }
 * );
 * ```
 *
 * Benefits:
 * - Automatic localStorage sync
 * - Built-in BroadcastChannel
 * - Error handling with graceful degradation
 * - TTL-based cache invalidation
 * - Less boilerplate code
 */
