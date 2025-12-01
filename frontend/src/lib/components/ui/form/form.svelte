<script lang="ts">
	import type { SuperForm } from 'sveltekit-superforms';
	import type { AnyZodObject } from 'zod';
	import type { Snippet } from 'svelte';

	interface Props {
		form: SuperForm<any>;
		schema: AnyZodObject;
		children?: Snippet<[{ config: { form: SuperForm<any>; name: string } }]>;
	}

	let { form, schema, children }: Props = $props();
</script>

{@render children?.({ config: { form, name: '' } })}
