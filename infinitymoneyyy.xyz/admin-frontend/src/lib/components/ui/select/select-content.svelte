<script lang="ts">
	import { getContext, onMount, onDestroy } from 'svelte';
	import { cn } from '$lib/utils';
	import type { HTMLAttributes } from 'svelte/elements';

	type Props = HTMLAttributes<HTMLDivElement> & {
		class?: string;
		position?: string;
		children?: any;
	};

	let { class: className, position, children, ...restProps }: Props = $props();

	const context = getContext<any>('select');
	const open = context?.open;

	let contentRef: HTMLDivElement;

	function handleClickOutside(event: MouseEvent) {
		if (contentRef && !contentRef.parentElement?.contains(event.target as Node)) {
			context?.close();
		}
	}

	onMount(() => {
		document.addEventListener('click', handleClickOutside, true);
	});

	onDestroy(() => {
		document.removeEventListener('click', handleClickOutside, true);
	});
</script>

{#if $open}
	<div
		bind:this={contentRef}
		class={cn(
			'absolute z-50 mt-1 min-w-[8rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md animate-in fade-in-0 zoom-in-95',
			className
		)}
		{...restProps}
	>
		{@render children?.()}
	</div>
{/if}
