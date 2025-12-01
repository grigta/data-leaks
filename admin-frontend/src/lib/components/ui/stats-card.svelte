<script lang="ts">
	import { Card, CardContent, CardHeader } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import type { Component } from 'svelte';

	interface Props {
		title: string;
		value: string | number;
		change?: number;
		description?: string;
		icon: Component;
		variant?: 'default' | 'success' | 'warning' | 'destructive';
		period?: string;
	}

	let {
		title,
		value,
		change,
		description,
		icon: Icon,
		variant = 'default',
		period
	}: Props = $props();

	const variantStyles = {
		default: {
			border: 'border-l-blue-500',
			iconColor: 'text-blue-500',
			bg: 'bg-blue-50'
		},
		success: {
			border: 'border-l-green-500',
			iconColor: 'text-green-500',
			bg: 'bg-green-50'
		},
		warning: {
			border: 'border-l-yellow-500',
			iconColor: 'text-yellow-500',
			bg: 'bg-yellow-50'
		},
		destructive: {
			border: 'border-l-red-500',
			iconColor: 'text-red-500',
			bg: 'bg-red-50'
		}
	};

	const currentVariant = variantStyles[variant];
</script>

<Card
	class="w-full border-l-4 {currentVariant.border} hover:scale-105 transition-transform duration-200"
>
	<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
		<h3 class="text-sm font-medium text-muted-foreground">{title}</h3>
		<div class="h-8 w-8 rounded-full {currentVariant.bg} flex items-center justify-center">
			<Icon class="h-4 w-4 {currentVariant.iconColor}" />
		</div>
	</CardHeader>
	<CardContent>
		<div class="text-3xl font-bold">{value}</div>
		{#if description}
			<p class="text-sm text-muted-foreground mt-1">{description}</p>
		{/if}
		{#if change !== undefined && change !== 0}
			<Badge
				variant={change > 0 ? 'default' : 'destructive'}
				class="mt-2 {change > 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}"
			>
				{change > 0 ? '+' : ''}{change}%
			</Badge>
		{/if}
	</CardContent>
</Card>
