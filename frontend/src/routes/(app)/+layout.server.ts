import { redirect } from '@sveltejs/kit';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = ({ cookies }) => {
	// Check for auth token in cookies
	// This provides server-side redirect to prevent FOUC on direct navigation
	const token = cookies.get('access_token');

	if (!token) {
		// Redirect to login if no token found
		throw redirect(303, '/login');
	}

	return {};
};
