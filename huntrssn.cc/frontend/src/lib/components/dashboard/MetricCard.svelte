<script lang="ts">
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Skeleton } from '$lib/components/ui/skeleton';

	let { title, value, icon, subtitle, loading = false }: {
		title: string;
		value: string | number;
		icon: any;
		subtitle?: string;
		loading?: boolean;
	} = $props();
</script>

<Card>
	<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
		<CardTitle class="text-sm font-medium">{title}</CardTitle>
		<svelte:component this={icon} class="h-4 w-4 text-muted-foreground" />
	</CardHeader>
	<CardContent>
		{#if loading}
			<Skeleton class="h-8 w-24" />
		{:else}
			<div class="text-2xl font-bold">{value}</div>
			{#if subtitle}
				<p class="text-xs text-muted-foreground">{subtitle}</p>
			{/if}
		{/if}
	</CardContent>
</Card>
