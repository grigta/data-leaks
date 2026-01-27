<script lang="ts">
	import type { SSNRecord, EnrichRecordResponse } from '$lib/api/client';
	import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '$lib/components/ui/table';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import {
		Pagination,
		PaginationContent,
		PaginationItem,
		PaginationPrevButton,
		PaginationNextButton
	} from '$lib/components/ui/pagination';
	import * as Tooltip from '$lib/components/ui/tooltip';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Mail from '@lucide/svelte/icons/mail';
	import Phone from '@lucide/svelte/icons/phone';
	import MapPin from '@lucide/svelte/icons/map-pin';
	import Plus from '@lucide/svelte/icons/plus';
	import Check from '@lucide/svelte/icons/check';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import ShoppingCart from '@lucide/svelte/icons/shopping-cart';
	import DollarSign from '@lucide/svelte/icons/dollar-sign';
	import { maskSSN, formatDate, formatCurrency, truncate, maskDOB } from '$lib/utils';
	import { userBalance, refreshUser } from '$lib/stores/auth';
	import { instantPurchaseWithEnrichment, handleApiError } from '$lib/api/client';
	import { loadUnviewedOrdersCount } from '$lib/stores/orders';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import { ENRICHMENT_FAILURE_COST } from '$lib/constants/pricing';

	// Extended type to include optional fields returned by search API
	type ExtendedSSNRecord = SSNRecord & { middlename?: string; price?: number };

	let {
		results = [],
		loading = false,
		showAddToCart = false,
		onAddToCart = undefined,
		processingSSNs = new Set(),
		defaultPrice = 1.50
	}: {
		results?: ExtendedSSNRecord[],
		loading?: boolean,
		showAddToCart?: boolean,
		onAddToCart?: ((record: ExtendedSSNRecord) => void) | undefined,
		processingSSNs?: Set<string>,
		defaultPrice?: number
	} = $props();

	let expandedRows: Set<number> = $state(new Set());
	let page: number = $state(1); // bits-ui uses 1-indexed pages
	const pageSize: number = 10;
	let purchasingSSNs = $state(new Set<string>());
	let addingToCartSSNs = $state(new Set<string>());
	let purchaseSuccessMessage = $state('');
	let purchaseErrorMessage = $state('');
	let cartSuccessMessage = $state('');
	let cartErrorMessage = $state('');

	// Store refs for truncation detection
	let truncationRefs = new Map<string, HTMLElement>();

	// Svelte action for setting refs
	function trackRef(node: HTMLElement, key: string) {
		truncationRefs.set(key, node);
		return {
			destroy() {
				truncationRefs.delete(key);
			}
		};
	}

	// Convert 1-indexed page to 0-indexed for slicing
	let currentPage = $derived(page - 1);
	let paginatedResults = $derived(results.slice(currentPage * pageSize, (currentPage + 1) * pageSize));
	let totalPages = $derived(Math.ceil(results.length / pageSize));
	// Calculate total columns for colspan (10 base columns + 1 if showAddToCart)
	let totalColumns = $derived(showAddToCart ? 11 : 10);

	function toggleRow(id: number) {
		const newSet = new Set(expandedRows);
		if (newSet.has(id)) {
			newSet.delete(id);
		} else {
			newSet.add(id);
		}
		expandedRows = newSet;
	}

	function isExpanded(id: number): boolean {
		return expandedRows.has(id);
	}

	// Reset or clamp page when results change
	$effect(() => {
		if (results.length === 0) {
			page = 1;
		} else if (totalPages > 0 && page > totalPages) {
			page = Math.max(1, totalPages);
		}
	});

	async function handleAddToCart(record: ExtendedSSNRecord) {
		// Cart functionality removed
		console.log('[Cart] Cart functionality has been removed');
	}

	function isInCart(ssn: string): boolean {
		// Cart functionality removed
		return false;
	}

	function getSourceBadgeClass(source: string): string {
		if (source === 'ssn_1') return 'badge-info';
		if (source === 'ssn_2') return 'badge-success';
		return '';
	}

	function isTruncated(key: string): boolean {
		const el = truncationRefs.get(key);
		return !!(el && el.scrollWidth > el.clientWidth);
	}

	function formatFullAddress(record: ExtendedSSNRecord): string {
		const parts = [];
		if (record.address) parts.push(record.address);
		if (record.city) parts.push(record.city);
		if (record.state) parts.push(record.state);
		if (record.zip) parts.push(record.zip);
		return parts.join(', ') || '-';
	}

	async function handleInstantPurchase(record: ExtendedSSNRecord) {
		// Clear messages
		purchaseSuccessMessage = '';
		purchaseErrorMessage = '';

		// Validate source_table
		if (!record.source_table) {
			purchaseErrorMessage = 'Cannot purchase: source table is missing';
			return;
		}

		const price = record.price ?? defaultPrice;

		// Check balance (need at least price + min enrichment cost)
		const totalRequired = price + ENRICHMENT_FAILURE_COST;
		if ($userBalance < totalRequired) {
			purchaseErrorMessage = `Недостаточно средств. Требуется: ${formatCurrency(totalRequired)} (товар + актуализация), Доступно: ${formatCurrency($userBalance)}. Пожалуйста, пополните баланс.`;
			return;
		}

		// Add SSN to purchasing set
		purchasingSSNs.add(record.ssn);
		purchasingSSNs = purchasingSSNs;

		try {
			await instantPurchaseWithEnrichment(record.ssn, record.source_table);

			// Refresh user balance and unviewed orders count
			await refreshUser();
			await loadUnviewedOrdersCount();

			purchaseSuccessMessage = `Запись успешно куплена с актуализацией! Проверьте раздел "Заказы".`;

			// Auto-clear success message after 5 seconds
			setTimeout(() => {
				purchaseSuccessMessage = '';
			}, 5000);
		} catch (error: any) {
			console.error('[INSTANT PURCHASE] Error:', error);
			purchaseErrorMessage = handleApiError(error);
		} finally {
			// Remove SSN from purchasing set
			purchasingSSNs.delete(record.ssn);
			purchasingSSNs = purchasingSSNs;
		}
	}

