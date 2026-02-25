<script lang="ts">
	import { cn } from '$lib/utils';
	import Crosshair from '@lucide/svelte/icons/crosshair';

	type LogoSize = 'small' | 'default' | 'large';
	type LogoVariant = 'full' | 'compact';

	interface LogoProps {
		size?: LogoSize;
		variant?: LogoVariant;
		class?: string;
	}

	let { size = 'default', variant = 'full', class: className }: LogoProps = $props();

	const sizeClasses = {
		small: 'text-lg',
		default: 'text-2xl',
		large: 'text-4xl'
	};

	const iconSizeClasses = {
		small: 'h-5 w-5',
		default: 'h-6 w-6',
		large: 'h-8 w-8'
	};
</script>

<a
	href="/"
	class={cn(
		'flex items-center gap-2 text-foreground font-heading font-bold tracking-wide hover:opacity-80 transition-colors duration-200',
		sizeClasses[size],
		className
	)}
	aria-label="Huntr Home"
>
	<Crosshair class={cn('text-primary flex-shrink-0', iconSizeClasses[size])} />
	{#if variant === 'full'}
		<span>Huntr</span>
	{/if}
</a>
