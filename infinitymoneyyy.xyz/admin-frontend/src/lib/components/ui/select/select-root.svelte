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
	const open = writable(false);

	$effect(() => {
		selectedValue.set(value);
	});

	setContext('select', {
		selectedValue,
		selectedLabel,
		open,
		toggle: () => {
			open.update((v) => !v);
		},
		close: () => {
			open.set(false);
		},
		onSelect: (newValue: string, label: string) => {
			value = newValue;
			selectedValue.set(newValue);
			selectedLabel.set(label);
			open.set(false);
			onSelectedChange?.({ value: newValue });
		}
	});
</script>

<div class="relative">
	{@render children?.()}
</div>
