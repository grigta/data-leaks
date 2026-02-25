<script lang="ts">
	import { getContext } from 'svelte';
	import { cn } from '$lib/utils';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import type { HTMLButtonAttributes } from 'svelte/elements';

	type Props = HTMLButtonAttributes & {
		class?: string;
		children?: any;
		title?: string;
	};

	let { class: className, children, title, ...restProps }: Props = $props();

	const context = getContext<any>('select');
</script>

<button
	type="button"
	class={cn(
		'flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50',
		className
	)}
	onclick={() => context?.toggle()}
	{title}
	{...restProps}
>
	{@render children?.()}
	<ChevronDown class="h-4 w-4 opacity-50 shrink-0 ml-2" />
</button>
