<script lang="ts">
	import { Avatar as AvatarPrimitive } from "bits-ui";
	import { cn } from "$lib/utils";
	import type { Snippet } from "svelte";

	let {
		ref = $bindable(null),
		class: className,
		children,
		...restProps
	}: AvatarPrimitive.FallbackProps & { children?: Snippet } = $props();
</script>

<AvatarPrimitive.Fallback
	bind:ref
	class={cn("bg-muted flex size-full items-center justify-center", className)}
	{...restProps}
>
	{@render children?.()}
</AvatarPrimitive.Fallback>
