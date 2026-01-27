import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import {
	login as apiLogin,
	register as apiRegister,
	getCurrentUser,
	type UserResponse
} from '$lib/api/client';
import { setCookie, deleteCookie } from '$lib/utils/cookies';
import { clearOrdersCache, setOrdersUserId } from './orders';

// Helper functions for safe localStorage operations
function safeLocalStorageSet(key: string, value: string): boolean {
	if (!browser) return false;
	try {
		localStorage.setItem(key, value);
		return true;
	} catch (error) {
		if (error instanceof DOMException && error.name === 'QuotaExceededError') {
			console.error('localStorage quota exceeded, attempting cleanup:', error);
			// Try to clear old cache data
			try {
				localStorage.removeItem('cart-cache');
				localStorage.removeItem('orders-count-cache');
				localStorage.setItem(key, value);
				return true;
			} catch (retryError) {
				console.error('Failed to save to localStorage even after cleanup:', retryError);
				return false;
			}
		}
		console.error('Failed to write to localStorage:', error);
		return false;
	}
}

function safeLocalStorageGet(key: string): string | null {
	if (!browser) return null;
	try {
		return localStorage.getItem(key);
	} catch (error) {
		console.error('Failed to read from localStorage:', error);
		return null;
	}
}

function safeLocalStorageRemove(key: string): void {
	if (!browser) return;
	try {
		localStorage.removeItem(key);
	} catch (error) {
		console.error('Failed to remove from localStorage:', error);
	}
}

interface AuthState {
	user: UserResponse | null;
	isAuthenticated: boolean;
	isLoading: boolean;
	isRegistering: boolean;
	isLoggingIn: boolean;
	initComplete: boolean;
	isInitializing: boolean;
}

const authStore = writable<AuthState>({
	user: null,
	isAuthenticated: false,
	isLoading: true,
	isRegistering: false,
	isLoggingIn: false,
	initComplete: false,
	isInitializing: false
});

// BroadcastChannel for cross-tab synchronization
const authChannel =
	typeof BroadcastChannel !== 'undefined' && browser ? new BroadcastChannel('auth-sync') : null;

// Types for broadcast messages
type AuthMessage =
	| { type: 'login'; token: string }
	| { type: 'logout' }
	| { type: 'user-updated'; user: UserResponse };

// Listen for messages from other tabs
if (authChannel) {
	authChannel.onmessage = async (event: MessageEvent<AuthMessage>) => {
		const message = event.data;

		if (message.type === 'login') {
			// Another tab logged in - sync token and validate
			const saved = safeLocalStorageSet('access_token', message.token);
			if (saved) {
				setCookie('access_token', message.token, 7);
				await validateToken();
			}
		} else if (message.type === 'logout') {
			// Another tab logged out - clean up and redirect
			safeLocalStorageRemove('access_token');
			deleteCookie('access_token');
			clearOrdersCache();
			setUnauthenticatedState();
			if (browser && window.location.pathname !== '/login') {
				window.location.replace('/login');
			}
		} else if (message.type === 'user-updated') {
			// Another tab updated user data - sync
			authStore.update((state) => ({ ...state, user: message.user }));
		}
	};
}

// Helper function to set unauthenticated state
function setUnauthenticatedState() {
	authStore.set({
		user: null,
		isAuthenticated: false,
		isLoading: false,
		isRegistering: false,
		isLoggingIn: false,
		initComplete: true,
		isInitializing: false
	});
}

// Validate existing token via API call
async function validateToken() {
	if (!browser) {
		setUnauthenticatedState();
		return;
	}

	const token = safeLocalStorageGet('access_token');
	if (!token) {
		setUnauthenticatedState();
		return;
	}

	try {
		const user = await getCurrentUser();
		// Ensure cookie is synced with localStorage
		setCookie('access_token', token, 7);
		// Set user ID for orders store
		setOrdersUserId(user.user_id);
		authStore.set({
			user,
			isAuthenticated: true,
			isLoading: false,
			isRegistering: false,
			isLoggingIn: false,
			initComplete: true,
			isInitializing: false
		});
	} catch (error) {
		console.error('Failed to fetch user:', error);
		safeLocalStorageRemove('access_token');
		deleteCookie('access_token');
		setUnauthenticatedState();
	}
}

