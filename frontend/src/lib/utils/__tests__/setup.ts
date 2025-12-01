/**
 * Vitest setup file
 *
 * Configures global test environment:
 * - Mock browser APIs (localStorage, BroadcastChannel)
 * - Setup global test utilities
 * - Configure test timeouts
 */

import { vi, beforeEach } from 'vitest';

// Mock $app/environment to simulate browser context
vi.mock('$app/environment', () => ({ browser: true }), { virtual: true });

// Mock browser flag (kept for backwards compatibility)
if (typeof global !== 'undefined') {
	(global as any).browser = true;
}

/**
 * Create localStorage mock with full API and test helpers
 */
const createLocalStorageMock = () => {
	let store: Record<string, string> = {};

	return {
		getItem: vi.fn((key: string) => store[key] || null),
		setItem: vi.fn((key: string, value: string) => {
			store[key] = value;
		}),
		removeItem: vi.fn((key: string) => {
			delete store[key];
		}),
		clear: vi.fn(() => {
			store = {};
		}),
		get length() {
			return Object.keys(store).length;
		},
		key: vi.fn((index: number) => {
			return Object.keys(store)[index] || null;
		}),
		// Test helpers
		__getStore: () => store,
		__reset: () => {
			store = {};
			vi.clearAllMocks();
		}
	};
};

// Initialize localStorage mock
if (typeof global !== 'undefined') {
	(global as any).localStorage = createLocalStorageMock();
}

/**
 * BroadcastChannel mock with message simulation
 */
class BroadcastChannelMock {
	name: string;
	onmessage: ((event: MessageEvent) => void) | null = null;

	constructor(name: string) {
		this.name = name;
		BroadcastChannelMock.instances.push(this);
	}

	postMessage(data: any) {
		// Simulate message to other instances with the same channel name
		BroadcastChannelMock.instances
			.filter((ch) => ch !== this && ch.name === this.name)
			.forEach((ch) => {
				if (ch.onmessage) {
					// Simulate async message delivery
					setTimeout(() => {
						ch.onmessage!(new MessageEvent('message', { data }));
					}, 0);
				}
			});
	}

	close() {
		const index = BroadcastChannelMock.instances.indexOf(this);
		if (index > -1) {
			BroadcastChannelMock.instances.splice(index, 1);
		}
	}

	// Static registry of all channel instances
	static instances: BroadcastChannelMock[] = [];

	// Test helper to reset all channels
	static reset() {
		this.instances.forEach((ch) => ch.close());
		this.instances = [];
	}
}

if (typeof global !== 'undefined') {
	(global as any).BroadcastChannel = BroadcastChannelMock;
}

/**
 * Mock window with event handling
 */
const createWindowMock = () => {
	const eventListeners: Record<string, Set<EventListener>> = {};

	return {
		addEventListener: vi.fn((event: string, handler: EventListener) => {
			if (!eventListeners[event]) {
				eventListeners[event] = new Set();
			}
			eventListeners[event].add(handler);
		}),
		removeEventListener: vi.fn((event: string, handler: EventListener) => {
			if (eventListeners[event]) {
				eventListeners[event].delete(handler);
			}
		}),
		dispatchEvent: vi.fn((event: Event) => {
			const listeners = eventListeners[event.type];
			if (listeners) {
				listeners.forEach((handler) => {
					handler(event);
				});
			}
			return true;
		}),
		// Test helper to trigger events
		__triggerEvent: (eventType: string) => {
			const event = new Event(eventType);
			const listeners = eventListeners[eventType];
			if (listeners) {
				listeners.forEach((handler) => handler(event));
			}
		},
		// Test helper to get listener count
		__getListenerCount: (eventType: string) => {
			return eventListeners[eventType]?.size || 0;
		},
		// Test helper to clear all listeners
		__clearListeners: () => {
			Object.keys(eventListeners).forEach((key) => {
				eventListeners[key].clear();
			});
		}
	};
};

if (typeof global !== 'undefined' && !(global as any).window) {
	(global as any).window = createWindowMock();
}

/**
 * Mock navigator.storage for quota testing
 */
const createNavigatorStorageMock = () => ({
	estimate: vi.fn().mockResolvedValue({
		quota: 10 * 1024 * 1024, // 10MB
		usage: 1 * 1024 * 1024 // 1MB
	})
});

if (typeof global !== 'undefined') {
	if (!(global as any).navigator) {
		(global as any).navigator = {};
	}
	(global as any).navigator.storage = createNavigatorStorageMock();
}

/**
 * Mock Date.now() helper for TTL testing
 */
export const mockDate = (timestamp: number) => {
	vi.spyOn(Date, 'now').mockReturnValue(timestamp);
};

export const restoreDate = () => {
	vi.restoreAllMocks();
};

/**
 * Global test configuration
 */
vi.setConfig({ testTimeout: 10000 });

/**
 * Reset all mocks before each test
 */
beforeEach(() => {
	// Reset localStorage
	if ((global as any).localStorage?.__reset) {
		(global as any).localStorage.__reset();
	}

	// Reset BroadcastChannel
	if ((global as any).BroadcastChannel?.reset) {
		(global as any).BroadcastChannel.reset();
	}

	// Clear window event listeners
	if ((global as any).window?.__clearListeners) {
		(global as any).window.__clearListeners();
	}

	// Clear all mocks
	vi.clearAllMocks();
});

/**
 * Export test helpers
 */
export const testHelpers = {
	localStorage: {
		getStore: () => (global as any).localStorage?.__getStore(),
		reset: () => (global as any).localStorage?.__reset()
	},
	broadcastChannel: {
		getInstances: () => (global as any).BroadcastChannel?.instances || [],
		reset: () => (global as any).BroadcastChannel?.reset()
	},
	window: {
		triggerEvent: (eventType: string) => (global as any).window?.__triggerEvent(eventType),
		getListenerCount: (eventType: string) =>
			(global as any).window?.__getListenerCount(eventType),
		clearListeners: () => (global as any).window?.__clearListeners()
	}
};
