import { browser } from '$app/environment';
import { writable, get } from 'svelte/store';
import { loadTranslations } from '$lib/i18n';
import { invalidateAll } from '$app/navigation';

export type SupportedLocale = 'en' | 'ru';

const STORAGE_KEY = 'app-language';
const DEFAULT_LOCALE: SupportedLocale = 'en';

// Flag to track initialization state
let isInitializing = false;

// Helper functions for safe localStorage operations
function safeLocalStorageSet(key: string, value: string): boolean {
	if (!browser) return false;
	try {
		localStorage.setItem(key, value);
		return true;
	} catch (error) {
		if (error instanceof DOMException && error.name === 'QuotaExceededError') {
			console.error('localStorage quota exceeded when setting language:', error);
		} else {
			console.error('Failed to write language to localStorage:', error);
		}
		return false;
	}
}

function safeLocalStorageGet(key: string): string | null {
	if (!browser) return null;
	try {
		return localStorage.getItem(key);
	} catch (error) {
		console.error('Failed to read language from localStorage:', error);
		return null;
	}
}

// Get saved language or default
function getInitialLocale(): SupportedLocale {
	if (!browser) return DEFAULT_LOCALE;

	const stored = safeLocalStorageGet(STORAGE_KEY);
	if (stored === 'en' || stored === 'ru') {
		return stored;
	}

	// Detect from browser
	try {
		const browserLang = navigator.language.split('-')[0];
		return browserLang === 'ru' ? 'ru' : 'en';
	} catch (error) {
		console.error('Failed to detect browser language:', error);
		return DEFAULT_LOCALE;
	}
}

// BroadcastChannel for cross-tab synchronization
const languageChannel =
	typeof BroadcastChannel !== 'undefined' && browser
		? new BroadcastChannel('language-sync')
		: null;

// Flag to prevent circular broadcasts
let isBroadcasting = false;

// Types for broadcast messages
type LanguageMessage = { type: 'language-changed'; locale: SupportedLocale };

// Store with current language
function createLanguageStore() {
	const { subscribe, set: internalSet } = writable<SupportedLocale>(getInitialLocale());

	// Listen for messages from other tabs
	if (languageChannel) {
		languageChannel.onmessage = async (event: MessageEvent<LanguageMessage>) => {
			if (isBroadcasting) return; // Prevent circular updates

			const message = event.data;
			if (message.type === 'language-changed') {
				// Set flag to prevent re-broadcasting
				isBroadcasting = true;
				await customSet(message.locale);
				isBroadcasting = false;
			}
		};
	}

	const customSet = async (value: SupportedLocale) => {
		// Skip side effects during initialization
		if (!isInitializing && browser) {
			// Сохранить в localStorage
			const saved = safeLocalStorageSet(STORAGE_KEY, value);
			if (!saved) {
				console.warn('Failed to persist language, continuing with in-memory value');
			}

			// Загрузить переводы (также устанавливает локаль в i18n)
			try {
				await loadTranslations(value, window.location.pathname);
			} catch (error) {
				console.error('Failed to load translations:', error);
				// Continue - language will be applied even if translations fail
			}

			// Установить cookie на сервере
			try {
				await fetch('/api/set-locale', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ locale: value })
				});
			} catch (error) {
				console.error('Failed to set locale cookie (status/message):', error);
			}

			// Обновить серверные данные
			try {
				await invalidateAll();
			} catch (error) {
				console.error('Failed to invalidate data:', error);
				// Continue - language is already applied locally
			}

			// Broadcast to other tabs (only if not already broadcasting)
			if (!isBroadcasting) {
				languageChannel?.postMessage({ type: 'language-changed', locale: value });
			}
		}

		// Обновить store (loadTranslations уже установил локаль в i18n)
		internalSet(value);
	};

	return {
		subscribe,
		set: customSet,
		toggle: async () => {
			const current = get({ subscribe });
			const next: SupportedLocale = current === 'en' ? 'ru' : 'en';

			// Делегируем всю логику методу customSet для централизации побочных эффектов
			return await customSet(next);
		}
	};
}

// Initialization function for SSR/hydration (replaces _set method)
export function initializeLanguage(locale: SupportedLocale) {
	isInitializing = true;
	currentLanguage.set(locale);
	isInitializing = false;
}

// Cleanup function for BroadcastChannel
export function cleanup() {
	languageChannel?.close();
}

export const currentLanguage = createLanguageStore();
