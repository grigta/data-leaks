<script lang="ts">
	import { onMount } from 'svelte';
	import { getOrders, getOrderDetails, getTestSearchHistory, type OrderSummary, type OrderDetailResponse, type OrderItemResponse, type SSNRecord, type TestSearchHistoryItem } from '$lib/api/client';
	import { formatCurrency, formatDate, maskSSN, getStatusBadgeClass, formatDOBISO, formatSSN, formatPhone, formatDOB } from '$lib/utils';
	import { dateFormat } from '$lib/stores/dateFormat';
	import { markOrdersAsViewed } from '$lib/stores/orders';
	import { t } from '$lib/i18n';
	import { ORDERS_PAGE_SIZE, ORDERS_FETCH_LIMIT, ORDERS_EXPORT_PAGE_SIZE } from '$lib/types/orders';

	// Components
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { TooltipProvider } from '$lib/components/ui/tooltip';

	// Icons (deep imports)
	import Download from '@lucide/svelte/icons/download';
	import ShoppingBag from '@lucide/svelte/icons/shopping-bag';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import X from '@lucide/svelte/icons/x';

	// State
	let orders = $state<OrderSummary[]>([]);
	let isLoading = $state(true);
	let selectedStatus = $state<string>('all');
	let currentPage = $state(0);
	let pageSize = $state(ORDERS_PAGE_SIZE); // Показывать 50 товаров на странице
	let expandedOrderId = $state<string | null>(null);
	let expandedItems = $state<Set<string>>(new Set()); // Track expanded items within orders
	let orderDetails = $state<Map<string, OrderDetailResponse>>(new Map());
	let loadingDetails = $state<Set<string>>(new Set());
	let errorMessage = $state('');
	let selectedOrderIds = $state<Set<string>>(new Set());
	let copyingItemIds = $state<Set<string>>(new Set()); // Track items being copied
	let copiedItemIds = $state<Set<string>>(new Set()); // Track successfully copied items
	let copiedCell = $state<string | null>(null); // Track which cell shows "Copied"
	let showCopyTooltip = $state(false); // Show tooltip on right-click row copy

	// Search history items (from test_search_history table)
	let searchHistoryItems = $state<TestSearchHistoryItem[]>([]);

	// Derived values
	let filteredOrders = $derived(
		selectedStatus === 'all' ? orders : orders.filter((o) => o.status === selectedStatus)
	);

	// Flatten all items from all orders
	let allItems = $derived(flattenAllItems());

	// Paginate items instead of orders
	let paginatedItems = $derived(
		allItems.slice(currentPage * pageSize, (currentPage + 1) * pageSize)
	);

	let totalPages = $derived(Math.ceil(allItems.length / pageSize));

	// Compute set of visible order IDs (only those with loaded details)
	let visibleOrderIds = $derived(new Set(allItems.map(item => item.order_id)));

	// Derived state for "select all" checkbox (based on visible orders only)
	let isAllSelected = $derived(visibleOrderIds.size > 0 && selectedOrderIds.size === visibleOrderIds.size);
	let isSomeSelected = $derived(selectedOrderIds.size > 0 && selectedOrderIds.size < visibleOrderIds.size);

	// Lifecycle
	onMount(async () => {
		await Promise.all([loadOrders(), loadSearchHistory()]);
		// Mark all orders as viewed when page loads
		await markOrdersAsViewed();
	});

	async function loadSearchHistory() {
		try {
			const data = await getTestSearchHistory();
			searchHistoryItems = data.history.filter(h => h.found);
		} catch (err) {
			console.error('Failed to load search history:', err);
		}
	}

	// Types for flattened items
	interface FlattenedItem extends OrderItemResponse {
		order_id: string;
		order_date: string;
		order_status: string;
		product_type: string;
		enrichment_attempted?: boolean;
		enrichment_success?: boolean;
		enrichment_cost?: string;
		enrichment_timestamp?: string;
	}

	// Helper Functions
	function extractTableName(ssn_record_id: string): string {
		// Extract table name from format "table_name:ssn"
		if (!ssn_record_id || typeof ssn_record_id !== 'string') {
			return '';
		}
		const parts = ssn_record_id.split(':');
		return parts[0] || '';
	}

	function getProductTypeLabel(tableName: string): string {
		// Map table name to translated product type label with alternative identifiers
		// Handles all order types: instant_ssn, manual_ssn, and reverse_ssn (deprecated but displayed for historical orders)
		const lowerName = tableName.toLowerCase();

		if (lowerName === 'ssn_1' || lowerName === 'instant_ssn' || lowerName === 'instant') {
			return $t('orders.productTypes.instantSSN');
		} else if (lowerName === 'ssn_2' || lowerName === 'reverse_ssn' || lowerName === 'reverse') {
			// Note: reverse_ssn is deprecated but still displayed for historical orders
			return $t('orders.productTypes.reverseSSN');
		} else if (lowerName === 'manual_ssn' || lowerName === 'manual') {
			// Manual SSN orders (from tickets system)
			return $t('orders.productTypes.manualSSN');
		}

		// Human-readable fallback: capitalize first letter
		return tableName.charAt(0).toUpperCase() + tableName.slice(1).replace(/_/g, ' ');
	}

	function groupItemsByProductType(items: OrderItemResponse[]): Map<string, OrderItemResponse[]> {
		// Group items by their table name (product type)
		const grouped = new Map<string, OrderItemResponse[]>();

		items.forEach((item) => {
			const tableName = extractTableName(item.ssn_record_id);
			if (!grouped.has(tableName)) {
				grouped.set(tableName, []);
			}
			grouped.get(tableName)?.push(item);
		});

		return grouped;
	}


	function formatFullAddress(details: SSNRecord): string {
		// Combine address components into single string
		const parts = [
			details.address,
			details.city,
			details.state,
			details.zip
		].filter(p => p && p.trim());

		return parts.join(', ') || '-';
	}

	function formatFullAddressFromItem(item: OrderItemResponse): string {
		// Try to get address from item first (enrichment data), fallback to ssn_details (old DB data)
		const address = item.address || item.ssn_details?.address;
		const city = item.city || item.ssn_details?.city;
		const state = item.state || item.ssn_details?.state;
		const zip = item.zip || item.ssn_details?.zip;

		const parts = [address, city, state, zip].filter(p => p && p.trim());
		return parts.join(', ') || '-';
	}

	function formatRecordForCopy(item: OrderItemResponse): string {
		const firstname = item.firstname || item.ssn_details?.firstname || '';
		const middlename = item.middlename || item.ssn_details?.middlename || '';
		const lastname = item.lastname || item.ssn_details?.lastname || '';
		const rawDob = item.dob || item.ssn_details?.dob || '';
		const dob = rawDob ? formatDOB(rawDob, $dateFormat) : '';
		const address = formatFullAddressFromItem(item);
		const ssn = item.ssn ? formatSSN(item.ssn) : '';
		const fullname = [firstname, middlename, lastname].filter(Boolean).join(' ');

		return [fullname, address, ssn, dob].filter(Boolean).join('\n');
	}

	function csvEscape(value: string): string {
		// Escape CSV field by wrapping in double quotes and escaping internal quotes
		const escaped = value.replace(/"/g, '""');
		return `"${escaped}"`;
	}

	function flattenAllItems(): FlattenedItem[] {
		// Flatten all orders and their details into a single array of items
		const flattened: FlattenedItem[] = [];

		// Add search history items first (most recent first)
		for (const h of searchHistoryItems) {
			const flatItem: FlattenedItem = {
				ssn_record_id: `history:${h.id}`,
				ssn: h.ssn,
				price: '0',
				firstname: h.result_fullname || h.input_fullname,
				lastname: '',
				middlename: '',
				address: h.result_address || h.input_address,
				city: '',
				state: '',
				zip: '',
				dob: h.dob || '',
				email: '',
				phone: '',
				order_id: `search-${h.id}`,
				order_date: h.created_at,
				order_status: 'completed',
				product_type: 'Search'
			};
			flattened.push(flatItem);
		}

		// Add order items
		for (const order of orders) {
			const details = orderDetails.get(order.id);
			if (!details) continue;

			for (const item of details.items) {
				const tableName = extractTableName(item.ssn_record_id);
				const flatItem: FlattenedItem = {
					...item,
					order_id: order.id,
					order_date: order.created_at,
					order_status: order.status,
					product_type: getProductTypeLabel(tableName)
				};
				flattened.push(flatItem);
			}
		}

		return flattened;
	}

	// Functions
	async function loadOrders() {
		try {
			isLoading = true;
			errorMessage = '';
			const status = selectedStatus === 'all' ? undefined : selectedStatus;
			orders = await getOrders(status, ORDERS_FETCH_LIMIT, 0);

			// Автоматически загружать детали всех заказов
			await loadAllOrderDetails();
		} catch (error) {
			console.error('Failed to load orders:', error);
			errorMessage = $t('orders.messages.loadFailed');
		} finally {
			isLoading = false;
		}
	}

	async function loadAllOrderDetails() {
		// Загрузить детали только для заказов, которых еще нет в кеше
		const ordersToFetch = orders.filter(order => !orderDetails.has(order.id));

		if (ordersToFetch.length === 0) {
			// Все детали уже в кеше
			return;
		}

		const detailsPromises = ordersToFetch.map(order =>
			getOrderDetails(order.id).catch(error => {
				console.error(`Failed to fetch details for order ${order.id}:`, error);
				return null;
			})
		);

		const detailsResults = await Promise.all(detailsPromises);

		// Update cache with fetched details
		const newDetailsMap = new Map(orderDetails);
		ordersToFetch.forEach((order, index) => {
			if (detailsResults[index]) {
				newDetailsMap.set(order.id, detailsResults[index]!);
			}
		});
		orderDetails = newDetailsMap;
	}

	async function fetchAllOrders(status?: string): Promise<OrderSummary[]> {
		// Paginate through API to fetch all orders
		const pageSize = ORDERS_EXPORT_PAGE_SIZE;
		let offset = 0;
		let allOrders: OrderSummary[] = [];
		let hasMore = true;

		while (hasMore) {
			try {
				const batch = await getOrders(status, pageSize, offset);
				if (batch.length === 0) {
					hasMore = false;
				} else {
					allOrders = [...allOrders, ...batch];
					offset += batch.length;
					// If we got fewer results than page size, we've reached the end
					if (batch.length < pageSize) {
						hasMore = false;
					}
				}
			} catch (error) {
				console.error(`Failed to fetch orders at offset ${offset}:`, error);
				hasMore = false;
			}
		}

		return allOrders;
	}

	async function handleRefresh() {
		await loadOrders();
	}

	async function handleStatusFilter(value: string) {
		selectedOrderIds = new Set();
		selectedStatus = value;
		currentPage = 0;
		await loadOrders();
	}

	async function handleToggleExpand(order_id: string) {
		if (expandedOrderId === order_id) {
			expandedOrderId = null;
			return;
		}

		expandedOrderId = order_id;

		// Load order details if not cached
		if (!orderDetails.has(order_id)) {
			try {
				loadingDetails = new Set(loadingDetails).add(order_id);

				const details = await getOrderDetails(order_id);
				orderDetails = new Map(orderDetails).set(order_id, details);
			} catch (error) {
				console.error('Failed to load order details:', error);
				errorMessage = $t('orders.messages.detailsFailed');
			} finally {
				const newSet = new Set(loadingDetails);
				newSet.delete(order_id);
				loadingDetails = newSet;
			}
		}
	}

	function formatItemBlock(item: OrderItemResponse): string {
		const firstname = item.firstname || item.ssn_details?.firstname || '';
		const middlename = item.middlename || item.ssn_details?.middlename || '';
		const lastname = item.lastname || item.ssn_details?.lastname || '';
		const fullname = [firstname, middlename, lastname].filter(Boolean).join(' ');
		const address = formatFullAddressFromItem(item);
		const ssn = item.ssn ? formatSSN(item.ssn) : '';
		const rawDob = item.dob || item.ssn_details?.dob || '';
		const dob = rawDob ? formatDOB(rawDob, $dateFormat) : '';
		return `${fullname}\n${address}\n${ssn}\n${dob}`;
	}

	async function handleExport() {
		try {
			const status = selectedStatus === 'all' ? undefined : selectedStatus;
			const allOrders = await fetchAllOrders(status);
			const ordersToExport = selectedOrderIds.size > 0
				? allOrders.filter(o => selectedOrderIds.has(o.id))
				: allOrders;

			await fetchMissingDetails(ordersToExport);

			// Build CSV: 1 cell per fullz (block inside cell)
			const blocks: string[] = [];
			for (const order of ordersToExport) {
				const details = orderDetails.get(order.id);
				if (!details) continue;
				for (const item of details.items) {
					blocks.push(formatItemBlock(item));
				}
			}

			const csvContent = '\uFEFF' + blocks.map(b => csvEscape(b)).join('\n');

			const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			const ts = new Date().toISOString().replace(/:/g, '-');
			a.download = `orders-${ts}.csv`;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
		} catch (error) {
			console.error('Failed to export orders:', error);
			errorMessage = $t('orders.messages.exportFailed');
		}
	}

	async function fetchMissingDetails(ordersToExport: OrderSummary[]) {
		const ordersNeedingDetails = ordersToExport.filter(o => !orderDetails.has(o.id));
		if (ordersNeedingDetails.length === 0) return;

		const detailsPromises = ordersNeedingDetails.map(order =>
			getOrderDetails(order.id).catch(error => {
				console.error(`Failed to fetch details for order ${order.id}:`, error);
				return null;
			})
		);
		const detailsResults = await Promise.all(detailsPromises);
		const newDetailsMap = new Map(orderDetails);
		ordersNeedingDetails.forEach((order, index) => {
			if (detailsResults[index]) {
				newDetailsMap.set(order.id, detailsResults[index]!);
			}
		});
		orderDetails = newDetailsMap;
	}

	async function handleExportTxt() {
		try {
			const status = selectedStatus === 'all' ? undefined : selectedStatus;
			const allOrders = await fetchAllOrders(status);
			const ordersToExport = selectedOrderIds.size > 0
				? allOrders.filter(o => selectedOrderIds.has(o.id))
				: allOrders;

			await fetchMissingDetails(ordersToExport);

			const blocks: string[] = [];
			for (const order of ordersToExport) {
				const details = orderDetails.get(order.id);
				if (!details) continue;
				for (const item of details.items) {
					blocks.push(formatItemBlock(item));
				}
			}

			const txtContent = blocks.join('\n\n') + '\n';

			const blob = new Blob([txtContent], { type: 'text/plain' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			const ts = new Date().toISOString().replace(/:/g, '-');
			a.download = `orders-${ts}.txt`;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
		} catch (error) {
			console.error('Failed to export orders:', error);
			errorMessage = $t('orders.messages.exportFailed');
		}
	}

	function goToPage(page: number) {
		if (page >= 0 && page < totalPages) {
			currentPage = page;
		}
	}

	function getStatusIcon(status: string) {
		switch (status.toLowerCase()) {
			case 'pending':
				return Clock;
			case 'completed':
				return CheckCircle;
			case 'failed':
				return XCircle;
			case 'cancelled':
				return Ban;
			default:
				return null;
		}
	}

	function handleSelectOrder(orderId: string, checked: boolean) {
		const newSet = new Set(selectedOrderIds);
		if (checked === true) {
			newSet.add(orderId);
		} else {
			newSet.delete(orderId);
		}
		selectedOrderIds = newSet;
	}

	function handleSelectAll(checked: boolean) {
		const newSet = new Set(selectedOrderIds);
		if (checked === true) {
			// Select only visible orders (those with loaded details)
			visibleOrderIds.forEach((orderId) => newSet.add(orderId));
		} else {
			// Deselect only visible orders
			visibleOrderIds.forEach((orderId) => newSet.delete(orderId));
		}
		selectedOrderIds = newSet;
	}

	function handleClearSelection() {
		selectedOrderIds = new Set();
	}

	function toggleItemExpand(orderId: string, itemIndex: number) {
		const key = `${orderId}-${itemIndex}`;
		const newSet = new Set(expandedItems);
		if (newSet.has(key)) {
			newSet.delete(key);
		} else {
			newSet.add(key);
		}
		expandedItems = newSet;
	}

	function isItemExpanded(orderId: string, itemIndex: number): boolean {
		return expandedItems.has(`${orderId}-${itemIndex}`);
	}

	async function handleCopyRecord(itemKey: string, item: OrderItemResponse) {
		try {
			// Set loading state
			copyingItemIds = new Set(copyingItemIds).add(itemKey);

			// Format and copy to clipboard
			const textToCopy = formatRecordForCopy(item);
			await navigator.clipboard.writeText(textToCopy);

			// Show tooltip
			showCopyTooltip = true;
			setTimeout(() => { showCopyTooltip = false; }, 1500);

			// Set success state
			copiedItemIds = new Set(copiedItemIds).add(itemKey);

			// Remove success indicator after 2 seconds
			setTimeout(() => {
				const newSet = new Set(copiedItemIds);
				newSet.delete(itemKey);
				copiedItemIds = newSet;
			}, 2000);
		} catch (error) {
			console.error('Failed to copy:', error);
			errorMessage = $t('orders.messages.copyFailed');
		} finally {
			// Remove loading state
			const newSet = new Set(copyingItemIds);
			newSet.delete(itemKey);
			copyingItemIds = newSet;
		}
	}

	async function copyCellValue(value: string, cellKey: string) {
		if (value === '-') return;
		try {
			await navigator.clipboard.writeText(value);
			copiedCell = cellKey;
			setTimeout(() => {
				if (copiedCell === cellKey) copiedCell = null;
			}, 1000);
		} catch (error) {
			console.error('Failed to copy cell value:', error);
		}
	}

	function formatRowForCopy(item: FlattenedItem): string {
		const firstname = item.firstname || item.ssn_details?.firstname || '';
		const middlename = item.middlename || item.ssn_details?.middlename || '';
		const lastname = item.lastname || item.ssn_details?.lastname || '';
		const dob = item.dob ? formatDOB(item.dob, $dateFormat) : item.ssn_details?.dob ? formatDOB(item.ssn_details.dob, $dateFormat) : '';
		const address = formatFullAddressFromItem(item);
		const ssn = item.ssn ? formatSSN(item.ssn) : '';
		const fullname = [firstname, middlename, lastname].filter(Boolean).join(' ');
		return [fullname, address, ssn, dob].filter(Boolean).join('\n');
	}

	async function handleRowRightClick(e: MouseEvent, item: FlattenedItem) {
		e.preventDefault();
		const text = formatRowForCopy(item);
		if (!text) return;
		try {
			await navigator.clipboard.writeText(text);
			showCopyTooltip = true;
			setTimeout(() => { showCopyTooltip = false; }, 1500);
		} catch (error) {
			console.error('Failed to copy row:', error);
		}
	}
</script>

<TooltipProvider>
<div class="w-full space-y-6 p-6 pt-2">
	<!-- Copy Tooltip (right-click) -->
	{#if showCopyTooltip}
		<div class="fixed top-16 right-4 z-50 bg-primary text-primary-foreground px-4 py-2 rounded-lg shadow-lg text-sm font-medium animate-tooltip-fade">
			Row copied to clipboard
		</div>
	{/if}

	<!-- Page Title -->
	<div class="flex items-center justify-center">
		<h1 class="text-3xl font-bold">{$t('orders.title')}</h1>
	</div>

		<!-- Actions Bar -->
		<div class="flex flex-wrap items-center justify-center gap-4 mt-4">
			<!-- Export Button -->
			<Button variant="outline" onclick={handleExport} disabled={orders.length === 0}>
				<Download class="mr-2 h-4 w-4" />
				{$t('orders.actions.exportCSV')}
			</Button>

			<!-- Export TXT Button -->
			<Button variant="outline" onclick={handleExportTxt} disabled={orders.length === 0}>
				<Download class="mr-2 h-4 w-4" />
				{$t('orders.actions.exportTXT')}
			</Button>
		</div>

		<!-- Selection Banner -->
		{#if selectedOrderIds.size > 0}
			<Alert variant="default" class="flex items-center justify-between">
				<AlertDescription class="flex-1">
					{$t('orders.selection.ordersSelected').replace('{{count}}', String(selectedOrderIds.size))}
				</AlertDescription>
				<Button variant="outline" size="sm" onclick={handleClearSelection}>
					<X class="mr-2 h-4 w-4" />
					{$t('orders.selection.clearSelection')}
				</Button>
			</Alert>
		{/if}

		<!-- Error Alert -->
		{#if errorMessage}
			<Alert variant="destructive">
				<AlertDescription>{errorMessage}</AlertDescription>
			</Alert>
		{/if}

		<!-- Loading State -->
		{#if isLoading}
			<div class="space-y-2">
				{#each Array(10) as _}
					<Skeleton class="h-16 w-full" />
				{/each}
			</div>
		{:else if orders.length === 0 && searchHistoryItems.length === 0}
			<!-- Empty State -->
			<Card>
				<CardContent class="flex flex-col items-center justify-center py-12">
					<ShoppingBag class="mb-4 h-16 w-16 text-gray-400" />
					<h2 class="mb-2 text-xl font-semibold">{$t('orders.empty.title')}</h2>
					<p class="mb-4 text-gray-500">{$t('orders.empty.subtitle')}</p>
				</CardContent>
			</Card>
		{:else}
			<!-- Flat Items Table -->
			<Card class="mx-auto max-w-5xl">
				<CardContent class="p-0">
					<div class="w-full">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead class="w-12 text-center">
										<Checkbox
											checked={isAllSelected}
											indeterminate={isSomeSelected}
											onCheckedChange={(checked) => handleSelectAll(checked === true)}
											aria-label={$t('orders.table.selectAll')}
										/>
									</TableHead>
									<TableHead class="w-12 text-center"></TableHead>
									<TableHead class="text-center">Full Name</TableHead>
									<TableHead class="text-center">Full Address</TableHead>
									<TableHead class="text-center">SSN</TableHead>
									<TableHead class="text-center">DOB</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each paginatedItems as item, index (item.order_id + '-' + index)}
									{@const itemKey = `${item.order_id}-${index}`}
									{@const isCopying = copyingItemIds.has(itemKey)}
									{@const isCopied = copiedItemIds.has(itemKey)}
									{@const firstname = item.firstname || item.ssn_details?.firstname || ''}
									{@const middlename = item.middlename || item.ssn_details?.middlename || ''}
									{@const lastname = item.lastname || item.ssn_details?.lastname || ''}
									{@const fullName = [firstname, middlename, lastname].filter(Boolean).join(' ') || '-'}
									{@const fullAddress = formatFullAddressFromItem(item)}
									{@const dob = item.dob ? formatDOB(item.dob, $dateFormat) : item.ssn_details?.dob ? formatDOB(item.ssn_details.dob, $dateFormat) : '-'}
									<TableRow oncontextmenu={(e) => handleRowRightClick(e, item)}>
										<TableCell class="w-12 text-center">
											<Checkbox
												checked={selectedOrderIds.has(item.order_id)}
												onCheckedChange={(checked) => handleSelectOrder(item.order_id, checked === true)}
												aria-label="Select order"
											/>
										</TableCell>
										<!-- Copy Button -->
										<TableCell class="text-center">
											<Button
												variant="ghost"
												size="sm"
												onclick={() => handleCopyRecord(itemKey, item)}
												disabled={isCopying}
												class="h-8 w-8 p-0 mx-auto"
											>
												{#if isCopying}
													<Loader2 class="h-4 w-4 animate-spin" />
												{:else if isCopied}
													<Check class="h-4 w-4 text-primary" />
												{:else}
													<Copy class="h-4 w-4" />
												{/if}
											</Button>
										</TableCell>
										<!-- Full Name -->
										<TableCell
											class="cursor-pointer text-center text-sm transition-all duration-150"
											onclick={() => copyCellValue(fullName, `${itemKey}-name`)}
										>
											{copiedCell === `${itemKey}-name` ? 'Copied' : fullName}
										</TableCell>
										<!-- Full Address -->
										<TableCell
											class="cursor-pointer text-center text-sm transition-all duration-150"
											onclick={() => copyCellValue(fullAddress, `${itemKey}-address`)}
										>
											{copiedCell === `${itemKey}-address` ? 'Copied' : fullAddress}
										</TableCell>
										<!-- SSN -->
										<TableCell
											class="cursor-pointer text-center transition-all duration-150"
											onclick={() => copyCellValue(formatSSN(item.ssn), `${itemKey}-ssn`)}
										>
											{#if copiedCell === `${itemKey}-ssn`}
												<span class="text-sm">Copied</span>
											{:else}
												<code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{formatSSN(item.ssn)}</code>
											{/if}
										</TableCell>
										<!-- DOB -->
										<TableCell
											class="cursor-pointer text-center text-sm transition-all duration-150"
											onclick={() => copyCellValue(dob, `${itemKey}-dob`)}
										>
											{copiedCell === `${itemKey}-dob` ? 'Copied' : dob}
										</TableCell>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					</div>
				</CardContent>
			</Card>

			<!-- Pagination & Total -->
			{#if allItems.length > 0}
				<div class="flex items-center justify-between">
					<div class="text-sm text-muted-foreground">
						{#if totalPages > 1}
							{$t('orders.pagination.page', { current: currentPage + 1, total: totalPages })}
						{/if}
					</div>
					<div class="text-sm text-muted-foreground">
						{$t('orders.pagination.totalRecords', { count: allItems.length })}
					</div>
					{#if totalPages > 1}
						<div class="flex gap-2">
							<Button variant="outline" onclick={() => goToPage(currentPage - 1)} disabled={currentPage === 0}>
								{$t('orders.pagination.previous')}
							</Button>
							<Button
								variant="outline"
								onclick={() => goToPage(currentPage + 1)}
								disabled={currentPage >= totalPages - 1}
							>
								{$t('orders.pagination.next')}
							</Button>
						</div>
					{/if}
				</div>
			{/if}
		{/if}
	</div>
</TooltipProvider>

<style>
	@keyframes tooltip-fade {
		0% {
			opacity: 0;
			transform: translateY(-8px);
		}
		15% {
			opacity: 1;
			transform: translateY(0);
		}
		85% {
			opacity: 1;
			transform: translateY(0);
		}
		100% {
			opacity: 0;
			transform: translateY(-8px);
		}
	}

	:global(.animate-tooltip-fade) {
		animation: tooltip-fade 1.5s ease-in-out;
	}
</style>
