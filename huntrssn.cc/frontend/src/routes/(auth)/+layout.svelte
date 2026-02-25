<script lang="ts">
	import { page } from '$app/stores';
	import { fade, fly } from 'svelte/transition';
	import { ANIMATION_DURATIONS } from '$lib/constants/animations';
	import { isInitializing } from '$lib/stores/auth';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { t, loading } from '$lib/i18n';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import { currentLanguage } from '$lib/stores/language';
	import Globe from '@lucide/svelte/icons/globe';
	import Crosshair from '@lucide/svelte/icons/crosshair';

	let { children } = $props();

	function toggleLanguage() {
		currentLanguage.toggle();
	}
</script>

<div class="min-h-screen bg-background flex flex-col">
	<!-- Header -->
	<header class="flex items-center justify-between px-6 py-4">
		<a href="/" class="flex items-center gap-2 text-foreground hover:opacity-80 transition-opacity">
			<Crosshair class="h-6 w-6 text-primary" />
			<span class="text-xl font-heading font-bold tracking-wide">Huntr</span>
		</a>
		<div class="flex items-center gap-1">
			<ThemeToggle />
			<button
				onclick={toggleLanguage}
				class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 hover:bg-accent hover:text-accent-foreground h-10 w-10"
				aria-label="Switch language"
			>
				<Globe class="h-5 w-5" />
			</button>
		</div>
	</header>

	<!-- Content -->
	<div class="flex-1 flex items-center justify-center p-4">
		<div class="w-full max-w-md mx-auto p-6 rounded-lg">
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
</div>
