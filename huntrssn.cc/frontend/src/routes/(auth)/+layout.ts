import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import type { LayoutLoad } from './$types';

// Disable SSR for all auth pages to avoid hydration issues
export const ssr = false;

export const load: LayoutLoad = async ({ parent }) => {
	// Используем локаль из родительского layout
	const parentData = await parent();

	// Auth guard: redirect authenticated users away from auth pages
	// This prevents race conditions when users are already logged in
	if (browser) {
		const token = localStorage.getItem('access_token');
		if (token) {
			// User is authenticated, redirect to dashboard
			console.debug('[Auth Guard] User has token, redirecting from auth page to dashboard');
			goto('/dashboard');
			return parentData;
		}
	}

	return parentData;
};
