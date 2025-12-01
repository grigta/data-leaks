import { browser } from '$app/environment';
import { isInitializing } from '$lib/stores/auth';
import { get } from 'svelte/store';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async () => {
	if (!browser) {
		// Server-side: assume authenticated until proven otherwise
		return { needsAuth: false };
	}

	// Check current initialization state synchronously
	const currentInitializing = get(isInitializing);

	// If auth is still initializing, wait for it to complete
	if (currentInitializing) {
		console.debug('[App Layout] Waiting for auth initialization...');

		await new Promise<void>((resolve) => {
			// Timeout to prevent indefinite waiting
			const timeout = setTimeout(() => {
				console.warn('[App Layout] Auth initialization timeout - proceeding anyway');
				unsubscribe();
				resolve();
			}, 5000); // 5 second maximum wait

			const unsubscribe = isInitializing.subscribe((initializing) => {
				if (!initializing) {
					clearTimeout(timeout);
					unsubscribe();
					resolve();
				}
			});
		});
	}

	// Check for token presence
	const token = localStorage.getItem('access_token');
	const needsAuth = !token;

	if (needsAuth) {
		console.debug('[App Layout] No token found, authentication required');
	} else {
		console.debug('[App Layout] Token found, user authenticated');
	}

	// Return data instead of doing redirect
	// The actual redirect will be handled reactively in the layout component
	return {
		needsAuth,
		hasToken: !!token
	};
};
