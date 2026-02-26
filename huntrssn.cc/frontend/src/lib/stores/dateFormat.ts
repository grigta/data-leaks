import { browser } from '$app/environment';
import { writable } from 'svelte/store';

export type DateFormatType = 'mmdd' | 'ddmm';

const STORAGE_KEY = 'dob-format';
const DEFAULT_FORMAT: DateFormatType = 'ddmm';

function getInitialFormat(): DateFormatType {
	if (!browser) return DEFAULT_FORMAT;
	try {
		const stored = localStorage.getItem(STORAGE_KEY);
		if (stored === 'mmdd' || stored === 'ddmm') return stored;
	} catch {
		// ignore
	}
	return DEFAULT_FORMAT;
}

function createDateFormatStore() {
	const { subscribe, set: internalSet, update } = writable<DateFormatType>(getInitialFormat());

	return {
		subscribe,
		set(value: DateFormatType) {
			if (browser) {
				try {
					localStorage.setItem(STORAGE_KEY, value);
				} catch {
					// ignore
				}
			}
			internalSet(value);
		},
		toggle() {
			update((current) => {
				const next: DateFormatType = current === 'ddmm' ? 'mmdd' : 'ddmm';
				if (browser) {
					try {
						localStorage.setItem(STORAGE_KEY, next);
					} catch {
						// ignore
					}
				}
				return next;
			});
		}
	};
}

export const dateFormat = createDateFormatStore();
