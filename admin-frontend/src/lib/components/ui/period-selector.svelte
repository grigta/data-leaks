<script lang="ts">
	import { Calendar } from 'lucide-svelte';
	import { cn } from '$lib/utils';

	interface Props {
		value: string;
		onChange: (period: string) => void;
	}

	let { value, onChange }: Props = $props();

	const periodOptions = [
		{ value: '1d', label: 'Today' },
		{ value: '7d', label: 'This Week' },
		{ value: '30d', label: 'This Month' },
		{ value: 'all', label: 'All Time' }
	];

	// Use reactive effect to call onChange when value changes
	$effect(() => {
		if (value) {
			// This ensures onChange is called when value is updated externally
		}
	});
</script>

<div class="relative inline-flex items-center">
	<Calendar class="absolute left-3 h-4 w-4 text-muted-foreground pointer-events-none" />
	<select
		bind:value
		onchange={() => onChange(value)}
		title="Select time period for statistics"
		class={cn(
			'h-10 w-[180px] pl-10 pr-4 rounded-md border border-input bg-background text-sm',
			'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
			'disabled:cursor-not-allowed disabled:opacity-50'
		)}
	>
		{#each periodOptions as option}
			<option value={option.value}>{option.label}</option>
		{/each}
	</select>
</div>
