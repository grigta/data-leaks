/**
 * Storage utilities for safe localStorage operations with error handling,
 * versioning, and migrations. Provides graceful degradation when localStorage
 * is unavailable or quota is exceeded.
 *
 * @module storage
 * @example
 * import { safeSet, safeGet, createVersionedStorage } from '$lib/utils/storage';
 *
 * // Simple usage
 * safeSet('key', 'value');
 * const value = safeGet('key');
 *
 * // With versioning and migrations
 * const storage = createVersionedStorage('my-data', 1, {
 *   0: (data) => ({ ...data, newField: 'default' })
 * });
 * storage.set({ foo: 'bar' });
 * const data = storage.get();
 */

import { browser } from '$app/environment';

/**
 * Result type for storage operations
 */
export type StorageResult<T> = {
	success: boolean;
	data?: T;
	error?: Error;
};

/**
 * Options for storage operations
 */
export type StorageOptions = {
	ttl?: number;
	compress?: boolean;
	encrypt?: boolean;
};

/**
 * Function type for data migrations between versions
 */
export type MigrationFunction<T> = (data: any) => T;

/**
 * Wrapper for versioned data with timestamp
 */
export type VersionedData<T> = {
	version: number;
	data: T;
	timestamp: number;
};

/**
 * Wrapper for data with TTL
 */
type TTLData<T> = {
	__ttl: true;
	data: T;
	timestamp: number;
	ttl: number;
};

/**
 * Safely set a value in localStorage with automatic error handling and retry logic.
 * Handles QuotaExceededError by attempting to cleanup expired entries and retrying once.
 *
 * @param key - Storage key
 * @param value - String value to store
 * @param options - Optional storage options (ttl, compression)
 * @returns true if successfully saved, false otherwise
 *
 * @example
 * ```typescript
 * const success = safeSet('user-token', 'abc123');
 * if (!success) {
 *   console.warn('Failed to save token, continuing with in-memory only');
 * }
 * ```
 *
 * @see {@link safeGet} for retrieving values
 * @see {@link safeSetJSON} for storing objects
 */
export function safeSet(key: string, value: string, options?: StorageOptions): boolean {
	if (!browser) return false;

	try {
		localStorage.setItem(key, value);
		return true;
	} catch (error) {
		if (error instanceof DOMException) {
			// Handle QuotaExceededError
			if (error.name === 'QuotaExceededError') {
				console.warn(`localStorage quota exceeded for key "${key}" (size: ${value.length} chars)`);

				// Try to cleanup expired entries
				const cleaned = cleanupExpired();
				console.log(`Cleaned up ${cleaned} expired entries`);

				// Retry once after cleanup
				try {
					localStorage.setItem(key, value);
					return true;
				} catch (retryError) {
					console.error(`Failed to save "${key}" even after cleanup:`, retryError);
					return false;
				}
			}

			// Handle SecurityError, InvalidAccessError, etc.
			console.error(`localStorage error for key "${key}":`, error.name, error.message);
		}
		return false;
	}
}

/**
 * Safely get a value from localStorage with error handling.
 *
 * @param key - Storage key
 * @returns The stored value or null if not found or error occurred
 *
 * @example
 * ```typescript
 * const token = safeGet('user-token');
 * if (token) {
 *   // Use token
 * }
 * ```
 *
 * @see {@link safeSet} for storing values
 * @see {@link safeGetJSON} for retrieving objects
 */
export function safeGet(key: string): string | null {
	if (!browser) return null;

	try {
		return localStorage.getItem(key);
	} catch (error) {
		console.error(`Failed to get "${key}" from localStorage:`, error);
		return null;
	}
}

/**
 * Safely remove a value from localStorage.
 *
 * @param key - Storage key to remove
 * @returns true if successfully removed, false otherwise
 *
 * @example
 * ```typescript
 * safeRemove('user-token');
 * ```
 *
 * @see {@link safeClear} for clearing all storage
 */
export function safeRemove(key: string): boolean {
	if (!browser) return false;

	try {
		localStorage.removeItem(key);
		return true;
	} catch (error) {
		console.error(`Failed to remove "${key}" from localStorage:`, error);
		return false;
	}
}

/**
 * Safely clear all localStorage data.
 *
 * @returns true if successfully cleared, false otherwise
 *
 * @example
 * ```typescript
 * if (safeClear()) {
 *   console.log('Storage cleared');
 * }
 * ```
 */
export function safeClear(): boolean {
	if (!browser) return false;

	try {
		localStorage.clear();
		return true;
	} catch (error) {
		console.error('Failed to clear localStorage:', error);
		return false;
	}
}

/**
 * Safely set a JSON value in localStorage with automatic serialization.
 * Handles circular references and serialization errors gracefully.
 *
 * @template T - Type of data to store
 * @param key - Storage key
 * @param value - Value to serialize and store
 * @param options - Optional storage options
 * @returns true if successfully saved, false otherwise
 *
 * @example
 * ```typescript
 * const user = { id: 1, name: 'John', email: 'john@example.com' };
 * const success = safeSetJSON('user', user);
 * ```
 *
 * @see {@link safeGetJSON} for retrieving objects
 */