// Guard against concurrent validation
let inFlightValidation: Promise<void> | null = null;
let initializationStarted = false;

// Initialize auth with explicit control
export function initialize() {
	// Prevent multiple initialization calls
	if (initializationStarted) {
		console.debug('Auth initialization already started, skipping');
		return;
	}
	initializationStarted = true;

	if (!browser) {
		setUnauthenticatedState();
		return;
	}

	// Synchronously check for token presence
	let token = safeLocalStorageGet('access_token');
	if (!token) {
		// Try to restore from cookie
		const cookieToken = document.cookie
			.split('; ')
			.find((row) => row.startsWith('access_token='))
			?.split('=')[1];

		if (cookieToken) {
			console.debug('No token in localStorage, restoring from cookie');
			const saved = safeLocalStorageSet('access_token', cookieToken);
			if (saved) {
				token = cookieToken;
			}
		}

		if (!token) {
			console.debug('No auth token found during initialization');
			// Synchronously clear cookie and set final state
			deleteCookie('access_token');
			setUnauthenticatedState();
			return;
		}
	}

	console.debug('Auth token found, validating...');

	// Prevent parallel validation
	if (inFlightValidation) {
		console.warn('Validation already in flight, skipping');
		return;
	}

	// Token exists - set initializing flag and validate asynchronously
	authStore.update((state) => ({ ...state, isInitializing: true }));

	// Add timeout to prevent hanging
	const timeoutPromise = new Promise<void>((_, reject) => {
		setTimeout(() => reject(new Error('Token validation timeout')), 10000); // 10 second timeout
	});

	inFlightValidation = Promise.race([validateToken(), timeoutPromise])
		.catch((error) => {
			console.error('Token validation failed or timed out:', error);
			// Clear invalid token
			safeLocalStorageRemove('access_token');
			deleteCookie('access_token');
			setUnauthenticatedState();
		})
		.finally(() => {
			inFlightValidation = null;
			console.debug('Auth initialization complete');
		});
}

// Periodic sync cleanup function
let stopPeriodicSync: (() => void) | null = null;

// Periodic sync to recover localStorage if manually cleared
function startPeriodicSync() {
	if (!browser) return () => {};

	const syncInterval = setInterval(() => {
		const token = safeLocalStorageGet('access_token');
		const currentState = get(authStore);

		// If authenticated but token missing in localStorage, restore it
		if (currentState.isAuthenticated && !token) {
			console.warn('Token missing from localStorage, attempting recovery');
			// Token should be in memory/cookie, try to restore
			const cookieToken = document.cookie
				.split('; ')
				.find((row) => row.startsWith('access_token='))
				?.split('=')[1];

			if (cookieToken) {
				safeLocalStorageSet('access_token', cookieToken);
			}
		}
	}, 60000); // Check every 60 seconds

	// Cleanup function
	return () => clearInterval(syncInterval);
}

// Cleanup function for BroadcastChannel
export function cleanup() {
	authChannel?.close();
}

// Auth methods
export async function login(access_code: string): Promise<{ success: boolean; error?: string }> {
	// Set logging in state
	authStore.update((state) => ({ ...state, isLoggingIn: true }));

	let tokenWasSaved = false;

	try {
		const response = await apiLogin(access_code);

		// ВАЖНО: Токен должен быть сохранен синхронно ДО обновления store
		// Это гарантирует, что layout loader увидит токен при проверке localStorage
		// даже если derived stores еще не успели обновиться (устраняет race condition)
		const saved = safeLocalStorageSet('access_token', response.access_token);
		if (!saved) {
			console.warn('Failed to save token to localStorage, continuing with in-memory only');
		}
		// Also set cookie for server-side checks to prevent FOUC
		setCookie('access_token', response.access_token, 7);
		tokenWasSaved = true;

		const user = await getCurrentUser();
		// Set user ID for orders store
		setOrdersUserId(user.user_id);
		authStore.set({
			user,
			isAuthenticated: true,
			isLoading: false,
			isRegistering: false,
			isLoggingIn: false,
			initComplete: true,
			isInitializing: false
		});

		// Broadcast login to other tabs
		authChannel?.postMessage({ type: 'login', token: response.access_token });

		// Start periodic sync after successful login
		stopPeriodicSync?.();
		stopPeriodicSync = startPeriodicSync();

		// Return success without redirect - let component handle navigation
		return { success: true };
	} catch (error: any) {
		console.error('Login failed:', error);

		// If token was saved but user fetch failed, clean up
		if (tokenWasSaved) {
			safeLocalStorageRemove('access_token');
			deleteCookie('access_token');
			setUnauthenticatedState();
		} else {
			authStore.update((state) => ({ ...state, isLoggingIn: false }));
		}

		// Provide more detailed error messages
		let errorMessage = 'Login failed';
		if (error.response?.status === 401) {
			errorMessage = 'Invalid access code';
		} else if (error.response?.status === 404) {
			errorMessage = 'User not found';
		} else if (error.message) {
			errorMessage = error.message;
		}

		return { success: false, error: errorMessage };
	}
}

