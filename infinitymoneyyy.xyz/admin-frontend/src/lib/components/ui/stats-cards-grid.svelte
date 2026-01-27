<script lang="ts">
	import StatsCard from './stats-card.svelte';
	import { BarChart3, Users, Clock, CheckCircle, AlertCircle } from '@lucide/svelte';
	import { Skeleton } from '$lib/components/ui/skeleton';

	interface Props {
		stats: any;
		period: string;
	}

	let { stats, period }: Props = $props();

	function formatAvgTime(minutes: number | undefined): string {
		if (minutes === undefined || minutes === null) return '0 min';
		if (minutes < 60) return `${Math.round(minutes)} min`;
		const hours = Math.floor(minutes / 60);
		const mins = Math.round(minutes % 60);
		return `${hours}h ${mins}m`;
	}
</script>

{#if stats === null || stats === undefined}
	<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
		{#each Array(7) as _}
			<div class="w-full">
				<Skeleton class="h-32 w-full" />
			</div>
		{/each}
	</div>
{:else}
	<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
		<!-- Ticket Stats -->
		{#if stats.tickets}
			<StatsCard
				title="Total Tickets"
				value={stats.tickets.total ?? 0}
				description="All tickets in {period === '1d'
					? 'today'
					: period === '7d'
						? 'this week'
						: period === '30d'
							? 'this month'
							: 'all time'}"
				icon={BarChart3}
				variant="default"
				{period}
			/>

			<StatsCard
				title="Pending Tickets"
				value={stats.tickets.pending ?? 0}
				description="Awaiting processing"
				icon={AlertCircle}
				variant="warning"
				{period}
			/>

			<StatsCard
				title="Processing Tickets"
				value={stats.tickets.processing ?? 0}
				description="Currently being processed"
				icon={Clock}
				variant="default"
				{period}
			/>

			<StatsCard
				title="Completed Tickets"
				value={stats.tickets.completed ?? 0}
				description="Successfully processed"
				icon={CheckCircle}
				variant="success"
				{period}
			/>

			<StatsCard
				title="Avg Processing Time"
				value={formatAvgTime(stats.tickets.avg_time)}
				description="Average ticket processing time"
				icon={Clock}
				variant="default"
				{period}
			/>
		{/if}

		<!-- Worker Stats -->
		{#if stats.workers}
			<StatsCard
				title="Total Workers"
				value={stats.workers.total ?? 0}
				description="Registered workers"
				icon={Users}
				variant="default"
				{period}
			/>

			<StatsCard
				title="Active Workers"
				value={stats.workers.active ?? 0}
				description="Currently active"
				icon={CheckCircle}
				variant="success"
				{period}
			/>

			{#if stats.workers.pending_requests !== undefined}
				<StatsCard
					title="Pending Requests"
					value={stats.workers.pending_requests}
					description="Worker registration requests"
					icon={AlertCircle}
					variant="warning"
					{period}
				/>
			{/if}
		{/if}
	</div>
{/if}
