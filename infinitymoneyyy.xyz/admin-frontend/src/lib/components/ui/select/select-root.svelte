<script lang="ts">
	import { setContext } from 'svelte';
	import { writable } from 'svelte/store';

	interface Props {
		value?: string;
		onSelectedChange?: (selected: { value?: string } | undefined) => void;
		children?: any;
	}

	let { value = $bindable(), onSelectedChange, children }: Props = $props();

	const selectedValue = writable(value);
	const selectedLabel = writable('');

	$effect(() => {
		selectedValue.set(value);
	});

	setContext('select', {
		selectedValue,
		selectedLabel,
		onSelect: (newValue: string, label: string) => {
			value = newValue;
			selectedValue.set(newValue);
			selectedLabel.set(label);
			onSelectedChange?.({ value: newValue });
		}
	});
</script>

{@render children?.()}
