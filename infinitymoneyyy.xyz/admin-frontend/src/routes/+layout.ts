import type { LayoutLoad } from './$types';
import { loadTranslations, setRoute } from '$lib/i18n';

export const load: LayoutLoad = async ({ url, data }) => {
	const locale = data?.locale || 'en';
	await setRoute(url.pathname);
	await loadTranslations(locale, url.pathname);
	return { locale };
};
