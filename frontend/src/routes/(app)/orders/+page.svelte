<script lang="ts">
	import { onMount } from 'svelte';
	import { getOrders, getOrderDetails, type OrderSummary, type OrderDetailResponse, type OrderItemResponse, type SSNRecord } from '$lib/api/client';
	import { formatCurrency, formatDate, maskSSN, getStatusBadgeClass, formatDOBISO, formatSSN, formatPhone } from '$lib/utils';
	import { ORDER_STATUSES } from '$lib/constants/orderStatuses';
	import { markOrdersAsViewed } from '$lib/stores/orders';
	import { t } from '$lib/i18n';
	import type { OrderTypeFilter } from '$lib/types/orders';
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
	import * as Select from '$lib/components/ui/select';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { TooltipProvider } from '$lib/components/ui/tooltip';
	import * as Tabs from '$lib/components/ui/tabs';

	// Icons (deep imports)
	import Clock from '@lucide/svelte/icons/clock';
	import CheckCircle from '@lucide/svelte/icons/check-circle';
	import XCircle from '@lucide/svelte/icons/x-circle';
	import Ban from '@lucide/svelte/icons/ban';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import ChevronUp from '@lucide/svelte/icons/chevron-up';
	import Download from '@lucide/svelte/icons/download';
	import Filter from '@lucide/svelte/icons/filter';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import ShoppingBag from '@lucide/svelte/icons/shopping-bag';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import X from '@lucide/svelte/icons/x';

	// State
	let orders = $state<OrderSummary[]>([]);
	let isLoading = $state(true);
	let selectedStatus = $state<string>('all');
	let selectedOrderType = $state<OrderTypeFilter>('all');
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
	let copiedCells = $state<Map<string, boolean>>(new Map()); // Track copied cells for tooltip

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
		await loadOrders();
		// Mark all orders as viewed when page loads
		await markOrdersAsViewed();
	});

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
		// Format record as tab-separated values for clipboard
		if (!item.ssn_details) return '';

		const details = item.ssn_details;
		const fields = [
			details.firstname || '',
			details.middlename || '',
			details.lastname || '',
			details.dob ? formatDOBISO(details.dob) : '',
			formatFullAddress(details),
			details.email || '',
			details.phone ? formatPhone(details.phone) : '',
			item.ssn ? formatSSN(item.ssn) : ''
		];

		return fields.join('\t');
	}

	function csvEscape(value: string): string {
		// Escape CSV field by wrapping in double quotes and escaping internal quotes
		const escaped = value.replace(/"/g, '""');
		return `"${escaped}"`;
	}

	function flattenAllItems(): FlattenedItem[] {
		// Flatten all orders and their details into a single array of items
		const flattened: FlattenedItem[] = [];

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
			// Important: When selectedOrderType is 'all', we pass undefined to the API.
			// This ensures the backend returns ALL order types without filtering:
			// - instant_ssn (current)
			// - manual_ssn (current)
			// - reverse_ssn (deprecated but still present for historical orders)
			const type = selectedOrderType === 'all' ? undefined : selectedOrderType;
			orders = await getOrders(status, ORDERS_FETCH_LIMIT, 0, type);

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

	async function fetchAllOrders(status?: string, type?: OrderTypeFilter): Promise<OrderSummary[]> {
		// Paginate through API to fetch all orders
		const pageSize = ORDERS_EXPORT_PAGE_SIZE;
		let offset = 0;
		let allOrders: OrderSummary[] = [];
		let hasMore = true;

		while (hasMore) {
			try {
				const batch = await getOrders(status, pageSize, offset, type);
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

	async function handleOrderTypeChange(value: string) {
		selectedOrderIds = new Set();
		selectedOrderType = value;
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

	async function handleExport() {
		try {
			// Create CSV content with full order details
			const headers = ['Order ID', 'Product Type', 'First', 'Middle', 'Last', 'DOB', 'Full Address', 'Email', 'Phone', 'SSN', 'Price'];
			const rows: string[][] = [];

			// Fetch all orders matching current filter
			const status = selectedStatus === 'all' ? undefined : selectedStatus;
			const type = selectedOrderType === 'all' ? undefined : selectedOrderType;
			const allOrders = await fetchAllOrders(status, type);

			// Get orders to export (selected or all filtered)
			const ordersToExport = selectedOrderIds.size > 0
				? allOrders.filter(o => selectedOrderIds.has(o.id))
				: allOrders;

			// Collect orders that need details fetched
			const ordersNeedingDetails = ordersToExport.filter(o => !orderDetails.has(o.id));

			// Fetch all missing details in parallel
			if (ordersNeedingDetails.length > 0) {
				const detailsPromises = ordersNeedingDetails.map(order =>
					getOrderDetails(order.id).catch(error => {
						console.error(`Failed to fetch details for order ${order.id}:`, error);
						return null;
					})
				);

				const detailsResults = await Promise.all(detailsPromises);

				// Update cache with fetched details
				const newDetailsMap = new Map(orderDetails);
				ordersNeedingDetails.forEach((order, index) => {
					if (detailsResults[index]) {
						newDetailsMap.set(order.id, detailsResults[index]!);
					}
				});
				orderDetails = newDetailsMap;
			}

			// Build rows from cached details
			for (const order of ordersToExport) {
				const details = orderDetails.get(order.id);
				if (!details) continue;

				// Group items by product type
				const groupedItems = groupItemsByProductType(details.items);

				// Add rows for each item
				for (const [tableName, items] of groupedItems.entries()) {
					const productType = getProductTypeLabel(tableName);

					for (const item of items) {
						if (!item.ssn_details) continue;

						const row = [
							order.id,
							productType,
							item.ssn_details.firstname || '',
							item.ssn_details.middlename || '',
							item.ssn_details.lastname || '',
							item.ssn_details.dob ? formatDOBISO(item.ssn_details.dob) : '',
							formatFullAddress(item.ssn_details),
							item.ssn_details.email || '',
							item.ssn_details.phone || '',
							item.ssn ? formatSSN(item.ssn) : '',
							item.price.toString()
						];

						rows.push(row);
					}
				}
			}

			// Escape all fields and create CSV content with BOM
			const csvContent = '\uFEFF' + [headers, ...rows].map((row) => row.map(csvEscape).join(',')).join('\n');

			// Create blob and download
			const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			const ts = new Date().toISOString().replace(/:/g, '-');
			a.download = `orders-details-${ts}.csv`;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
		} catch (error) {
			console.error('Failed to export orders:', error);
			errorMessage = $t('orders.messages.exportFailed');
		}
	}

	async function handleExportTxt() {
		try {
			// Create TXT content with full order details
			let txtContent = 'ORDERS DETAILS\n\n';
			txtContent += '='.repeat(140) + '\n\n';

			// Fetch all orders matching current filter
			const status = selectedStatus === 'all' ? undefined : selectedStatus;
			const type = selectedOrderType === 'all' ? undefined : selectedOrderType;
			const allOrders = await fetchAllOrders(status, type);

			// Get orders to export (selected or all filtered)
			const ordersToExport = selectedOrderIds.size > 0
				? allOrders.filter(o => selectedOrderIds.has(o.id))
				: allOrders;

			// Collect orders that need details fetched
			const ordersNeedingDetails = ordersToExport.filter(o => !orderDetails.has(o.id));

			// Fetch all missing details in parallel
			if (ordersNeedingDetails.length > 0) {
				const detailsPromises = ordersNeedingDetails.map(order =>
					getOrderDetails(order.id).catch(error => {
						console.error(`Failed to fetch details for order ${order.id}:`, error);
						return null;
					})
				);

				const detailsResults = await Promise.all(detailsPromises);

				// Update cache with fetched details
				const newDetailsMap = new Map(orderDetails);
				ordersNeedingDetails.forEach((order, index) => {
					if (detailsResults[index]) {
						newDetailsMap.set(order.id, detailsResults[index]!);
					}
				});
				orderDetails = newDetailsMap;
			}

			// Build TXT content from cached details
			for (const order of ordersToExport) {
				const details = orderDetails.get(order.id);
				if (!details) continue;

				// Order header
				txtContent += `ORDER: ${order.id.slice(0, 8)}... - ${formatDate(order.created_at)} - ${order.status.toUpperCase()}\n`;
				txtContent += '='.repeat(140) + '\n\n';

				// Group items by product type
				const groupedItems = groupItemsByProductType(details.items);

				// Add sections for each product type
				for (const [tableName, items] of groupedItems.entries()) {
					const productType = getProductTypeLabel(tableName);
					txtContent += `${productType.toUpperCase()}:\n`;
					txtContent += '-'.repeat(140) + '\n';

					// Table header with proper spacing
					const header = `${padRight('First', 12)} ${padRight('Middle', 10)} ${padRight('Last', 12)} ${padRight('DOB', 12)} ${padRight('Full Address', 35)} ${padRight('Email', 25)} ${padRight('Phone', 15)} SSN`;
					txtContent += header + '\n';
					txtContent += '-'.repeat(140) + '\n';

					// Table rows
					for (const item of items) {
						if (!item.ssn_details) continue;

						const row = `${padRight(item.ssn_details.firstname || '', 12)} ${padRight(item.ssn_details.middlename || '', 10)} ${padRight(item.ssn_details.lastname || '', 12)} ${padRight(item.ssn_details.dob ? formatDOBISO(item.ssn_details.dob) : '', 12)} ${padRight(formatFullAddress(item.ssn_details).slice(0, 34), 35)} ${padRight(item.ssn_details.email || '', 25)} ${padRight(item.ssn_details.phone || '', 15)} ${item.ssn ? formatSSN(item.ssn) : ''}`;
						txtContent += row + '\n';
					}

					txtContent += '\n';
				}

				// Order total
				txtContent += `Total: ${formatCurrency(details.total_price)}\n`;
				txtContent += '\n\n';
			}

			// Create blob and download
			const blob = new Blob([txtContent], { type: 'text/plain' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			const ts = new Date().toISOString().replace(/:/g, '-');
			a.download = `orders-details-${ts}.txt`;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
		} catch (error) {
			console.error('Failed to export orders:', error);
			errorMessage = $t('orders.messages.exportFailed');
		}
	}

	// Helper function for padding text
	function padRight(text: string, length: number): string {
		return text.padEnd(length).slice(0, length);
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
		// Don't copy if value is just a placeholder
		if (value === '-') return;

		try {
			// Copy to clipboard
			await navigator.clipboard.writeText(value);

			// Show tooltip
			copiedCells.set(cellKey, true);

			// Hide tooltip after 2 seconds
			setTimeout(() => {
				copiedCells.delete(cellKey);
				copiedCells = new Map(copiedCells); // Trigger reactivity
			}, 2000);
		} catch (error) {
			console.error('Failed to copy cell value:', error);
		}
	}
</script>

<TooltipProvider>
<div class="w-full space-y-6 p-6">
	<!-- Page Title -->
	<div class="flex items-center justify-center">
		<h1 class="text-3xl font-bold">{$t('orders.title')}</h1>
	</div>

	<!-- Order Type Tabs -->
	<Tabs.Root value={selectedOrderType} onValueChange={handleOrderTypeChange}>
		<Tabs.List class="grid w-full grid-cols-3">
			<Tabs.Trigger value="all">{$t('orders.tabs.all')}</Tabs.Trigger>
			<Tabs.Trigger value="instant_ssn">{$t('orders.tabs.instantSSN')}</Tabs.Trigger>
			<Tabs.Trigger value="manual_ssn">{$t('orders.tabs.manualSSN')}</Tabs.Trigger>
		</Tabs.List>

		<Tabs.Content value={selectedOrderType}>
		<!-- Filters and Actions Bar -->
		<div class="flex flex-wrap items-center justify-center gap-4 mt-4">
			<!-- Status Filter -->
			<Select.Root
				onSelectedChange={(selected) => {
					if (selected) {
						handleStatusFilter(selected.value);
					}
				}}
			>
				<Select.Trigger class="w-[180px]">
					<Filter class="mr-2 h-4 w-4" />
					<Select.Value placeholder={$t('orders.filters.status')} />
				</Select.Trigger>
				<Select.Content>
					{#each ORDER_STATUSES as status}
						<Select.Item value={status.value}>{status.label}</Select.Item>
					{/each}
				</Select.Content>
			</Select.Root>

			<!-- Refresh Button -->
			<Button variant="outline" onclick={handleRefresh} disabled={isLoading}>
				<RefreshCw class={`mr-2 h-4 w-4${isLoading ? ' animate-spin' : ''}`} />
				{$t('orders.actions.refresh')}
			</Button>

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
		{:else if orders.length === 0}
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
			<Card>
				<CardContent class="p-0">
					<div class="w-full">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead class="w-12">
										<Checkbox
											checked={isAllSelected}
											indeterminate={isSomeSelected}
											onCheckedChange={(checked) => handleSelectAll(checked === true)}
											aria-label={$t('orders.table.selectAll')}
										/>
									</TableHead>
									<TableHead>{$t('orders.table.firstName')}</TableHead>
									<TableHead class="hidden md:table-cell">{$t('orders.table.middleName')}</TableHead>
									<TableHead>{$t('orders.table.lastName')}</TableHead>
									<TableHead>{$t('orders.table.ssn')}</TableHead>
									<TableHead>{$t('orders.table.dob')}</TableHead>
									<TableHead>{$t('orders.table.fullAddress')}</TableHead>
									<TableHead>{$t('orders.table.emails')}</TableHead>
									<TableHead>{$t('orders.table.phones')}</TableHead>
									<TableHead class="text-center">{$t('orders.table.actions')}</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each paginatedItems as item, index (item.order_id + '-' + index)}
									{@const itemKey = `${item.order_id}-${index}`}
									{@const isCopying = copyingItemIds.has(itemKey)}
									{@const isCopied = copiedItemIds.has(itemKey)}
									<TableRow>
										<TableCell class="w-12">
											<Checkbox
												checked={selectedOrderIds.has(item.order_id)}
												onCheckedChange={(checked) => handleSelectOrder(item.order_id, checked === true)}
												aria-label="Select order"
											/>
										</TableCell>
										{@const firstname = item.firstname || item.ssn_details?.firstname || '-'}
										{@const middlename = item.middlename || item.ssn_details?.middlename || '-'}
										{@const lastname = item.lastname || item.ssn_details?.lastname || '-'}
										{@const dob = item.dob ? formatDOBISO(item.dob) : item.ssn_details?.dob ? formatDOBISO(item.ssn_details.dob) : '-'}
										{@const fullAddress = formatFullAddressFromItem(item)}
										{@const email = item.email || item.ssn_details?.email || '-'}
										{@const phone = item.phone ? formatPhone(item.phone) : item.ssn_details?.phone ? formatPhone(item.ssn_details.phone) : '-'}

										<TableCell class="text-sm relative cursor-pointer hover:bg-primary/5 hover:ring-1 hover:ring-primary/20 transition-all duration-150" onclick={() => copyCellValue(firstname, `${itemKey}-firstname`)}>
											{firstname}
											{#if copiedCells.get(`${itemKey}-firstname`)}
												<span class="absolute inset-0 flex items-center justify-center bg-primary/90 backdrop-blur-sm text-primary-foreground text-xs rounded pointer-events-none animate-fade">
													Copied
												</span>
											{/if}
										</TableCell>
										<TableCell class="text-sm hidden md:table-cell relative cursor-pointer hover:bg-primary/5 hover:ring-1 hover:ring-primary/20 transition-all duration-150" onclick={() => copyCellValue(middlename, `${itemKey}-middlename`)}>
											{middlename}
											{#if copiedCells.get(`${itemKey}-middlename`)}
												<span class="absolute inset-0 flex items-center justify-center bg-primary/90 backdrop-blur-sm text-primary-foreground text-xs rounded pointer-events-none animate-fade">
													Copied
												</span>
											{/if}
										</TableCell>
										<TableCell class="text-sm relative cursor-pointer hover:bg-primary/5 hover:ring-1 hover:ring-primary/20 transition-all duration-150" onclick={() => copyCellValue(lastname, `${itemKey}-lastname`)}>
											{lastname}
											{#if copiedCells.get(`${itemKey}-lastname`)}
												<span class="absolute inset-0 flex items-center justify-center bg-primary/90 backdrop-blur-sm text-primary-foreground text-xs rounded pointer-events-none animate-fade">
													Copied
												</span>
											{/if}
										</TableCell>
										<TableCell class="relative cursor-pointer hover:bg-primary/5 hover:ring-1 hover:ring-primary/20 transition-all duration-150" onclick={() => copyCellValue(formatSSN(item.ssn), `${itemKey}-ssn`)}>
											<code class="code-block text-xs">
												{formatSSN(item.ssn)}
											</code>
											{#if copiedCells.get(`${itemKey}-ssn`)}
												<span class="absolute inset-0 flex items-center justify-center bg-primary/90 backdrop-blur-sm text-primary-foreground text-xs rounded pointer-events-none animate-fade">
													Copied
												</span>
											{/if}
										</TableCell>
										<TableCell class="text-sm relative cursor-pointer hover:bg-primary/5 hover:ring-1 hover:ring-primary/20 transition-all duration-150" onclick={() => copyCellValue(dob, `${itemKey}-dob`)}>
											{dob}
											{#if copiedCells.get(`${itemKey}-dob`)}
												<span class="absolute inset-0 flex items-center justify-center bg-primary/90 backdrop-blur-sm text-primary-foreground text-xs rounded pointer-events-none animate-fade">
													Copied
												</span>
											{/if}
										</TableCell>
										<TableCell class="text-sm relative cursor-pointer hover:bg-primary/5 hover:ring-1 hover:ring-primary/20 transition-all duration-150" onclick={() => copyCellValue(fullAddress, `${itemKey}-address`)}>
											{fullAddress}
											{#if copiedCells.get(`${itemKey}-address`)}
												<span class="absolute inset-0 flex items-center justify-center bg-primary/90 backdrop-blur-sm text-primary-foreground text-xs rounded pointer-events-none animate-fade">
													Copied
												</span>
											{/if}
										</TableCell>
										<TableCell class="text-sm relative cursor-pointer hover:bg-primary/5 hover:ring-1 hover:ring-primary/20 transition-all duration-150" onclick={() => copyCellValue(email, `${itemKey}-email`)}>
											{email}
											{#if copiedCells.get(`${itemKey}-email`)}
												<span class="absolute inset-0 flex items-center justify-center bg-primary/90 backdrop-blur-sm text-primary-foreground text-xs rounded pointer-events-none animate-fade">
													Copied
												</span>
											{/if}
										</TableCell>
										<TableCell class="text-sm relative cursor-pointer hover:bg-primary/5 hover:ring-1 hover:ring-primary/20 transition-all duration-150" onclick={() => copyCellValue(phone, `${itemKey}-phone`)}>
											{phone}
											{#if copiedCells.get(`${itemKey}-phone`)}
												<span class="absolute inset-0 flex items-center justify-center bg-primary/90 backdrop-blur-sm text-primary-foreground text-xs rounded pointer-events-none animate-fade">
													Copied
												</span>
											{/if}
										</TableCell>
										<TableCell>
											<Button
												variant="ghost"
												size="sm"
												onclick={() => handleCopyRecord(itemKey, item)}
												disabled={isCopying}
												class="h-8 w-8 p-0"
											>
												{#if isCopying}
													<Loader2 class="h-4 w-4 animate-spin" />
												{:else if isCopied}
													<Check class="h-4 w-4 text-green-500" />
												{:else}
													<Copy class="h-4 w-4" />
												{/if}
											</Button>
										</TableCell>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					</div>
				</CardContent>
			</Card>

			<!-- Pagination -->
			{#if totalPages > 1}
				<div class="flex items-center justify-between">
					<div class="text-sm text-gray-600">
						{$t('orders.pagination.page').replace('{{current}}', String(currentPage + 1)).replace('{{total}}', String(totalPages))}
					</div>
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
				</div>
			{/if}
		{/if}
		</Tabs.Content>
	</Tabs.Root>
</div>
</TooltipProvider>

<style>
	@keyframes fade {
		0% {
			opacity: 0;
			transform: scale(0.95);
		}
		10% {
			opacity: 1;
			transform: scale(1);
		}
		90% {
			opacity: 1;
			transform: scale(1);
		}
		100% {
			opacity: 0;
			transform: scale(0.95);
		}
	}

	:global(.animate-fade) {
		animation: fade 2s ease-in-out;
	}
</style>
