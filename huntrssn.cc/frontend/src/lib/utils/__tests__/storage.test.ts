/**
 * Unit tests for storage utilities
 *
 * SETUP REQUIRED:
 * 1. Install vitest: pnpm add -D vitest @vitest/ui jsdom
 * 2. Add to package.json scripts:
 *    "test": "vitest",
 *    "test:ui": "vitest --ui",
 *    "test:coverage": "vitest --coverage"
 * 3. Create vitest.config.ts:
 *    import { defineConfig } from 'vitest/config';
 *    import { sveltekit } from '@sveltejs/kit/vite';
 *
 *    export default defineConfig({
 *      plugins: [sveltekit()],
 *      test: {
 *        environment: 'jsdom',
 *        globals: true,
 *        setupFiles: ['./src/lib/utils/__tests__/setup.ts']
 *      }
 *    });
 * 4. Run tests: pnpm test
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
	safeSet,
	safeGet,
	safeRemove,
	safeClear,
	safeSetJSON,
	safeGetJSON,
	setWithTTL,
	getWithTTL,
	cleanupExpired,
	createVersionedStorage,
	getStorageSize,
	isStorageAvailable,
	getStorageKeys
} from '../storage';

describe('Basic safe operations', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
	});

	it('should set and get string values', () => {
		const success = safeSet('key', 'value');
		expect(success).toBe(true);

		const value = safeGet('key');
		expect(value).toBe('value');
	});

	it('should return null for non-existent keys', () => {
		const value = safeGet('non-existent');
		expect(value).toBe(null);
	});

	it('should remove keys', () => {
		safeSet('key', 'value');
		const removed = safeRemove('key');
		expect(removed).toBe(true);

		const value = safeGet('key');
		expect(value).toBe(null);
	});

	it('should clear all storage', () => {
		safeSet('key1', 'value1');
		safeSet('key2', 'value2');

		const cleared = safeClear();
		expect(cleared).toBe(true);
		expect(localStorage.length).toBe(0);
	});

	it('should handle QuotaExceededError with retry', () => {
		let callCount = 0;
		const setItemSpy = vi.spyOn(localStorage, 'setItem').mockImplementation(() => {
			callCount++;
			if (callCount === 1) {
				const error = new DOMException('QuotaExceededError');
				error.name = 'QuotaExceededError';
				throw error;
			}
		});

		const success = safeSet('key', 'value');
		expect(success).toBe(true);
		expect(callCount).toBe(2); // Initial attempt + retry

		setItemSpy.mockRestore();
	});

	it('should return false when quota exceeded and retry fails', () => {
		const setItemSpy = vi.spyOn(localStorage, 'setItem').mockImplementation(() => {
			const error = new DOMException('QuotaExceededError');
			error.name = 'QuotaExceededError';
			throw error;
		});

		const success = safeSet('key', 'value');
		expect(success).toBe(false);

		setItemSpy.mockRestore();
	});
});

describe('JSON operations', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
	});

	it('should set and get JSON objects', () => {
		const obj = { foo: 'bar', num: 42 };
		const success = safeSetJSON('key', obj);
		expect(success).toBe(true);

		const retrieved = safeGetJSON<typeof obj>('key');
		expect(retrieved).toEqual(obj);
	});

	it('should handle complex nested objects', () => {
		const complex = {
			id: 1,
			name: 'Test',
			nested: {
				array: [1, 2, 3],
				obj: { deep: true }
			},
			items: ['a', 'b', 'c']
		};

		safeSetJSON('complex', complex);
		const retrieved = safeGetJSON<typeof complex>('complex');
		expect(retrieved).toEqual(complex);
	});

	it('should return default value on parse error', () => {
		// Set invalid JSON directly
		localStorage.setItem('key', 'invalid json{');

		const defaultValue = { foo: 'default' };
		const retrieved = safeGetJSON('key', defaultValue);
		expect(retrieved).toEqual(defaultValue);
	});

	it('should handle circular references gracefully', () => {
		const circular: any = { a: 1 };
		circular.self = circular;

		const success = safeSetJSON('circular', circular);
		expect(success).toBe(false);
	});

	it('should return null for non-existent keys', () => {
		const value = safeGetJSON<{ foo: string }>('non-existent');
		expect(value).toBe(null);
	});
});

describe('TTL operations', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('should set and get values with TTL', () => {
		const success = setWithTTL('key', 'value', 1000);
		expect(success).toBe(true);

		const value = getWithTTL<string>('key');
		expect(value).toBe('value');
	});

	it('should return null for expired values', () => {
		setWithTTL('key', 'value', 100);

		// Fast-forward time by 200ms
		vi.advanceTimersByTime(200);

		const value = getWithTTL<string>('key');
		expect(value).toBe(null);

		// Key should be removed
		expect(safeGet('key')).toBe(null);
	});

	it('should cleanup expired entries', () => {
		// Set multiple values with different TTLs
		setWithTTL('key1', 'value1', 100);
		setWithTTL('key2', 'value2', 200);
		setWithTTL('key3', 'value3', 300);

		// Fast-forward to expire first two
		vi.advanceTimersByTime(250);

		const removed = cleanupExpired();
		expect(removed).toBe(2);

		// key3 should still exist
		const value3 = getWithTTL<string>('key3');
		expect(value3).toBe('value3');
	});

	it('should not cleanup non-TTL entries', () => {
		setWithTTL('ttl-key', 'value', 100);
		safeSet('regular-key', 'value');

		vi.advanceTimersByTime(200);

		const removed = cleanupExpired();
		expect(removed).toBe(1);

		// Regular key should still exist
		expect(safeGet('regular-key')).toBe('value');
	});
});

describe('Versioned storage', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
	});

	it('should save and load with version', () => {
		const storage = createVersionedStorage<{ foo: string }>('key', 1);
		const data = { foo: 'bar' };

		const saved = storage.set(data);
		expect(saved).toBe(true);

		const loaded = storage.get();
		expect(loaded).toEqual(data);
	});

	it('should apply migration when loading old version', () => {
		type V1 = { name: string };
		type V2 = V1 & { email: string };

		// Create v1 storage and save
		const storageV1 = createVersionedStorage<V1>('user', 1);
		storageV1.set({ name: 'John' });

		// Create v2 storage with migration
		const storageV2 = createVersionedStorage<V2>('user', 2, {
			1: (data: V1) => ({ ...data, email: '' })
		});

		const loaded = storageV2.get();
		expect(loaded).toEqual({ name: 'John', email: '' });
	});

	it('should apply multiple migrations sequentially', () => {
		type V1 = { name: string };
		type V2 = V1 & { email: string };
		type V3 = V2 & { verified: boolean };

		// Save as v1
		const storageV1 = createVersionedStorage<V1>('user', 1);
		storageV1.set({ name: 'John' });

		// Load as v3 with migrations
		const storageV3 = createVersionedStorage<V3>('user', 3, {
			1: (data: V1) => ({ ...data, email: '' }),
			2: (data: V2) => ({ ...data, verified: false })
		});

		const loaded = storageV3.get();
		expect(loaded).toEqual({ name: 'John', email: '', verified: false });
	});

	it('should return null for future versions', () => {
		// Save as v2
		const storageV2 = createVersionedStorage<{ foo: string }>('key', 2);
		storageV2.set({ foo: 'bar' });

		// Try to load as v1
		const storageV1 = createVersionedStorage<{ foo: string }>('key', 1);
		const loaded = storageV1.get();
		expect(loaded).toBe(null);
	});

	it('should remove data', () => {
		const storage = createVersionedStorage<{ foo: string }>('key', 1);
		storage.set({ foo: 'bar' });

		const removed = storage.remove();
		expect(removed).toBe(true);

		const loaded = storage.get();
		expect(loaded).toBe(null);
	});

	it('should force migration', () => {
		type V1 = { name: string };
		type V2 = V1 & { email: string };

		const storageV1 = createVersionedStorage<V1>('user', 1);
		storageV1.set({ name: 'John' });

		const storageV2 = createVersionedStorage<V2>('user', 2, {
			1: (data: V1) => ({ ...data, email: '' })
		});

		const success = storageV2.migrate();
		expect(success).toBe(true);

		// Should now be saved as v2
		const raw = safeGetJSON<any>('user');
		expect(raw.version).toBe(2);
	});
});

describe('Utility functions', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
	});

	it('should calculate storage size', () => {
		safeSet('key1', 'value1');
		safeSet('key2', 'value2');

		const size = getStorageSize();
		expect(size).toBeGreaterThan(0);
	});

	it('should check storage availability', () => {
		const available = isStorageAvailable();
		expect(available).toBe(true);
	});

	it('should get all storage keys', () => {
		safeSet('key1', 'value1');
		safeSet('key2', 'value2');
		safeSet('key3', 'value3');

		const keys = getStorageKeys();
		expect(keys).toHaveLength(3);
		expect(keys).toContain('key1');
		expect(keys).toContain('key2');
		expect(keys).toContain('key3');
	});

	it('should get storage keys with prefix filter', () => {
		safeSet('user:1', 'value1');
		safeSet('user:2', 'value2');
		safeSet('cart:1', 'value3');

		const userKeys = getStorageKeys('user:');
		expect(userKeys).toHaveLength(2);
		expect(userKeys).toContain('user:1');
		expect(userKeys).toContain('user:2');
		expect(userKeys).not.toContain('cart:1');
	});
});

describe('Edge cases', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
	});

	it('should handle empty strings', () => {
		const success = safeSet('key', '');
		expect(success).toBe(true);

		const value = safeGet('key');
		expect(value).toBe('');
	});

	it('should handle special characters in keys', () => {
		const key = 'key:with:colons';
		safeSet(key, 'value');

		const value = safeGet(key);
		expect(value).toBe('value');
	});

	it('should handle null and undefined values in JSON', () => {
		const obj = { a: null, b: undefined, c: 'value' };
		safeSetJSON('key', obj);

		const retrieved = safeGetJSON<typeof obj>('key');
		// JSON.stringify removes undefined
		expect(retrieved).toEqual({ a: null, c: 'value' });
	});

	it('should handle arrays in JSON', () => {
		const arr = [1, 2, 3, { nested: true }];
		safeSetJSON('array', arr);

		const retrieved = safeGetJSON<typeof arr>('array');
		expect(retrieved).toEqual(arr);
	});

	it('should handle very large values', () => {
		const largeValue = 'x'.repeat(1000000); // 1MB string
		const success = safeSet('large', largeValue);
		expect(success).toBe(true);

		const retrieved = safeGet('large');
		expect(retrieved).toBe(largeValue);
	});
});
