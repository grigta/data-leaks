import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

const SUPPORTED_LOCALES = ['en', 'ru'];

export const POST: RequestHandler = async ({ request, cookies }) => {
	const body = await request.json();
	const locale = body?.locale;

	if (locale && SUPPORTED_LOCALES.includes(locale)) {
		cookies.set('admin-language', locale, {
			path: '/',
			maxAge: 60 * 60 * 24 * 365,
			httpOnly: false,
			secure: false,
			sameSite: 'lax'
		});
		return json({ success: true });
	}

	return json({ success: false }, { status: 400 });
};
