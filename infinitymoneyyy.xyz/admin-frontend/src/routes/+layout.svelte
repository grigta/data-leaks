<script lang="ts">
	import '../app.css';
	import { ModeWatcher } from 'mode-watcher';
	import { Toaster } from 'svelte-sonner';
	import { isLoading } from '$lib/stores/auth';
	import { fade } from 'svelte/transition';
	import { ANIMATION_DURATIONS } from '$lib/constants/animations';
	import { Loader2 } from '@lucide/svelte';
	import type { Snippet } from 'svelte';

	interface Props {
		children?: Snippet;
	}

	let { children }: Props = $props();
</script>

<ModeWatcher />
<Toaster richColors position="top-right" />

{#if $isLoading}
	<div class="flex min-h-screen items-center justify-center bg-background">
		<div class="flex flex-col items-center gap-4">
			<Loader2 class="h-8 w-8 animate-spin text-primary" />
			<p class="text-sm text-muted-foreground">Загрузка...</p>
		</div>
	</div>
{:else}
	<div transition:fade={{ duration: ANIMATION_DURATIONS.fast }}>
		{@render children?.()}
	</div>
{/if}
