import { dev } from '$app/environment';
import i18n from 'sveltekit-i18n';
import type { Config } from 'sveltekit-i18n';

const config: Config = {
	fallbackLocale: 'en',
	// Routes mapping для точечной загрузки неймспейсов
	routes: {
		'/': ['common', 'navigation'],
		'/login': ['common', 'navigation', 'auth'],
		'/register': ['common', 'navigation', 'auth'],
		'/dashboard': ['common', 'navigation', 'dashboard', 'search', 'cart'],
		'/cart': ['common', 'navigation', 'cart'],
		'/orders': ['common', 'navigation', 'orders', 'cart'],
		'/balance': ['common', 'navigation', 'balance', 'crypto'],
		'/profile': ['common', 'navigation', 'profile'],
		'/api': ['common', 'navigation', 'api'],
		'/support': ['common', 'navigation', 'support'],
		'/contact': ['common', 'navigation', 'contact'],
		'/manual-ssn': ['common', 'navigation', 'search'],
		'/subscription': ['common', 'navigation', 'subscription'],
		'/lookup-ssn': ['common', 'navigation', 'subscription'],
		'/phone-lookup': ['common', 'navigation', 'phone-lookup'],
		// Дефолтный маппинг для всех необработанных маршрутов
		'*': ['common', 'navigation']
	},
	loaders: [
		{
			locale: 'en',
			key: 'common',
			loader: async () => (await import('./locales/en/common.json')).default
		},
		{
			locale: 'en',
			key: 'auth',
			loader: async () => (await import('./locales/en/auth.json')).default
		},
		{
			locale: 'en',
			key: 'navigation',
			loader: async () => (await import('./locales/en/navigation.json')).default
		},
		{
			locale: 'en',
			key: 'cart',
			loader: async () => (await import('./locales/en/cart.json')).default
		},
		{
			locale: 'en',
			key: 'orders',
			loader: async () => (await import('./locales/en/orders.json')).default
		},
		{
			locale: 'en',
			key: 'balance',
			loader: async () => (await import('./locales/en/balance.json')).default
		},
		{
			locale: 'en',
			key: 'profile',
			loader: async () => (await import('./locales/en/profile.json')).default
		},
		{
			locale: 'en',
			key: 'search',
			loader: async () => (await import('./locales/en/search.json')).default
		},
		{
			locale: 'en',
			key: 'crypto',
			loader: async () => (await import('./locales/en/crypto.json')).default
		},
		{
			locale: 'en',
			key: 'errors',
			loader: async () => (await import('./locales/en/errors.json')).default
		},
		{
			locale: 'en',
			key: 'dashboard',
			loader: async () => (await import('./locales/en/dashboard.json')).default
		},
		{
			locale: 'en',
			key: 'api',
			loader: async () => (await import('./locales/en/api.json')).default
		},
		{
			locale: 'en',
			key: 'support',
			loader: async () => (await import('./locales/en/support.json')).default
		},
		{
			locale: 'en',
			key: 'contact',
			loader: async () => (await import('./locales/en/contact.json')).default
		},
		{
			locale: 'en',
			key: 'subscription',
			loader: async () => (await import('./locales/en/subscription.json')).default
		},
		{
			locale: 'en',
			key: 'phone-lookup',
			loader: async () => (await import('./locales/en/phone-lookup.json')).default
		},
		{
			locale: 'ru',
			key: 'common',
			loader: async () => (await import('./locales/ru/common.json')).default
		},
		{
			locale: 'ru',
			key: 'auth',
			loader: async () => (await import('./locales/ru/auth.json')).default
		},
		{
			locale: 'ru',
			key: 'navigation',
			loader: async () => (await import('./locales/ru/navigation.json')).default
		},
		{
			locale: 'ru',
			key: 'cart',
			loader: async () => (await import('./locales/ru/cart.json')).default
		},
		{
			locale: 'ru',
			key: 'orders',
			loader: async () => (await import('./locales/ru/orders.json')).default
		},
		{
			locale: 'ru',
			key: 'balance',
			loader: async () => (await import('./locales/ru/balance.json')).default
		},
		{
			locale: 'ru',
			key: 'profile',
			loader: async () => (await import('./locales/ru/profile.json')).default
		},
		{
			locale: 'ru',
			key: 'search',
			loader: async () => (await import('./locales/ru/search.json')).default
		},
		{
			locale: 'ru',
			key: 'crypto',
			loader: async () => (await import('./locales/ru/crypto.json')).default
		},
		{
			locale: 'ru',
			key: 'errors',
			loader: async () => (await import('./locales/ru/errors.json')).default
		},
		{
			locale: 'ru',
			key: 'dashboard',
			loader: async () => (await import('./locales/ru/dashboard.json')).default
		},
		{
			locale: 'ru',
			key: 'api',
			loader: async () => (await import('./locales/ru/api.json')).default
		},
		{
			locale: 'ru',
			key: 'support',
			loader: async () => (await import('./locales/ru/support.json')).default
		},
		{
			locale: 'ru',
			key: 'contact',
			loader: async () => (await import('./locales/ru/contact.json')).default
		},
		{
			locale: 'ru',
			key: 'subscription',
			loader: async () => (await import('./locales/ru/subscription.json')).default
		},
		{
			locale: 'ru',
			key: 'phone-lookup',
			loader: async () => (await import('./locales/ru/phone-lookup.json')).default
		}
	],
	log: {
		level: dev ? 'warn' : 'error'
	}
};

export const { t, locale, locales, loading, setLocale, setRoute, loadTranslations } = new (i18n as any)(config);
