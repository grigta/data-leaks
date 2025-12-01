<script lang="ts">
	import { Avatar as AvatarPrimitive } from "bits-ui";
	import { cn } from "$lib/utils";
	import type { Snippet } from "svelte";

	let {
		ref = $bindable(null),
		class: className,
		children,
		...restProps
	}: AvatarPrimitive.RootProps & { children?: Snippet } = $props();
</script>

<AvatarPrimitive.Root
	bind:ref
	class={cn("relative flex size-10 shrink-0 overflow-hidden rounded-full", className)}
	{...restProps}
>
	{@render children?.()}
</AvatarPrimitive.Root>
