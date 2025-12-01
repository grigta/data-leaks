import { browser } from '$app/environment';
import { get, writable } from 'svelte/store';
import { mode, setMode } from 'mode-watcher';

export type Theme = 'light' | 'dark';
export type ThemeMode = 'light' | 'dark';

const STORAGE_KEY = 'app-theme';
const DEFAULT_THEME: Theme = 'light';

// Helper function for safe mode setting
function safeSetMode(value: ThemeMode): boolean {
	try {
		setMode(value);
		return true;
	} catch (error) {
		if (error instanceof DOMException && error.name === 'QuotaExceededError') {
			console.error('localStorage quota exceeded when setting theme:', error);
		} else {
			console.error('Failed to set theme mode:', error);
		}
		return false;
	}
}

// Store with current theme - создаём функцию, которая безопасно инициализирует stores
function createThemeStore() {

	// Создаём writable store для хранения текущей темы
	const themeStore = writable<Theme>(DEFAULT_THEME);

	// Флаг для предотвращения повторной инициализации
	let isInitialized = false;

	// Функция инициализации, которая будет вызвана после загрузки всех зависимостей
	const initialize = () => {
		if (isInitialized || !browser) return;
		isInitialized = true;

		try {
			// Миграция старого ключа 'app-theme' на 'mode-watcher-mode'
			// и автоматическая миграция с 'system' на 'dark'
			const oldTheme = localStorage.getItem(STORAGE_KEY);
			let newTheme = localStorage.getItem('mode-watcher-mode');

			// Если в новом ключе сохранен 'system', заменяем на 'dark'
			if (newTheme === 'system') {
				safeSetMode('dark');
				newTheme = 'dark';
			}

			// Если есть старый ключ, но нет нового - мигрировать
			if (oldTheme && !newTheme) {
				const migratedTheme =
					oldTheme === 'system' ? 'dark' : oldTheme === 'light' || oldTheme === 'dark' ? oldTheme : 'dark';
				safeSetMode(migratedTheme);
				localStorage.removeItem(STORAGE_KEY);
			}
		} catch (error) {
			console.error('Failed to access localStorage during theme initialization:', error);
			// Continue with default theme
		}

		// Подписываемся на изменения mode
		const unsubscribeMode = mode.subscribe(($mode) => {
			// Используем только 'light' или 'dark'
			if ($mode === 'light' || $mode === 'dark') {
				themeStore.set($mode);
			} else {
				// Если mode невалидный, устанавливаем 'light'
				themeStore.set('light');
				safeSetMode('light');
			}
		});

		// Cleanup функция не нужна, так как stores живут весь жизненный цикл приложения
	};

	// Вызываем инициализацию сразу если в браузере
	if (browser) {
		// Используем setTimeout для гарантии, что все импорты загружены
		setTimeout(initialize, 0);
	}

	const customSet = (value: Theme) => {
		if (!browser) return;

		// Только 'light' или 'dark'
		if (value === 'light' || value === 'dark') {
			const success = safeSetMode(value);
			if (!success) {
				console.warn('Failed to persist theme, continuing with in-memory value');
			}
			// Update store in memory even if localStorage failed
			themeStore.set(value);
		}
	};

	const customToggle = () => {
		if (!browser) return;

		// Get current effective theme (not raw mode)
		const currentEffective = get(themeStore);

		// Toggle based on effective theme
		const next: Theme = currentEffective === 'dark' ? 'light' : 'dark';

		// Use customSet to apply and persist
		customSet(next);
	};

	return {
		subscribe: themeStore.subscribe,
		set: customSet,
		toggle: customToggle,
		initialize // Экспортируем для явного вызова если нужно
	};
}

export const currentTheme = createThemeStore();
