<script lang="ts">
	import { getContext } from 'svelte';
	import { cn } from '$lib/utils';
	import type { HTMLButtonAttributes } from 'svelte/elements';

	type Props = HTMLButtonAttributes & {
		value: string;
		class?: string;
		children?: any;
	};

	let { value, class: className, children, ...restProps }: Props = $props();

	const context = getContext<any>('select');
	let buttonRef: HTMLButtonElement;

	function handleClick(event: MouseEvent) {
		const label = buttonRef?.textContent?.trim() || value;
		context?.onSelect(value, label);
	}
</script>

<button
	bind:this={buttonRef}
	type="button"
	class={cn(
		'relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 px-2 text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground',
		className
	)}
	onclick={handleClick}
	{...restProps}
>
	{@render children?.()}
</button>