export function safeSetJSON<T>(key: string, value: T, options?: StorageOptions): boolean {
	try {
		const serialized = JSON.stringify(value);
		return safeSet(key, serialized, options);
	} catch (error) {
		if (error instanceof TypeError && error.message.includes('circular')) {
			console.error(`Cannot serialize "${key}": circular reference detected`);
		} else {
			console.error(`Failed to serialize "${key}":`, error);
		}
		return false;
	}
}

/**
 * Safely get and parse a JSON value from localStorage.
 *
 * @template T - Expected type of the stored data
 * @param key - Storage key
 * @param defaultValue - Value to return if key doesn't exist or parsing fails
 * @returns The parsed value, defaultValue, or null
 *
 * @example
 * ```typescript
 * type User = { id: number; name: string };
 * const user = safeGetJSON<User>('user');
 * const userWithDefault = safeGetJSON<User>('user', { id: 0, name: 'Guest' });
 * ```
 *
 * @see {@link safeSetJSON} for storing objects
 */
export function safeGetJSON<T>(key: string, defaultValue?: T): T | null {
	const raw = safeGet(key);
	if (raw === null) {
		return defaultValue ?? null;
	}

	try {
		return JSON.parse(raw) as T;
	} catch (error) {
		console.error(`Failed to parse JSON for "${key}":`, error);
		return defaultValue ?? null;
	}
}

/**
 * Set a value with Time To Live (TTL).
 * The value will be automatically considered expired after the specified time.
 *
 * @template T - Type of data to store
 * @param key - Storage key
 * @param value - Value to store
 * @param ttlMs - Time to live in milliseconds
 * @returns true if successfully saved, false otherwise
 *
 * @example
 * ```typescript
 * // Cache for 5 minutes
 * setWithTTL('api-cache', data, 5 * 60 * 1000);
 * ```
 *
 * @see {@link getWithTTL} for retrieving values with TTL
 * @see {@link cleanupExpired} for removing expired entries
 */
export function setWithTTL<T>(key: string, value: T, ttlMs: number): boolean {
	const wrapper: TTLData<T> = {
		__ttl: true,
		data: value,
		timestamp: Date.now(),
		ttl: ttlMs
	};
	return safeSetJSON(key, wrapper);
}

/**
 * Get a value with TTL check. Returns null if the value has expired.
 * Automatically removes expired entries.
 *
 * @template T - Expected type of the stored data
 * @param key - Storage key
 * @returns The stored value if valid, null if expired or not found
 *
 * @example
 * ```typescript
 * const cachedData = getWithTTL<ApiResponse>('api-cache');
 * if (cachedData) {
 *   // Use cached data
 * } else {
 *   // Fetch fresh data
 * }
 * ```
 *
 * @see {@link setWithTTL} for storing values with TTL
 */
export function getWithTTL<T>(key: string): T | null {
	const wrapper = safeGetJSON<TTLData<T>>(key);
	if (!wrapper || wrapper.__ttl !== true) return null;

	const now = Date.now();
	const expiresAt = wrapper.timestamp + wrapper.ttl;

	if (now > expiresAt) {
		// Expired - remove it
		safeRemove(key);
		return null;
	}

	return wrapper.data;
}

/**
 * Cleanup all expired TTL entries from localStorage.
 * Useful for freeing up space when QuotaExceededError occurs.
 *
 * @returns Number of expired entries removed
 *
 * @example
 * ```typescript
 * const removed = cleanupExpired();
 * console.log(`Cleaned up ${removed} expired entries`);
 * ```
 *
 * @see {@link setWithTTL} for storing values with TTL
 */
export function cleanupExpired(): number {
	if (!browser) return 0;

	let removed = 0;
	const now = Date.now();

	try {
		const keys = Object.keys(localStorage);

		for (const key of keys) {
			try {
				const raw = localStorage.getItem(key);
				if (!raw) continue;

				const parsed = JSON.parse(raw);

				// Check if it's a TTL wrapper with the __ttl marker
				if (
					parsed &&
					typeof parsed === 'object' &&
					parsed.__ttl === true &&
					'timestamp' in parsed &&
					'ttl' in parsed &&
					'data' in parsed
				) {
					const expiresAt = parsed.timestamp + parsed.ttl;
					if (now > expiresAt) {
						localStorage.removeItem(key);
						removed++;
					}
				}
			} catch {
				// Ignore parse errors - not a TTL entry
				continue;
			}
		}
	} catch (error) {
		console.error('Error during cleanup:', error);
	}

	return removed;
}

