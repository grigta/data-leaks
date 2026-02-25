import type { LayoutServerLoad } from './$types';

const SUPPORTED_LOCALES = ['en', 'ru'];

export const load: LayoutServerLoad = ({ cookies, request }) => {
	const cookieLocale = cookies.get('admin-language');
	if (cookieLocale && SUPPORTED_LOCALES.includes(cookieLocale)) {
		return { locale: cookieLocale };
	}

	const acceptLang = request.headers.get('accept-language');
	if (acceptLang) {
		const browserLang = acceptLang.split(',')[0]?.split('-')[0];
		if (browserLang && SUPPORTED_LOCALES.includes(browserLang)) {
			return { locale: browserLang };
		}
	}

	return { locale: 'en' };
};
