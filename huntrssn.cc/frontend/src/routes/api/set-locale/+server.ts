import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request, cookies }) => {
	try {
		const { locale } = await request.json();

		// Валидация локали
		if (locale !== 'en' && locale !== 'ru') {
			return json({ error: 'Invalid locale' }, { status: 400 });
		}

		// Установить cookie
		cookies.set('app-language', locale, {
			path: '/',
			maxAge: 60 * 60 * 24 * 365, // 1 год
			sameSite: 'lax',
			httpOnly: true // Защищено от XSS, клиентский доступ через localStorage
		});

		return json({ success: true });
	} catch (error) {
		console.error('Failed to set locale:', error);
		return json({ error: 'Failed to set locale' }, { status: 500 });
	}
};