/**
 * Create a versioned storage handler with automatic migrations.
 *
 * @template T - Type of data stored
 * @param key - Storage key
 * @param currentVersion - Current version number
 * @param migrations - Map of version -> migration function
 * @returns Storage handler with get/set/remove/migrate methods
 *
 * @example
 * ```typescript
 * type UserV1 = { id: number; name: string };
 * type UserV2 = UserV1 & { email: string };
 *
 * const userStorage = createVersionedStorage<UserV2>('user', 2, {
 *   1: (data: UserV1) => ({ ...data, email: '' })
 * });
 *
 * userStorage.set({ id: 1, name: 'John', email: 'john@example.com' });
 * const user = userStorage.get(); // Automatically migrates if needed
 * ```
 */
export function createVersionedStorage<T>(
	key: string,
	currentVersion: number,
	migrations: Record<number, MigrationFunction<T>> = {}
) {
	/**
	 * Get data with automatic migration
	 */
	function get(): T | null {
		const raw = safeGetJSON<VersionedData<T>>(key);
		if (!raw) return null;

		// Check version
		if (raw.version === currentVersion) {
			return raw.data;
		}

		if (raw.version > currentVersion) {
			console.warn(
				`Data version (${raw.version}) is newer than current version (${currentVersion}). ` +
				`This may indicate data from a future version of the app.`
			);
			return null;
		}

		// Need to migrate
		console.log(`Migrating "${key}" from version ${raw.version} to ${currentVersion}`);

		let data = raw.data;
		for (let v = raw.version; v < currentVersion; v++) {
			const migrationFn = migrations[v];
			if (!migrationFn) {
				console.error(`Missing migration function for version ${v}`);
				return null;
			}
			data = migrationFn(data);
		}

		// Save migrated data
		const success = set(data);
		if (!success) {
			console.warn('Failed to save migrated data');
		}

		return data;
	}

	/**
	 * Set data with current version
	 */
	function set(data: T): boolean {
		const versioned: VersionedData<T> = {
			version: currentVersion,
			data,
			timestamp: Date.now()
		};
		return safeSetJSON(key, versioned);
	}

	/**
	 * Remove data
	 */
	function remove(): boolean {
		return safeRemove(key);
	}

	/**
	 * Force migration of stored data
	 */
	function migrate(): boolean {
		const data = get();
		if (data === null) return false;
		return set(data);
	}

	return { get, set, remove, migrate };
}

/**
 * Get the total size of all data in localStorage.
 *
 * @returns Size in bytes
 *
 * @example
 * ```typescript
 * const size = getStorageSize();
 * console.log(`localStorage is using ${(size / 1024).toFixed(2)} KB`);
 * ```
 *
 * @see {@link getAvailableSpace} for checking available space
 */
export function getStorageSize(): number {
	if (!browser) return 0;

	let total = 0;
	try {
		for (let i = 0; i < localStorage.length; i++) {
			const key = localStorage.key(i);
			if (key !== null) {
				const value = localStorage.getItem(key) || '';
				// Count key + value + overhead (approx 2 bytes per char in UTF-16)
				total += (key.length + value.length) * 2;
			}
		}
	} catch (error) {
		console.error('Error calculating storage size:', error);
	}
	return total;
}

/**
 * Get available storage space if possible.
 * Uses navigator.storage.estimate() if available.
 *
 * @returns Available space in bytes, or null if cannot be determined
 *
 * @example
 * ```typescript
 * const available = await getAvailableSpace();
 * if (available !== null) {
 *   console.log(`${(available / 1024 / 1024).toFixed(2)} MB available`);
 * }
 * ```
 */
export async function getAvailableSpace(): Promise<number | null> {
	if (!browser || !navigator.storage || !navigator.storage.estimate) {
		return null;
	}

	try {
		const estimate = await navigator.storage.estimate();
		const quota = estimate.quota || 0;
		const usage = estimate.usage || 0;
		return quota - usage;
	} catch (error) {
		console.error('Error estimating storage:', error);
		return null;
	}
}

/**
 * Check if localStorage is available and working.
 * Performs a test write/read/delete operation.
 *
 * @returns true if localStorage is available and working
 *
 * @example
 * ```typescript
 * if (!isStorageAvailable()) {
 *   console.warn('localStorage is not available, using in-memory storage');
 * }
 * ```
 */
export function isStorageAvailable(): boolean {
	if (!browser) return false;

	const testKey = '__storage_test__';
	try {
		localStorage.setItem(testKey, 'test');
		const value = localStorage.getItem(testKey);
		localStorage.removeItem(testKey);
		return value === 'test';
	} catch {
		return false;
	}
}

/**
 * Get all localStorage keys, optionally filtered by prefix.
 *
 * @param prefix - Optional prefix to filter keys
 * @returns Array of matching keys
 *
 * @example
 * ```typescript
 * // Get all keys
 * const allKeys = getStorageKeys();
 *
 * // Get keys with prefix
 * const userKeys = getStorageKeys('user:');
 * ```
 */
export function getStorageKeys(prefix?: string): string[] {
	if (!browser) return [];

	try {
		const keys = Object.keys(localStorage);
		if (prefix) {
			return keys.filter(key => key.startsWith(prefix));
		}
		return keys;
	} catch (error) {
		console.error('Error getting storage keys:', error);
		return [];
	}
}
