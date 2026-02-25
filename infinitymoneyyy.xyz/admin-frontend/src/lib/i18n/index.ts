import { dev } from '$app/environment';
import i18n from 'sveltekit-i18n';
import type { Config } from 'sveltekit-i18n';

const config: Config = {
	fallbackLocale: 'en',
	loaders: [
		{ locale: 'en', key: 'common', loader: async () => (await import('./locales/en/common.json')).default },
		{ locale: 'en', key: 'navigation', loader: async () => (await import('./locales/en/navigation.json')).default },
		{ locale: 'en', key: 'auth', loader: async () => (await import('./locales/en/auth.json')).default },
		{ locale: 'en', key: 'dashboard', loader: async () => (await import('./locales/en/dashboard.json')).default },
		{ locale: 'en', key: 'users', loader: async () => (await import('./locales/en/users.json')).default },
		{ locale: 'en', key: 'tickets', loader: async () => (await import('./locales/en/tickets.json')).default },
		{ locale: 'en', key: 'workers', loader: async () => (await import('./locales/en/workers.json')).default },
		{ locale: 'en', key: 'errors', loader: async () => (await import('./locales/en/errors.json')).default },
		{ locale: 'en', key: 'orders', loader: async () => (await import('./locales/en/orders.json')).default },
		{ locale: 'en', key: 'report', loader: async () => (await import('./locales/en/report.json')).default },
		{ locale: 'en', key: 'settings', loader: async () => (await import('./locales/en/settings.json')).default },
		{ locale: 'en', key: 'test-polygon', loader: async () => (await import('./locales/en/test-polygon.json')).default },
		{ locale: 'ru', key: 'common', loader: async () => (await import('./locales/ru/common.json')).default },
		{ locale: 'ru', key: 'navigation', loader: async () => (await import('./locales/ru/navigation.json')).default },
		{ locale: 'ru', key: 'auth', loader: async () => (await import('./locales/ru/auth.json')).default },
		{ locale: 'ru', key: 'dashboard', loader: async () => (await import('./locales/ru/dashboard.json')).default },
		{ locale: 'ru', key: 'users', loader: async () => (await import('./locales/ru/users.json')).default },
		{ locale: 'ru', key: 'tickets', loader: async () => (await import('./locales/ru/tickets.json')).default },
		{ locale: 'ru', key: 'workers', loader: async () => (await import('./locales/ru/workers.json')).default },
		{ locale: 'ru', key: 'errors', loader: async () => (await import('./locales/ru/errors.json')).default },
		{ locale: 'ru', key: 'orders', loader: async () => (await import('./locales/ru/orders.json')).default },
		{ locale: 'ru', key: 'report', loader: async () => (await import('./locales/ru/report.json')).default },
		{ locale: 'ru', key: 'settings', loader: async () => (await import('./locales/ru/settings.json')).default },
		{ locale: 'ru', key: 'test-polygon', loader: async () => (await import('./locales/ru/test-polygon.json')).default }
	],
	log: {
		level: dev ? 'warn' : 'error'
	}
};

export const { t, locale, locales, loading, setLocale, setRoute, loadTranslations } = new (i18n as any)(config);
