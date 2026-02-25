import { writable } from 'svelte/store';

/** Number of currently online workers (updated by workers page) */
export const onlineWorkerCount = writable<number | null>(null);
