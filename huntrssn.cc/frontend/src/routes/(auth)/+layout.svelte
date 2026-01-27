<script lang="ts">
	import { page } from '$app/stores';
	import { fade, fly } from 'svelte/transition';
	import { ANIMATION_DURATIONS } from '$lib/constants/animations';
	import { isInitializing } from '$lib/stores/auth';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { t, loading } from '$lib/i18n';

	let { children } = $props();
</script>

<div class="min-h-screen bg-background flex items-center justify-center p-4">
	<div class="w-full max-w-md mx-auto">
		{#if $loading || $isInitializing}
			<div class="w-full max-w-md animate-in fade-in duration-slow flex flex-col items-center">
				<div class="space-y-4 w-full">
					<!-- Card header skeleton -->
					<Skeleton class="h-8 w-48 mb-2" />
					<Skeleton class="h-4 w-64 mb-6" />

					<!-- Input field skeleton -->
					<Skeleton class="h-4 w-24 mb-2" />
					<Skeleton class="h-12 w-full mb-4" />

					<!-- Button skeleton -->
					<Skeleton class="h-12 w-full mb-4" />

					<!-- Footer text skeleton -->
					<Skeleton class="h-4 w-48 mx-auto" />
				</div>
			</div>
		{:else}
			{@render children?.()}
		{/if}
	</div>
</div>
