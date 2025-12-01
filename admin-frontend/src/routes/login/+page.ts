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

		// Pure worker (worker_role=true, is_admin=false) -> redirect to /manual-ssn
		if (user?.worker_role === true && user?.is_admin === false) {
			throw redirect(302, '/manual-ssn');
		} else {
			throw redirect(302, '/dashboard');
		}
	}

	return {};
};
