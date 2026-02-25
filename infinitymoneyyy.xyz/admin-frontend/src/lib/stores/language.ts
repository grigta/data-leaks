import { browser } from '$app/environment';
import { writable, get } from 'svelte/store';
import { loadTranslations } from '$lib/i18n';
import { invalidateAll } from '$app/navigation';

export type SupportedLocale = 'en' | 'ru';

const STORAGE_KEY = 'admin-language';
const DEFAULT_LOCALE: SupportedLocale = 'en';

let isInitializing = false;

function safeLocalStorageSet(key: string, value: string): boolean {
	if (!browser) return false;
	try {
		localStorage.setItem(key, value);
		return true;
	} catch {
		return false;
	}
}

function safeLocalStorageGet(key: string): string | null {
	if (!browser) return null;
	try {
		return localStorage.getItem(key);
	} catch {
		return null;
	}
}

function getInitialLocale(): SupportedLocale {
	if (!browser) return DEFAULT_LOCALE;

	const stored = safeLocalStorageGet(STORAGE_KEY);
	if (stored === 'en' || stored === 'ru') return stored;

	try {
		const browserLang = navigator.language.split('-')[0];
		return browserLang === 'ru' ? 'ru' : 'en';
	} catch {
		return DEFAULT_LOCALE;
	}
}

const languageChannel =
	typeof BroadcastChannel !== 'undefined' && browser
		? new BroadcastChannel('admin-language-sync')
		: null;

let isBroadcasting = false;

type LanguageMessage = { type: 'language-changed'; locale: SupportedLocale };

function createLanguageStore() {
	const { subscribe, set: internalSet } = writable<SupportedLocale>(getInitialLocale());

	if (languageChannel) {
		languageChannel.onmessage = async (event: MessageEvent<LanguageMessage>) => {
			if (isBroadcasting) return;
			const message = event.data;
			if (message.type === 'language-changed') {
				isBroadcasting = true;
				await customSet(message.locale);
				isBroadcasting = false;
			}
		};
	}

	const customSet = async (value: SupportedLocale) => {
		if (!isInitializing && browser) {
			safeLocalStorageSet(STORAGE_KEY, value);

			try {
				await loadTranslations(value, window.location.pathname);
			} catch (error) {
				console.error('Failed to load translations:', error);
			}

			try {
				await fetch('/api/set-locale', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ locale: value })
				});
			} catch (error) {
				console.error('Failed to set locale cookie:', error);
			}

			try {
				await invalidateAll();
			} catch (error) {
				console.error('Failed to invalidate data:', error);
			}

			if (!isBroadcasting) {
				languageChannel?.postMessage({ type: 'language-changed', locale: value });
			}
		}

		internalSet(value);
	};

	return {
		subscribe,
		set: customSet,
		toggle: async () => {
			const current = get({ subscribe });
			const next: SupportedLocale = current === 'en' ? 'ru' : 'en';
			return await customSet(next);
		}
	};
}

export function initializeLanguage(locale: SupportedLocale) {
	isInitializing = true;
	currentLanguage.set(locale);
	isInitializing = false;
}

export function cleanup() {
	languageChannel?.close();
}

export const currentLanguage = createLanguageStore();
