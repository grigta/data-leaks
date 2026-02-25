<script lang="ts">
	import '../app.css';
	import { ModeWatcher } from 'mode-watcher';
	import { Toaster } from 'svelte-sonner';
	import { isLoading } from '$lib/stores/auth';
	import { fade } from 'svelte/transition';
	import { ANIMATION_DURATIONS } from '$lib/constants/animations';
	import { Loader2 } from '@lucide/svelte';
	import type { Snippet } from 'svelte';
	import { browser } from '$app/environment';
	import { page } from '$app/stores';
	import { loadTranslations, setRoute, t } from '$lib/i18n';
	import { currentLanguage, initializeLanguage } from '$lib/stores/language';

	interface Props {
		children?: Snippet;
		data: { locale: string };
	}

	let { children, data }: Props = $props();

	let lastLocale: string | undefined = undefined;
	let lastRoute: string | undefined = undefined;

	$effect(() => {
		if (browser) {
			const currentRoute = $page.url.pathname;
			const currentLocale = $currentLanguage || data?.locale || 'en';

			if (lastLocale === currentLocale && lastRoute === currentRoute) return;

			lastLocale = currentLocale;
			lastRoute = currentRoute;

			setRoute(currentRoute);
			loadTranslations(currentLocale, currentRoute);
		}
	});

	$effect(() => {
		if (browser && data?.locale) {
			initializeLanguage(data.locale as 'en' | 'ru');
		}
	});
</script>

<ModeWatcher />
<Toaster richColors position="top-right" />

{#if $isLoading}
	<div class="flex min-h-screen items-center justify-center bg-background">
		<div class="flex flex-col items-center gap-4">
			<Loader2 class="h-8 w-8 animate-spin text-primary" />
			<p class="text-sm text-muted-foreground">{$t('common.loading')}</p>
		</div>
	</div>
{:else}
	<div transition:fade={{ duration: ANIMATION_DURATIONS.fast }}>
		{@render children?.()}
	</div>
{/if}
