import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';
import {
	adminLogin,
	verifyTwoFactor,
	setupTwoFactor,
	confirmTwoFactor,
	getCurrentAdminUser
} from '$lib/api/client';
import { setCookie, deleteCookie, getCookie } from '$lib/utils/cookies';

// Admin auth state interface
export interface AdminAuthState {
	username: string | null;
	isAuthenticated: boolean;
	isLoading: boolean;
	requires2FA: boolean;
	tempToken: string | null;
	has2FASetup: boolean;
	user: { username: string; email?: string; is_admin?: boolean; worker_role?: boolean } | null;
}

// Initial state
const initialState: AdminAuthState = {
	username: null,
	isAuthenticated: false,
	isLoading: true,
	requires2FA: false,
	tempToken: null,
	has2FASetup: false,
	user: null
};

// Create writable store
const { subscribe, set, update } = writable<AdminAuthState>(initialState);

// Helper to decode JWT and check expiration
function isTokenValid(token: string): boolean {
	try {
		// Check token format (should have 3 parts separated by dots)
		if (!token || typeof token !== 'string') {
			return false;
		}

		const parts = token.split('.');
		if (parts.length !== 3) {
			return false;
		}

		// Decode payload
		const payload = JSON.parse(atob(parts[1]));

		// Check expiration
		if (!payload.exp) {
			return false;
		}

		const exp = payload.exp * 1000; // Convert to milliseconds
		return exp > Date.now();
	} catch (error) {
		console.error('Token validation error:', error);
		return false;
	}
}

// Initialize auth state from localStorage
export async function initAuth(): Promise<void> {
	if (!browser) {
		update((state) => ({ ...state, isLoading: false }));
		return;
	}

	try {
		// Try localStorage first, then fallback to cookie
		let token = localStorage.getItem('admin_access_token');
		if (!token) {
			token = getCookie('admin_access_token');
			// Sync to localStorage if found in cookie
			if (token) {
				localStorage.setItem('admin_access_token', token);
			}
		}

		if (!token) {
			update((state) => ({
				...state,
				isAuthenticated: false,
				isLoading: false
			}));
			return;
		}

		// Validate token expiration and format
		if (!isTokenValid(token)) {
			console.warn('Invalid or expired admin token detected, clearing authentication state');
			localStorage.removeItem('admin_access_token');
			localStorage.removeItem('admin_temp_token');
			deleteCookie('admin_access_token');
			update((state) => ({
				...state,
				isAuthenticated: false,
				isLoading: false
			}));
			return;
		}

		// Token is valid - decode it to get username and 2FA status
		try {
			const payload = JSON.parse(atob(token.split('.')[1]));
			const username = payload.sub || null;

			// Validate that we have at least a username
			if (!username) {
				console.warn('Token missing username claim, clearing authentication');
				localStorage.removeItem('admin_access_token');
				localStorage.removeItem('admin_temp_token');
				deleteCookie('admin_access_token');
				update((state) => ({
					...state,
					isAuthenticated: false,
					isLoading: false
				}));
				return;
			}

			// Check for 2FA enabled claim (can be mfa_enabled, two_factor_enabled, or totp_enabled)
			const has2FASetup = payload.mfa_enabled === true ||
			                    payload.two_factor_enabled === true ||
			                    payload.totp_enabled === true ||
			                    false;

			update((state) => ({
				...state,
				isAuthenticated: true,
				isLoading: false,
				username,
				has2FASetup
			}));

			// Fetch current user data
			try {
				const user = await getCurrentAdminUser();
				update((state) => ({ ...state, user }));
			} catch (error: any) {
				// If 401/403, clear auth state
				if (error.response?.status === 401 || error.response?.status === 403) {
					console.warn('Failed to fetch current user, clearing auth');
					localStorage.removeItem('admin_access_token');
					localStorage.removeItem('admin_temp_token');
					deleteCookie('admin_access_token');
					update((state) => ({
						...initialState,
						isLoading: false
					}));
				}
			}
		} catch (error) {
			// Token decoding failed - clear it
			console.error('Failed to decode admin token:', error);
			localStorage.removeItem('admin_access_token');
			localStorage.removeItem('admin_temp_token');
			deleteCookie('admin_access_token');
			update((state) => ({
				...state,
				isAuthenticated: false,
				isLoading: false
			}));
		}
	} catch (error) {
		// Catch any unexpected errors during initialization
		console.error('Error initializing auth state:', error);
		update((state) => ({
			...state,
			isAuthenticated: false,
			isLoading: false
		}));
	}
}

