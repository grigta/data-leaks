import { browser } from '$app/environment';
import { redirect } from '@sveltejs/kit';
import { get } from 'svelte/store';
import { isAuthenticated, isLoading } from '$lib/stores/auth';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async () => {
	if (!browser) {
		return { needsAuth: false };
	}

	// Wait for auth initialization with timeout
	if (get(isLoading)) {
		await new Promise<void>((resolve) => {
			const timeout = setTimeout(() => {
				unsubscribe();
				resolve();
			}, 5000); // 5 second timeout

			const unsubscribe = isLoading.subscribe((loading) => {
				if (!loading) {
					clearTimeout(timeout);
					unsubscribe();
					resolve();
				}
			});
		});
	}

	const token = localStorage.getItem('admin_access_token');

	// Throw redirect instead of goto
	if (!token) {
		throw redirect(302, '/login');
	}

	return { hasToken: true };
};
