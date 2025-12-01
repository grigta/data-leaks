import type { LayoutServerLoad } from './$types';

const LOCALE_COOKIE_NAME = 'app-language';
const SUPPORTED_LOCALES = ['en', 'ru'] as const;
type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

export const load: LayoutServerLoad = ({ cookies, request }) => {
	// Приоритет 1: Cookie
	const cookieLocale = cookies.get(LOCALE_COOKIE_NAME);
	if (cookieLocale) {
		const normalizedCookie = cookieLocale.toLowerCase();
		if (SUPPORTED_LOCALES.includes(normalizedCookie as SupportedLocale)) {
			return { locale: normalizedCookie as SupportedLocale };
		}
	}

	// Приоритет 2: Accept-Language header
	const acceptLanguage = request.headers.get('accept-language');
	if (acceptLanguage) {
		// Формат: "en-US,en;q=0.9,ru;q=0.8"
		const browserLocale = acceptLanguage.split(',')[0]?.split('-')[0];
		if (browserLocale) {
			const normalizedBrowser = browserLocale.toLowerCase();
			if (SUPPORTED_LOCALES.includes(normalizedBrowser as SupportedLocale)) {
				return { locale: normalizedBrowser as SupportedLocale };
			}
		}
	}

	// Fallback
	return { locale: 'en' as const };
};