// Login function
export async function login(
	username: string,
	password: string
): Promise<{ success: boolean; requires2FA?: boolean; user?: any; error?: string }> {
	update((state) => ({ ...state, isLoading: true }));

	try {
		const response = await adminLogin(username, password);

		// Priority 1: Check if API explicitly provides requires_2fa field
		if (response.requires_2fa !== undefined) {
			if (response.requires_2fa) {
				// Store temp token and set requires2FA flag
				if (browser) {
					localStorage.setItem('admin_temp_token', response.access_token);
				}

				update((state) => ({
					...state,
					isLoading: false,
					requires2FA: true,
					tempToken: response.access_token,
					username
				}));

				return { success: true, requires2FA: true };
			} else {
				// No 2FA required - store access token
				if (browser) {
					localStorage.setItem('admin_access_token', response.access_token);
					setCookie('admin_access_token', response.access_token, 7);
				}

				update((state) => ({
					...state,
					isAuthenticated: true,
					isLoading: false,
					username,
					has2FASetup: false
				}));

				// Fetch current user data
				let user: AdminAuthState['user'] = null;
				try {
					const userData = await getCurrentAdminUser();
					user = userData;
					update((state) => ({ ...state, user: userData }));
				} catch (error: any) {
					console.error('Failed to fetch current user after login:', error);
				}

				return { success: true, requires2FA: false, user };
			}
		}

		// Priority 2: Fall back to decoding JWT token for temp_2fa flag
		const payload = JSON.parse(atob(response.access_token.split('.')[1]));
		const isTempToken = payload.temp_2fa === true;

		if (isTempToken) {
			// Store temp token and set requires2FA flag
			if (browser) {
				localStorage.setItem('admin_temp_token', response.access_token);
			}

			update((state) => ({
				...state,
				isLoading: false,
				requires2FA: true,
				tempToken: response.access_token,
				username
			}));

			return { success: true, requires2FA: true };
		} else {
			// No 2FA required - store access token
			if (browser) {
				localStorage.setItem('admin_access_token', response.access_token);
				setCookie('admin_access_token', response.access_token, 7);
			}

			update((state) => ({
				...state,
				isAuthenticated: true,
				isLoading: false,
				username,
				has2FASetup: false
			}));

			// Fetch current user data
			let user: AdminAuthState['user'] = null;
			try {
				const userData = await getCurrentAdminUser();
				user = userData;
				update((state) => ({ ...state, user: userData }));
			} catch (error: any) {
				console.error('Failed to fetch current user after login:', error);
			}

			return { success: true, requires2FA: false, user };
		}
	} catch (error: any) {
		update((state) => ({ ...state, isLoading: false }));
		return {
			success: false,
			error: error.response?.data?.detail || 'Login failed'
		};
	}
}

// Verify TOTP code
export async function verifyTOTP(
	totp_code: string
): Promise<{ success: boolean; user?: any; error?: string }> {
	update((state) => ({ ...state, isLoading: true }));

	try {
		const response = await verifyTwoFactor(totp_code);

		// Store access token and clear temp token
		if (browser) {
			localStorage.setItem('admin_access_token', response.access_token);
			localStorage.removeItem('admin_temp_token');
			setCookie('admin_access_token', response.access_token, 7);
		}

		update((state) => ({
			...state,
			isAuthenticated: true,
			isLoading: false,
			requires2FA: false,
			tempToken: null,
			has2FASetup: true
		}));

		// Fetch current user data
		let user: AdminAuthState['user'] = null;
		try {
			const userData = await getCurrentAdminUser();
			user = userData;
			update((state) => ({ ...state, user: userData }));
		} catch (error: any) {
			console.error('Failed to fetch current user after TOTP verification:', error);
		}

		return { success: true, user };
	} catch (error: any) {
		update((state) => ({ ...state, isLoading: false }));

		// Check if it's a session expiration error
		if (error.message === 'Session expired. Please login again.') {
			// Clear state and show the error but don't force redirect
			update((state) => ({
				...state,
				requires2FA: false,
				tempToken: null
			}));
		}

		return {
			success: false,
			error: error.message || error.response?.data?.detail || 'TOTP verification failed'
		};
	}
}

// Logout function
export function logout(): void {
	if (browser) {
		localStorage.removeItem('admin_access_token');
		localStorage.removeItem('admin_temp_token');
		deleteCookie('admin_access_token');
	}

	set(initialState);

	// Redirect to login
	if (browser) {
		window.location.replace('/login');
	}
}

// Setup 2FA
export async function setup2FA(): Promise<{
	success: boolean;
	secret?: string;
	qr_uri?: string;
	backup_codes?: string[];
	error?: string;
}> {
	try {
		const response = await setupTwoFactor();
		return {
			success: true,
			secret: response.secret,
			qr_uri: response.provisioning_uri,
			backup_codes: []
		};
	} catch (error: any) {
		return {
			success: false,
			error: error.response?.data?.detail || '2FA setup failed'
		};
	}
}

// Confirm 2FA setup
export async function confirm2FA(
	totp_code: string
): Promise<{ success: boolean; error?: string }> {
	try {
		await confirmTwoFactor(totp_code);

		update((state) => ({ ...state, has2FASetup: true }));

		return { success: true };
	} catch (error: any) {
		return {
			success: false,
			error: error.response?.data?.detail || '2FA confirmation failed'
		};
	}
}

// Export store
export const authStore = {
	subscribe,
	initAuth,
	login,
	verifyTOTP,
	logout,
	setup2FA,
	confirm2FA
};

// Derived stores
export const isAuthenticated = derived(authStore, ($auth) => $auth.isAuthenticated);
export const isLoading = derived(authStore, ($auth) => $auth.isLoading);
export const requires2FA = derived(authStore, ($auth) => $auth.requires2FA);
export const username = derived(authStore, ($auth) => $auth.username);

// Initialize on module load
if (browser) {
	initAuth();
}
