<script lang="ts">
	import { cn } from '$lib/utils';

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

	const text = variant === 'full' ? 'Data-Leaks' : 'DL';
</script>

<a
	href="/"
	class={cn(
		'logo-text text-foreground font-michroma font-bold tracking-wider transition-all duration-300 hover:opacity-80',
		sizeClasses[size],
		className
	)}
	aria-label="Data-Leaks Home"
>
	{text}
</a>

<style>
	.logo-text {
		text-decoration: none;
		display: inline-block;
	}

	.logo-text:hover {
		transform: scale(1.02);
	}
</style>