</script>

<Tooltip.Provider>
<div class="w-full">
	{#if purchaseSuccessMessage}
		<Alert variant="default" class="mb-4">
			<AlertDescription>{purchaseSuccessMessage}</AlertDescription>
		</Alert>
	{/if}

	{#if purchaseErrorMessage}
		<Alert variant="destructive" class="mb-4">
			<AlertCircle class="h-4 w-4" />
			<AlertDescription>{purchaseErrorMessage}</AlertDescription>
		</Alert>
	{/if}

	{#if cartSuccessMessage}
		<Alert variant="default" class="mb-4">
			<AlertDescription>{cartSuccessMessage}</AlertDescription>
		</Alert>
	{/if}

	{#if cartErrorMessage}
		<Alert variant="destructive" class="mb-4">
			<AlertCircle class="h-4 w-4" />
			<AlertDescription>{cartErrorMessage}</AlertDescription>
		</Alert>
	{/if}

	{#if loading}
		<div class="rounded-md border">
			<Table role="table" class={showAddToCart ? "search-results-grid search-results-grid-with-actions" : "search-results-grid"}>
				<TableHeader role="rowgroup">
					<TableRow role="row">
						<TableHead role="columnheader"></TableHead>
						<TableHead role="columnheader">First</TableHead>
						<TableHead role="columnheader">Middle</TableHead>
						<TableHead role="columnheader">Last</TableHead>
						<TableHead role="columnheader">DOB</TableHead>
						<TableHead role="columnheader">Last 4 SSN</TableHead>
						<TableHead role="columnheader">Full Address</TableHead>
						<TableHead role="columnheader">Emails</TableHead>
						<TableHead role="columnheader">Phones</TableHead>
						<TableHead role="columnheader">Price</TableHead>
						{#if showAddToCart}
							<TableHead role="columnheader">Actions</TableHead>
						{/if}
					</TableRow>
				</TableHeader>
				<TableBody role="rowgroup">
					{#each Array(5) as _}
						<TableRow role="row">
							<TableCell role="cell"><Skeleton class="h-4 w-4" /></TableCell>
							<TableCell role="cell"><Skeleton class="h-4 w-24" /></TableCell>
							<TableCell role="cell"><Skeleton class="h-4 w-20" /></TableCell>
							<TableCell role="cell"><Skeleton class="h-4 w-24" /></TableCell>
							<TableCell role="cell"><Skeleton class="h-4 w-24" /></TableCell>
							<TableCell role="cell"><Skeleton class="h-4 w-24" /></TableCell>
							<TableCell role="cell"><Skeleton class="h-4 w-48" /></TableCell>
							<TableCell role="cell"><Skeleton class="h-4 w-32" /></TableCell>
							<TableCell role="cell"><Skeleton class="h-4 w-28" /></TableCell>
							<TableCell role="cell"><Skeleton class="h-4 w-16" /></TableCell>
							{#if showAddToCart}
								<TableCell role="cell"><Skeleton class="h-8 w-32" /></TableCell>
							{/if}
						</TableRow>
					{/each}
				</TableBody>
			</Table>
		</div>
	{:else if results.length === 0}
		<div class="rounded-md border p-8 text-center text-muted-foreground">
			Результаты не найдены
		</div>
	{:else}
		<div class="rounded-md border">
			<Table role="table" class={showAddToCart ? "search-results-grid search-results-grid-with-actions" : "search-results-grid"}>
				<TableHeader role="rowgroup">
					<TableRow role="row">
						<TableHead role="columnheader"></TableHead>
						<TableHead role="columnheader">First</TableHead>
						<TableHead role="columnheader">Middle</TableHead>
						<TableHead role="columnheader">Last</TableHead>
						<TableHead role="columnheader">DOB</TableHead>
						<TableHead role="columnheader">Last 4 SSN</TableHead>
						<TableHead role="columnheader">Full Address</TableHead>
						<TableHead role="columnheader">Emails</TableHead>
						<TableHead role="columnheader">Phones</TableHead>
						<TableHead role="columnheader">Price</TableHead>
						{#if showAddToCart}
							<TableHead role="columnheader">Actions</TableHead>
						{/if}
					</TableRow>
				</TableHeader>
				<TableBody role="rowgroup">
					{#each paginatedResults as record}
						{@const r = record as ExtendedSSNRecord}
						{@const inCart = isInCart(r.ssn)}
						{@const processing = processingSSNs.has(r.ssn)}
						{@const expanded = isExpanded(r.id)}
						<TableRow role="row" class="hover:bg-muted/50">
							<TableCell role="cell" class="p-2">
								<Button
									variant="ghost"
									size="icon"
									class="h-6 w-6 p-0"
									onclick={() => toggleRow(r.id)}
								>
									{#if expanded}
										<ChevronDown class="h-4 w-4" />
									{:else}
										<ChevronRight class="h-4 w-4" />
									{/if}
								</Button>
							</TableCell>
							<TableCell role="cell" class="text-sm" title={r.firstname || ''}>{r.firstname || '-'}</TableCell>
							<TableCell role="cell" class="text-sm" title={r.middlename || ''}>{r.middlename || '-'}</TableCell>
							<TableCell role="cell" class="text-sm" title={r.lastname || ''}>{r.lastname || '-'}</TableCell>
							<TableCell role="cell" class="text-sm">{r.dob ? r.dob.substring(0, 4) : '-'}</TableCell>
							<TableCell role="cell" class="text-sm font-mono">{r.ssn.slice(-4)}</TableCell>
							<TableCell role="cell" class="text-sm">
								{@const fullAddress = formatFullAddress(r)}
								{@const addressKey = `address-${r.id}`}
								{#if fullAddress && fullAddress !== '-'}
									{#if isTruncated(addressKey)}
										<Tooltip.Root>
											<Tooltip.Trigger asChild>
												<span use:trackRef={addressKey} class="w-full block">
													{fullAddress}
												</span>
											</Tooltip.Trigger>
											<Tooltip.Content class="max-w-xs break-words">
												{fullAddress}
											</Tooltip.Content>
										</Tooltip.Root>
									{:else}
										<span use:trackRef={addressKey} class="w-full block">
											{fullAddress}
										</span>
									{/if}
								{:else}
									{fullAddress}
								{/if}
							</TableCell>
							<TableCell role="cell" class="text-sm">
								{#if r.email_count !== undefined}
									{r.email_count}
								{:else}
									-
								{/if}
							</TableCell>
							<TableCell role="cell" class="text-sm">
								{#if r.phone_count !== undefined}
									{r.phone_count}
								{:else}
									-
								{/if}
							</TableCell>
							<TableCell role="cell" class="text-sm font-medium">
								{formatCurrency(r.price ?? defaultPrice)}
							</TableCell>
							{#if showAddToCart}
								<TableCell role="cell">
									{@const isPurchasing = purchasingSSNs.has(r.ssn)}
									{@const isAddingToCart = addingToCartSSNs.has(r.ssn)}
									<div class="flex items-center justify-center gap-1">
										<Button
											variant="ghost"
											size="icon"
											class="h-8 w-8"
											disabled={inCart || processing || isAddingToCart}
											onclick={() => handleAddToCart(r)}
											title="Добавить в корзину с актуализацией"
										>
											{#if isAddingToCart}
												<Loader2 class="h-4 w-4 animate-spin" />
											{:else if inCart}
												<Check class="h-4 w-4" />
											{:else}
												<ShoppingCart class="h-4 w-4" />
											{/if}
										</Button>
										<Button
											variant="ghost"
											size="icon"
											class="h-8 w-8"
											disabled={isPurchasing}
											onclick={() => handleInstantPurchase(r)}
											title="Мгновенная покупка с актуализацией"
										>
											{#if isPurchasing}
												<Loader2 class="h-4 w-4 animate-spin" />
											{:else}
												<DollarSign class="h-4 w-4" />
											{/if}
										</Button>
									</div>
								</TableCell>
							{/if}
						</TableRow>
						{#if expanded}
							<TableRow role="row">
								<TableCell role="cell" colspan={totalColumns} class="bg-muted/30 p-6">
									<div class="grid grid-cols-2 gap-6">
										<div class="space-y-2">
											<h4 class="font-semibold text-sm mb-3">Personal Information</h4>
											<div class="grid grid-cols-[120px_1fr] gap-2 text-sm">
												<span class="text-muted-foreground">Last 4 SSN:</span>
												<span class="font-mono">{r.ssn.slice(-4)}</span>

												<span class="text-muted-foreground">Full Name:</span>
												<span>{r.firstname} {r.middlename || ''} {r.lastname}</span>

												<span class="text-muted-foreground">Date of Birth:</span>
												<span>{r.dob ? r.dob.substring(0, 4) : '-'}</span>
											</div>
										</div>

										<div class="space-y-2">
											<h4 class="font-semibold text-sm mb-3">Contact Information</h4>
											<div class="grid grid-cols-[120px_1fr] gap-2 text-sm">
												<span class="text-muted-foreground">Email Count:</span>
												<span>{r.email_count !== undefined ? r.email_count : '-'}</span>

												<span class="text-muted-foreground">Phone Count:</span>
												<span>{r.phone_count !== undefined ? r.phone_count : '-'}</span>
											</div>
										</div>

										<div class="space-y-2">
											<h4 class="font-semibold text-sm mb-3">Address Details</h4>
											<div class="grid grid-cols-[120px_1fr] gap-2 text-sm">
												<span class="text-muted-foreground">Street:</span>
												<span>{r.address || '-'}</span>

												<span class="text-muted-foreground">City:</span>
												<span>{r.city || '-'}</span>

												<span class="text-muted-foreground">State:</span>
												<span>{r.state || '-'}</span>

												<span class="text-muted-foreground">ZIP Code:</span>
												<span>{r.zip || '-'}</span>
											</div>
										</div>
									</div>
								</TableCell>
							</TableRow>
						{/if}
					{/each}
				</TableBody>
			</Table>
		</div>

		{#if totalPages > 1}
			{@const start = currentPage * pageSize + 1}
			{@const end = Math.min((currentPage + 1) * pageSize, results.length)}
			<Pagination count={results.length} perPage={pageSize} bind:page>
				<div class="flex items-center justify-between px-2 py-4">
					<div class="text-sm text-muted-foreground">
						Showing {start}-{end} of {results.length}
					</div>
					<PaginationContent>
						<PaginationItem>
							<PaginationPrevButton />
						</PaginationItem>
						<PaginationItem>
							<PaginationNextButton />
						</PaginationItem>
					</PaginationContent>
				</div>
			</Pagination>
		{/if}
	{/if}
</div>
</Tooltip.Provider>

