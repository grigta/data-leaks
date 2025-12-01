<script lang="ts">
	import type { SSNRecord } from '$lib/api/client';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Button } from '$lib/components/ui/button';
	import * as Tooltip from '$lib/components/ui/tooltip';
	import Mail from '@lucide/svelte/icons/mail';
	import Phone from '@lucide/svelte/icons/phone';
	import MapPin from '@lucide/svelte/icons/map-pin';
	import User from '@lucide/svelte/icons/user';
	import Calendar from '@lucide/svelte/icons/calendar';
	import CreditCard from '@lucide/svelte/icons/credit-card';
	import ShoppingCart from '@lucide/svelte/icons/shopping-cart';
	import Check from '@lucide/svelte/icons/check';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import { maskSSN, formatDate, maskDOB, formatCurrency } from '$lib/utils';
	import { getRecordPrice, DEFAULT_RECORD_PRICE } from '$lib/constants/pricing';
	import { t } from '$lib/i18n';

	let {
		results = [],
		loading = false,
		showCartButton = false,
		onAddToCart = undefined,
		processingSSNs = new Set()
	}: {
		results?: SSNRecord[];
		loading?: boolean;
		showCartButton?: boolean;
		onAddToCart?: ((record: SSNRecord) => void) | undefined;
		processingSSNs?: Set<string>;
	} = $props();

	$effect(() => {
		console.log('[SearchResultCards] results:', results);
		console.log('[SearchResultCards] results.length:', results.length);
		console.log('[SearchResultCards] loading:', loading);
	});

	function isInCart(ssn: string): boolean {
		// Cart functionality removed
		return false;
	}

	function getRecordPriceWithFallback(source_table?: string): number {
		return getRecordPrice(source_table) ?? DEFAULT_RECORD_PRICE;
	}

	function hasValidPrice(source_table?: string): boolean {
		if (!source_table) return false;
		const price = getRecordPrice(source_table);
		return price !== null && price !== undefined;
	}
</script>

<div class="w-full">
	{#if loading}
		<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
			{#each Array(4) as _}
				<Card>
					<CardHeader>
						<Skeleton class="h-6 w-48" />
					</CardHeader>
					<CardContent class="space-y-3">
						<Skeleton class="h-4 w-full" />
						<Skeleton class="h-4 w-full" />
						<Skeleton class="h-4 w-3/4" />
						<Skeleton class="h-4 w-2/3" />
					</CardContent>
				</Card>
			{/each}
		</div>
	{:else if results.length === 0}
		<Card>
			<CardContent class="pt-6">
				<div class="text-center text-muted-foreground py-8">{$t('search.common.notFound')}</div>
			</CardContent>
		</Card>
	{:else}
		<div class="space-y-4">
			<div class="text-sm text-muted-foreground mb-4">
				{$t('search.common.recordsFound')} <span class="font-semibold">{results.length}</span>
			</div>

			<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
				{#each results as record}
					<Card class="hover:shadow-md transition-shadow relative">
						<CardHeader class="pb-3">
							<CardTitle class="text-lg flex items-center gap-2">
								<User class="h-5 w-5 text-muted-foreground" />
								<span>{record.firstname || 'N/A'} {record.lastname || 'N/A'}</span>
							</CardTitle>
						</CardHeader>
						{#if showCartButton && record.source_table && hasValidPrice(record.source_table)}
							<Tooltip.Provider>
								<Tooltip.Root>
									<Tooltip.Trigger asChild>
										<Button
											variant="ghost"
											size="icon"
											class="absolute top-3 right-3"
											disabled={isInCart(record.ssn) || processingSSNs.has(record.ssn)}
											onclick={() => onAddToCart?.(record)}
										>
											{#if processingSSNs.has(record.ssn)}
												<Loader2 class="h-4 w-4 animate-spin" />
											{:else if isInCart(record.ssn)}
												<Check class="h-4 w-4" />
											{:else}
												<ShoppingCart class="h-4 w-4" />
											{/if}
										</Button>
									</Tooltip.Trigger>
									<Tooltip.Content>
										<p>
											{isInCart(record.ssn)
												? $t('search.cart.inCart')
												: $t('search.cart.add')}
										</p>
									</Tooltip.Content>
								</Tooltip.Root>
							</Tooltip.Provider>
						{/if}
						<CardContent class="space-y-3">
							<!-- SSN -->
							<div class="flex items-center gap-2 text-sm">
								<CreditCard class="h-4 w-4 text-muted-foreground flex-shrink-0" />
								<span class="font-medium text-muted-foreground min-w-[80px]">SSN:</span>
								<span class="font-mono font-semibold">{maskSSN(record.ssn)}</span>
							</div>

							<!-- Email Count -->
							{#if record.email_count !== undefined}
								<div class="flex items-center gap-2 text-sm">
									<Mail class="h-4 w-4 text-muted-foreground flex-shrink-0" />
									<span class="font-medium text-muted-foreground min-w-[80px]">Emails:</span>
									<span>{record.email_count}</span>
								</div>
							{/if}

							<!-- Phone Count -->
							{#if record.phone_count !== undefined}
								<div class="flex items-center gap-2 text-sm">
									<Phone class="h-4 w-4 text-muted-foreground flex-shrink-0" />
									<span class="font-medium text-muted-foreground min-w-[80px]">Телефоны:</span>
									<span>{record.phone_count}</span>
								</div>
							{/if}

							<!-- Address -->
							{#if record.address}
								<div class="flex items-start gap-2 text-sm">
									<MapPin class="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />
									<span class="font-medium text-muted-foreground min-w-[80px]">Адрес:</span>
									<span class="flex-1">{record.address}</span>
								</div>
							{/if}

							<!-- City -->
							{#if record.city}
								<div class="flex items-center gap-2 text-sm">
									<MapPin class="h-4 w-4 text-muted-foreground flex-shrink-0" />
									<span class="font-medium text-muted-foreground min-w-[80px]">Город:</span>
									<span>{record.city}</span>
								</div>
							{/if}

							<!-- State -->
							{#if record.state}
								<div class="flex items-center gap-2 text-sm">
									<MapPin class="h-4 w-4 text-muted-foreground flex-shrink-0" />
									<span class="font-medium text-muted-foreground min-w-[80px]">Штат:</span>
									<span>{record.state}</span>
								</div>
							{/if}

							<!-- ZIP -->
							{#if record.zip}
								<div class="flex items-center gap-2 text-sm">
									<MapPin class="h-4 w-4 text-muted-foreground flex-shrink-0" />
									<span class="font-medium text-muted-foreground min-w-[80px]">ZIP:</span>
									<span class="font-mono">{record.zip}</span>
								</div>
							{/if}

							<!-- Date of Birth -->
							{#if record.dob}
								<div class="flex items-center gap-2 text-sm">
									<Calendar class="h-4 w-4 text-muted-foreground flex-shrink-0" />
									<span class="font-medium text-muted-foreground min-w-[80px]">Дата рожд.:</span>
									<span>{maskDOB(record.dob)}</span>
								</div>
							{/if}
						</CardContent>
					</Card>
				{/each}
			</div>
		</div>
	{/if}
</div>
