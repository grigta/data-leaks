import { getStatsTickets, getStatsWorkers } from '$lib/api/client';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ url }) => {
	const period = url.searchParams.get('period') || '7d';

	try {
		const [tickets, workers] = await Promise.all([
			getStatsTickets({ period }),
			getStatsWorkers({ period })
		]);

		return {
			period,
			stats: {
				tickets,
				workers
			}
		};
	} catch (error) {
		console.error('Failed to load stats:', error);
		return {
			period,
			stats: null,
			error: 'Failed to load statistics'
		};
	}
};
