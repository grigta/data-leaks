<script lang="ts">
	import '../app.css';
	import { ModeWatcher } from 'mode-watcher';
	import { Toaster } from 'svelte-sonner';
	import { onMount } from 'svelte';
	import { initialize } from '$lib/stores/auth';
	import { loadTranslations, setRoute, locale } from '$lib/i18n';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';

	let { children, data } = $props();

	// Мемоизация для предотвращения дублирующихся вызовов loadTranslations
	let lastLocale: string | undefined = undefined;
	let lastRoute: string | undefined = undefined;

	onMount(() => {
		initialize();
	});

	$effect(() => {
		if (browser) {
			const currentRoute = $page.url.pathname;
			const currentLocale = data?.locale || $locale || 'en';

			// Проверяем, изменились ли locale или route
			if (lastLocale === currentLocale && lastRoute === currentRoute) {
				return; // Ничего не изменилось, пропускаем загрузку
			}

			// Обновляем мемоизированные значения
			lastLocale = currentLocale;
			lastRoute = currentRoute;

			setRoute(currentRoute);
			loadTranslations(currentLocale, currentRoute);
		}
	});
</script>

<ModeWatcher />
<Toaster richColors position="top-right" />

{@render children?.()}
