<script lang="ts">
	import { getContext } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	type Props = HTMLAttributes<HTMLSpanElement> & {
		placeholder?: string;
	};

	let { placeholder = '', ...restProps }: Props = $props();

	const context = getContext<any>('select');
	const selectedValue = context?.selectedValue;
	const selectedLabel = context?.selectedLabel;
</script>

<span {...restProps}>
	{#if $selectedValue}
		{$selectedLabel || $selectedValue}
	{:else}
		{placeholder}
	{/if}
</span>
