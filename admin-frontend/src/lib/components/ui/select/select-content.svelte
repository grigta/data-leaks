<script lang="ts">
	import { cn } from '$lib/utils';
	import type { HTMLAttributes } from 'svelte/elements';

	type Props = HTMLAttributes<HTMLDivElement> & {
		class?: string;
		position?: string;
		children?: any;
	};

	let { class: className, position, children, ...restProps }: Props = $props();
</script>

<div
	class={cn(
		'absolute z-50 min-w-[8rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md',
		className
	)}
	{...restProps}
>
	{@render children?.()}
</div>
