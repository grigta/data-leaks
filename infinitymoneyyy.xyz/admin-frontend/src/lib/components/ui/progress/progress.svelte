<script lang="ts">
	import { cn } from '$lib/utils.js';
	import type { HTMLAttributes } from 'svelte/elements';

	type $$Props = HTMLAttributes<HTMLDivElement> & {
		value?: number;
		max?: number;
		class?: string;
	};

	let className: $$Props['class'] = undefined;
	export { className as class };
	export let value: $$Props['value'] = 0;
	export let max: $$Props['max'] = 100;

	$: normalizedValue = Math.min(max || 100, Math.max(0, value || 0));
	$: percentageValue = ((normalizedValue || 0) / (max || 100)) * 100;
</script>

<div
	role="progressbar"
	aria-valuemin={0}
	aria-valuemax={max}
	aria-valuenow={normalizedValue}
	class={cn('relative h-4 w-full overflow-hidden rounded-full bg-secondary', className)}
	{...$$restProps}
>
	<div
		class="h-full w-full flex-1 bg-primary transition-all"
		style="transform: translateX(-{100 - percentageValue}%)"
	/>
</div>