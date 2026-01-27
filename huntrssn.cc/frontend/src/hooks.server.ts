import type { Handle } from '@sveltejs/kit';

// Disable SSR globally to avoid hydration issues
export const handle: Handle = async ({ event, resolve }) => {
	const response = await resolve(event, {
		ssr: false
	});

	// Remove Link header to prevent 502 errors with large preload headers
	// SvelteKit generates Link headers for preloading resources which can exceed nginx buffer limits
	// Only apply to HTML responses to avoid affecting other content types
	const contentType = response.headers.get('content-type');
	if (contentType && contentType.startsWith('text/html')) {
		const headers = new Headers(response.headers);
		headers.delete('Link');

		return new Response(response.body, {
			status: response.status,
			statusText: response.statusText,
			headers
		});
	}

	return response;
};
