<script lang="ts">
	import Sun from '@lucide/svelte/icons/sun';
	import Moon from '@lucide/svelte/icons/moon';
	import { currentTheme } from '$lib/stores/theme';
	import { t } from '$lib/i18n';

	const isDark = $derived($currentTheme === 'dark');

	function toggle() {
		currentTheme.set(isDark ? 'light' : 'dark');
	}
</script>

<button
	onclick={toggle}
	class="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 hover:bg-accent hover:text-accent-foreground h-10 w-10 relative"
	aria-label={$t('common.toggleTheme')}
>
	<Sun
		class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-5 w-5 {isDark
			? 'hidden'
			: ''}"
	/>
	<Moon
		class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-5 w-5 {isDark
			? ''
			: 'hidden'}"
	/>
</button>
