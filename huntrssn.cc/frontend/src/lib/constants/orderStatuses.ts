export const ORDER_STATUSES = [
	{ value: 'all', label: 'All' },
	{ value: 'pending', label: 'Pending' },
	{ value: 'completed', label: 'Completed' },
	{ value: 'failed', label: 'Failed' },
	{ value: 'cancelled', label: 'Cancelled' }
];

export function getStatusLabel(status: string): string {
	const statusObj = ORDER_STATUSES.find(s => s.value === status);
	return statusObj?.label || status;
}
