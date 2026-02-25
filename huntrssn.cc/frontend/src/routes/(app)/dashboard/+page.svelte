<script lang="ts">
	import { onMount } from 'svelte';
	import { Card } from '$lib/components/ui/card';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { t } from '$lib/i18n';
	import { getNews, type NewsResponse, handleApiError } from '$lib/api/client';
	import { formatDate } from '$lib/utils';

	let news = $state<NewsResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let abortController: AbortController | null = null;

	async function loadNews() {
		// Cancel previous request if exists
		if (abortController) {
			abortController.abort();
		}

		// Create new abort controller
		abortController = new AbortController();
		const currentController = abortController;

		isLoading = true;
		error = '';
		try {
			const response = await getNews({ limit: 10, offset: 0 });
			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				news = response.news;
			}
		} catch (err: unknown) {
			// Only update error if not aborted
			if (!currentController.signal.aborted) {
				error = handleApiError(err);
				news = [];
			}
		} finally {
			// Only update loading state if not aborted
			if (!currentController.signal.aborted) {
				isLoading = false;
			}
		}
	}

	onMount(() => {
		loadNews();

		// Cleanup function
		return () => {
			if (abortController) {
				abortController.abort();
			}
		};
	});
</script>

<div class="space-y-6">
	<!-- Page Header -->
	<div class="flex items-center justify-center">
		<h1 class="text-2xl font-semibold">{$t('dashboard.title')}</h1>
	</div>

	<!-- News Cards -->
	<div class="space-y-4">
		{#if isLoading}
			{#each Array(4) as _, i}
				<Card class="p-6 transition-colors">
					<div class="flex items-start justify-between mb-3">
						<Skeleton class="h-6 w-48" />
						<Skeleton class="h-5 w-24" />
					</div>
					<Skeleton class="h-4 w-full mb-2" />
					<Skeleton class="h-4 w-3/4" />
				</Card>
			{/each}
		{:else if error}
			<Alert variant="destructive">
				<AlertDescription>{error}</AlertDescription>
			</Alert>
			<div class="flex justify-center">
				<button
					on:click={loadNews}
					class="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
				>
					Try Again
				</button>
			</div>
		{:else if news.length === 0}
			<Card class="p-8 text-center">
				<p class="text-muted-foreground mb-2">No news available</p>
				<p class="text-sm text-muted-foreground">Check back later for updates</p>
			</Card>
		{:else}
			{#each news as newsItem (newsItem.id)}
				<Card class="p-6 hover:bg-accent hover:shadow-md transition-all duration-200 space-y-3">
					<div class="flex items-start justify-between">
						<h3 class="text-lg font-semibold">{newsItem.title}</h3>
						<span class="text-xs text-muted-foreground">
							{newsItem.created_at ? formatDate(newsItem.created_at) : '—'}
						</span>
					</div>
					<p class="text-sm text-muted-foreground leading-relaxed">{newsItem.content}</p>
				</Card>
			{/each}
		{/if}
	</div>
</div>
