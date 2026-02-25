import { browser } from '$app/environment';
import { redirect } from '@sveltejs/kit';
import { get } from 'svelte/store';
import { authStore, isAuthenticated } from '$lib/stores/auth';
import type { PageLoad } from './$types';

export const load: PageLoad = async () => {
	// Redirect to appropriate page if already authenticated
	if (browser && get(isAuthenticated)) {
		const state = get(authStore);
		const user = state.user;

		throw redirect(302, '/profit-dashboard');
	}

	return {};
};
