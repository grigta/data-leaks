import { browser } from '$app/environment';
import { redirect } from '@sveltejs/kit';
import { get } from 'svelte/store';
import { isAuthenticated } from '$lib/stores/auth';
import type { PageLoad } from './$types';

export const load: PageLoad = async () => {
	// Redirect to dashboard if already authenticated
	if (browser && get(isAuthenticated)) {
		throw redirect(302, '/profit-dashboard');
	}

	return {};
};