export async function register(couponCode?: string, invitationCode?: string): Promise<{ success: boolean; user?: UserResponse; error?: string }> {
	// Set registering state
	authStore.update((state) => ({ ...state, isRegistering: true }));

	try {
		const user = await apiRegister(couponCode, invitationCode);
		authStore.update((state) => ({ ...state, isRegistering: false }));
		return { success: true, user };
	} catch (error: any) {
		console.error('Registration failed:', error);
		authStore.update((state) => ({ ...state, isRegistering: false }));

		// Provide more detailed error messages
		let errorMessage = 'Registration failed';
		if (error.response?.status === 409) {
			errorMessage = 'User already exists';
		} else if (error.response?.status === 400) {
			// Extract specific error message from response
			const detail = error.response?.data?.detail;
			if (detail) {
				errorMessage = detail;
			} else {
				errorMessage = 'Invalid data';
			}
		} else if (error.message) {
			errorMessage = error.message;
		}

		return { success: false, error: errorMessage };
	}
}

export async function logout() {
	try {
		// Clear localStorage and cookies
		if (browser) {
			safeLocalStorageRemove('access_token');
			deleteCookie('access_token');
			clearOrdersCache();
		}

		// Broadcast logout to other tabs
		authChannel?.postMessage({ type: 'logout' });

		// Reset user ID in orders store
		setOrdersUserId(undefined);

		// Stop periodic sync
		stopPeriodicSync?.();
		stopPeriodicSync = null;

		// Reset auth state
		setUnauthenticatedState();

		// Reset initialization flag to allow re-initialization after logout
		initializationStarted = false;

		// Small delay for smooth animation before redirect
		await new Promise((resolve) => setTimeout(resolve, 150));

		// Redirect to login page using location.replace to prevent back button access
		if (browser) {
			window.location.replace('/login');
		}
	} catch (error) {
		console.error('Logout navigation failed:', error);
		// Still try to navigate even if error occurred
		if (browser) {
			window.location.replace('/login');
		}
	}
}

export async function refreshUser(): Promise<void> {
	try {
		const user = await getCurrentUser();
		authStore.update((state) => ({ ...state, user }));
	} catch (error) {
		console.error('Failed to refresh user:', error);
	}
}

export function setUser(updated: UserResponse): void {
	authStore.update((state) => ({ ...state, user: updated }));
	// Broadcast user update to other tabs
	authChannel?.postMessage({ type: 'user-updated', user: updated });
}

// Derived stores
export const user = derived(authStore, ($auth) => $auth.user);
export const isAuthenticated = derived(authStore, ($auth) => $auth.isAuthenticated);
export const isLoading = derived(authStore, ($auth) => $auth.isLoading);
export const isRegistering = derived(authStore, ($auth) => $auth.isRegistering);
export const isLoggingIn = derived(authStore, ($auth) => $auth.isLoggingIn);
export const initComplete = derived(authStore, ($auth) => $auth.initComplete);
export const isInitializing = derived(authStore, ($auth) => $auth.isInitializing);
export const userBalance = derived(authStore, ($auth) => $auth.user?.balance ?? 0);
