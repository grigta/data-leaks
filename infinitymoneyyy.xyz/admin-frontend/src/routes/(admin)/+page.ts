import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ url }) => {
	// Check if this is the worker domain (f72nak8127sd.top)
	const hostname = url.hostname;

	if (hostname === 'f72nak8127sd.top' || hostname === 'www.f72nak8127sd.top') {
		// Worker domain - redirect to manual SSN processing page
		throw redirect(302, '/manual-ssn');
	} else {
		// Admin domain - redirect to dashboard
		throw redirect(302, '/dashboard');
	}
};
