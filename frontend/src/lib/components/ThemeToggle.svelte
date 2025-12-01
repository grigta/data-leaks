<script lang="ts">
	import Sun from '@lucide/svelte/icons/sun';
	import Moon from '@lucide/svelte/icons/moon';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import { currentTheme } from '$lib/stores/theme';
	import { mode } from 'mode-watcher';
	import { t } from '$lib/i18n';

	const isDark = $derived($currentTheme === 'dark');
	const currentMode = $derived($mode);
</script>

<DropdownMenu.Root>
	<DropdownMenu.Trigger
		class="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 hover:bg-accent hover:text-accent-foreground h-10 w-10 relative hover:opacity-80 transition-opacity duration-normal"
		aria-label={$t('common.toggleTheme')}
	>
		<Sun
			class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-5 w-5 transition-all duration-normal {isDark
				? 'rotate-90 scale-0 opacity-0'
				: 'rotate-0 scale-100 opacity-100'}"
		/>
		<Moon
			class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-5 w-5 transition-all duration-normal {isDark
				? 'rotate-0 scale-100 opacity-100'
				: '-rotate-90 scale-0 opacity-0'}"
		/>
	</DropdownMenu.Trigger>
	<DropdownMenu.Content align="end">
		<DropdownMenu.Item onclick={() => currentTheme.set('light')}>
			<Sun class="mr-2 h-4 w-4" />
			<span>Light</span>
			{#if currentMode === 'light'}
				<span class="ml-auto">✓</span>
			{/if}
		</DropdownMenu.Item>
		<DropdownMenu.Item onclick={() => currentTheme.set('dark')}>
			<Moon class="mr-2 h-4 w-4" />
			<span>Dark</span>
			{#if currentMode === 'dark'}
				<span class="ml-auto">✓</span>
			{/if}
		</DropdownMenu.Item>
	</DropdownMenu.Content>
</DropdownMenu.Root>
