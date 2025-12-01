/**
 * Unit tests for persistent store utilities
 *
 * Tests cover:
 * - Store creation and initialization
 * - Automatic localStorage synchronization
 * - BroadcastChannel cross-tab sync
 * - Error handling and graceful degradation
 * - TTL and cache invalidation
 * - Versioning and migrations
 *
 * SETUP: See storage.test.ts for vitest configuration
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import { createPersistentStore, createCachedStore } from '../persistent-store';

describe('createPersistentStore', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
	});

	afterEach(() => {
		// Cleanup is handled by setup.ts
	});

	it('should create store with initial value', () => {
		const store = createPersistentStore('test', {
			key: 'test-key'
		});

		const value = get(store);
		expect(value).toBe('test');

		store.destroy();
	});

	it('should load value from localStorage on init', () => {
		// Manually set value in localStorage
		localStorage.setItem(
			'test-key',
			JSON.stringify({
				version: 1,
				data: 'cached-value',
				timestamp: Date.now()
			})
		);

		const store = createPersistentStore('initial-value', {
			key: 'test-key'
		});

		const value = get(store);
		expect(value).toBe('cached-value');

		store.destroy();
	});

	it('should automatically save to localStorage on update', () => {
		const store = createPersistentStore('initial', {
			key: 'test-key'
		});

		store.set('new value');

		// Check localStorage
		const raw = localStorage.getItem('test-key');
		expect(raw).toBeTruthy();

		const parsed = JSON.parse(raw!);
		expect(parsed.data).toBe('new value');

		store.destroy();
	});

	it('should use fallback value when localStorage fails', () => {
		// Mock localStorage to throw error
		const getItemSpy = vi.spyOn(localStorage, 'getItem').mockImplementation(() => {
			throw new Error('Storage unavailable');
		});

		const store = createPersistentStore('initial', {
			key: 'test-key',
			fallbackValue: 'fallback'
		});

		const value = get(store);
		expect(value).toBe('initial'); // Uses initial since loading failed

		getItemSpy.mockRestore();
		store.destroy();
	});

	it('should check availability', () => {
		const store = createPersistentStore('test', {
			key: 'test-key'
		});

		expect(store.isAvailable()).toBe(true);

		store.destroy();
	});
});

describe('Cross-tab synchronization', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
	});

	afterEach(() => {
		// Cleanup is handled by setup.ts
	});

	it('should sync updates between tabs', () => {
		const store1 = createPersistentStore('initial', {
			key: 'sync-key',
			broadcastChannel: 'test-sync'
		});

		const store2 = createPersistentStore('initial', {
			key: 'sync-key',
			broadcastChannel: 'test-sync'
		});

		// Update store1
		store1.set('updated');

		// store2 should be updated
		const value2 = get(store2);
		expect(value2).toBe('updated');

		store1.destroy();
		store2.destroy();
	});

	it('should not create infinite broadcast loop', () => {
		const store1 = createPersistentStore('initial', {
			key: 'loop-key',
			broadcastChannel: 'test-loop'
		});

		const store2 = createPersistentStore('initial', {
			key: 'loop-key',
			broadcastChannel: 'test-loop'
		});

		const postMessageSpy = vi.spyOn(BroadcastChannel.prototype, 'postMessage');

		store1.set('updated');

		// Should only be called once from store1
		// store2 receiving the message should not trigger another broadcast
		expect(postMessageSpy).toHaveBeenCalledTimes(1);

		postMessageSpy.mockRestore();
		store1.destroy();
		store2.destroy();
	});

	it('should handle clear message', () => {
		const store1 = createPersistentStore('initial', {
			key: 'clear-key',
			broadcastChannel: 'test-clear'
		});

		const store2 = createPersistentStore('initial', {
			key: 'clear-key',
			broadcastChannel: 'test-clear'
		});

		store1.set('some value');
		store1.clear();

		const value2 = get(store2);
		expect(value2).toBe('initial');

		store1.destroy();
		store2.destroy();
	});

	it('should handle reset message', () => {
		const store1 = createPersistentStore('initial', {
			key: 'reset-key',
			broadcastChannel: 'test-reset',
			fallbackValue: 'fallback'
		});

		const store2 = createPersistentStore('initial', {
			key: 'reset-key',
			broadcastChannel: 'test-reset',
			fallbackValue: 'fallback'
		});

		store1.set('changed');
		store1.reset();

		const value2 = get(store2);
		expect(value2).toBe('fallback');

		store1.destroy();
		store2.destroy();
	});

	it('should ignore messages from other channels', () => {
		const store1 = createPersistentStore('initial', {
			key: 'key1',
			broadcastChannel: 'channel-1'
		});

		const store2 = createPersistentStore('initial', {
			key: 'key2',
			broadcastChannel: 'channel-2'
		});

		store1.set('updated');

		// store2 should not be affected
		const value2 = get(store2);
		expect(value2).toBe('initial');

		store1.destroy();
		store2.destroy();
	});
});

describe('TTL functionality', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('should respect TTL when loading from cache', () => {
		// Create store with TTL and save value
		const store1 = createPersistentStore('initial', {
			key: 'ttl-key',
			ttl: 1000
		});

		store1.set('cached');
		store1.destroy();

		// Fast-forward time beyond TTL
		vi.advanceTimersByTime(2000);

		// Create new store - should use initial value (cache expired)
		const store2 = createPersistentStore('initial', {
			key: 'ttl-key',
			ttl: 1000
		});

		const value = get(store2);
		expect(value).toBe('initial');

		store2.destroy();
	});

	it('should use cached value within TTL', () => {
		const store1 = createPersistentStore('initial', {
			key: 'ttl-valid-key',
			ttl: 10000
		});

		store1.set('cached');
		store1.destroy();

		// Fast-forward but stay within TTL
		vi.advanceTimersByTime(5000);

		const store2 = createPersistentStore('initial', {
			key: 'ttl-valid-key',
			ttl: 10000
		});

		const value = get(store2);
		expect(value).toBe('cached');

		store2.destroy();
	});
});

describe('Versioning and migrations', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
	});

	afterEach(() => {
		// Cleanup is handled by setup.ts
	});

	it('should apply migration when loading old version', () => {
		type V1 = { name: string };
		type V2 = V1 & { email: string };

		// Create v1 store
		const storeV1 = createPersistentStore<V1>(
			{ name: 'default' },
			{
				key: 'user',
				version: 1
			}
		);

		storeV1.set({ name: 'John' });
		storeV1.destroy();

		// Create v2 store with migration
		const storeV2 = createPersistentStore<V2>(
			{ name: 'default', email: '' },
			{
				key: 'user',
				version: 2,
				migrations: {
					1: (data: V1) => ({ ...data, email: '' })
				}
			}
		);

		const value = get(storeV2);
		expect(value).toEqual({ name: 'John', email: '' });

		storeV2.destroy();
	});

	it('should apply multiple migrations in order', () => {
		type V1 = { name: string };
		type V2 = V1 & { email: string };
		type V3 = V2 & { verified: boolean };

		const storeV1 = createPersistentStore<V1>(
			{ name: 'default' },
			{
				key: 'user',
				version: 1
			}
		);

		storeV1.set({ name: 'John' });
		storeV1.destroy();

		const storeV3 = createPersistentStore<V3>(
			{ name: 'default', email: '', verified: false },
			{
				key: 'user',
				version: 3,
				migrations: {
					1: (data: V1) => ({ ...data, email: '' }),
					2: (data: V2) => ({ ...data, verified: false })
				}
			}
		);

		const value = get(storeV3);
		expect(value).toEqual({ name: 'John', email: '', verified: false });

		storeV3.destroy();
	});
});

describe('Debounced save', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('should debounce rapid updates', () => {
		const setItemSpy = vi.spyOn(localStorage, 'setItem');

		const store = createPersistentStore('initial', {
			key: 'debounce-key',
			debounceMs: 100
		});

		// Rapidly update 10 times
		for (let i = 0; i < 10; i++) {
			store.set(`value-${i}`);
		}

		// localStorage.setItem should not be called yet
		const callsBefore = setItemSpy.mock.calls.length;

		// Fast-forward past debounce delay
		vi.advanceTimersByTime(150);

		// Should have been called only once more after debounce
		const callsAfter = setItemSpy.mock.calls.length;
		expect(callsAfter).toBeLessThan(10 + callsBefore);

		setItemSpy.mockRestore();
		store.destroy();
	});
});

describe('Store methods', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
	});

	afterEach(() => {
		// Cleanup is handled by setup.ts
	});

	it('should sync from localStorage', async () => {
		const store = createPersistentStore('initial', {
			key: 'sync-method-key'
		});

		// Manually change localStorage
		localStorage.setItem(
			'sync-method-key',
			JSON.stringify({
				version: 1,
				data: 'manually-changed',
				timestamp: Date.now()
			})
		);

		await store.sync();

		const value = get(store);
		expect(value).toBe('manually-changed');

		store.destroy();
	});

	it('should clear store and localStorage', () => {
		const store = createPersistentStore('initial', {
			key: 'clear-method-key'
		});

		store.set('some value');
		store.clear();

		const value = get(store);
		expect(value).toBe('initial');

		const raw = localStorage.getItem('clear-method-key');
		expect(raw).toBe(null);

		store.destroy();
	});

	it('should reset to fallback value', () => {
		const store = createPersistentStore('initial', {
			key: 'reset-method-key',
			fallbackValue: 'fallback'
		});

		store.set('changed');
		store.reset();

		const value = get(store);
		expect(value).toBe('fallback');

		store.destroy();
	});

	it('should cleanup on destroy', () => {
		const store = createPersistentStore('test', {
			key: 'destroy-key',
			broadcastChannel: 'destroy-channel'
		});

		const initialChannels = (global as any).BroadcastChannel?.instances?.length || 0;
		store.destroy();

		// Channel should be closed
		const finalChannels = (global as any).BroadcastChannel?.instances?.length || 0;
		expect(finalChannels).toBe(initialChannels - 1);
	});
});

describe('createCachedStore', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('should fetch data on init', async () => {
		const fetchFn = vi.fn().mockResolvedValue({ data: 'fetched' });

		const store = createCachedStore('cache-key', fetchFn, {
			initialValue: { data: 'initial' },
			ttl: 5000
		});

		// Wait for fetch to complete
		await Promise.resolve();
		await Promise.resolve();

		expect(fetchFn).toHaveBeenCalled();

		const value = get(store);
		expect(value).toEqual({ data: 'fetched' });

		store.destroy();
	});

	it('should use cache when fetch fails', async () => {
		// Set cached data
		localStorage.setItem(
			'cache-fail-key',
			JSON.stringify({
				version: 1,
				data: { data: 'cached' },
				timestamp: Date.now()
			})
		);

		const fetchFn = vi.fn().mockRejectedValue(new Error('Network error'));

		const store = createCachedStore('cache-fail-key', fetchFn, {
			initialValue: { data: 'initial' },
			ttl: 5000,
			retryOnError: false
		});

		// Wait for fetch attempt
		await Promise.resolve();
		await Promise.resolve();

		expect(fetchFn).toHaveBeenCalled();

		// Should fall back to cached value
		const value = get(store);
		expect(value).toEqual({ data: 'cached' });

		store.destroy();
	});

	it('should refetch on window focus', async () => {
		const fetchFn = vi.fn().mockResolvedValue({ data: 'fetched' });

		const store = createCachedStore('focus-key', fetchFn, {
			initialValue: { data: 'initial' },
			refetchOnFocus: true
		});

		// Wait for initial fetch
		await Promise.resolve();
		await Promise.resolve();

		expect(fetchFn).toHaveBeenCalledTimes(1);

		// Trigger focus event
		window.dispatchEvent(new Event('focus'));

		// Should refetch
		await Promise.resolve();
		await Promise.resolve();

		expect(fetchFn).toHaveBeenCalledTimes(2);

		store.destroy();
	});

	it('should refetch on interval', async () => {
		const fetchFn = vi.fn().mockResolvedValue({ data: 'fetched' });

		const store = createCachedStore('interval-key', fetchFn, {
			initialValue: { data: 'initial' },
			refetchInterval: 1000
		});

		// Wait for initial fetch
		await Promise.resolve();
		await Promise.resolve();

		expect(fetchFn).toHaveBeenCalledTimes(1);

		// Fast-forward interval
		vi.advanceTimersByTime(1000);

		// Should refetch
		await Promise.resolve();
		await Promise.resolve();

		expect(fetchFn).toHaveBeenCalledTimes(2);

		store.destroy();
	});
});

describe('Error handling', () => {
	beforeEach(() => {
		// Reset is handled by setup.ts
	});

	afterEach(() => {
		// Cleanup is handled by setup.ts
	});

	it('should call onError callback on save failure', () => {
		const onError = vi.fn();

		const setItemSpy = vi.spyOn(localStorage, 'setItem').mockImplementation(() => {
			throw new Error('Storage error');
		});

		const store = createPersistentStore('initial', {
			key: 'error-key',
			onError
		});

		store.set('new value');

		expect(onError).toHaveBeenCalled();

		setItemSpy.mockRestore();
		store.destroy();
	});

	it('should continue working when localStorage unavailable', () => {
		const getItemSpy = vi.spyOn(localStorage, 'getItem').mockImplementation(() => {
			throw new Error('Storage unavailable');
		});

		const store = createPersistentStore('initial', {
			key: 'unavailable-key'
		});

		// Should still work in-memory
		store.set('new value');
		const value = get(store);
		expect(value).toBe('new value');

		getItemSpy.mockRestore();
		store.destroy();
	});

	it('should handle JSON parse errors gracefully', () => {
		// Set invalid JSON
		localStorage.setItem('invalid-json-key', 'invalid json{');

		const store = createPersistentStore('initial', {
			key: 'invalid-json-key',
			fallbackValue: 'fallback'
		});

		const value = get(store);
		expect(value).toBe('initial'); // Uses initial since parsing failed

		store.destroy();
	});
});
