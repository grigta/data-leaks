import { setMode, mode, userPrefersMode } from 'mode-watcher';
import { get } from 'svelte/store';

export type Theme = 'light' | 'dark' | 'system';

// Re-export mode-watcher functionality for convenience
export { setMode as setTheme, mode as currentMode, userPrefersMode };

// Helper function to toggle through themes (light -> dark -> system -> light)
export function toggleTheme(): void {
	const current = get(userPrefersMode);
	if (current === 'light') {
		setMode('dark');
	} else if (current === 'dark') {
		setMode('system');
	} else {
		setMode('light');
	}
}
