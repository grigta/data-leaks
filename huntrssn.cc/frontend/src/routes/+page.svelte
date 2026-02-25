<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { isAuthenticated, isInitializing } from '$lib/stores/auth';

	$effect(() => {
		if (browser && !$isInitializing) {
			if ($isAuthenticated) {
				goto('/search', { replaceState: true });
			} else {
				goto('/login', { replaceState: true });
			}
		}
	});
</script>

<div class="flex min-h-screen items-center justify-center bg-background">
	<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-foreground"></div>
</div>
