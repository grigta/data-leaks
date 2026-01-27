<script lang="ts">
	import { getContext } from "svelte";

	let {
		placeholder = "",
		class: className = "",
		...restProps
	}: {
		placeholder?: string;
		class?: string;
		[key: string]: any;
	} = $props();

	// Try to get the selected value from context if available
	const ctx = getContext("select");
	const selected: any = ctx?.selected || {};

	const displayValue = $derived(
		selected?.label || placeholder
	);
</script>

<span class={className} {...restProps}>{displayValue}</span>
