<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import {
		Dialog,
		DialogContent,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import ShoppingCart from '@lucide/svelte/icons/shopping-cart';
	import SearchIcon from '@lucide/svelte/icons/search';
	import {
		getOrders,
		getFailedSearches,
		handleApiError,
		type OrderItemResponse,
		type FailedItemResponse
	} from '$lib/api/client';
	import { formatDateTime } from '$lib/utils';
	import { toast } from 'svelte-sonner';
	import { t } from '$lib/i18n';

	// Cost constants (match backend pricing.py)
	const INSTANT_SSN_ATTEMPT_COST = 0.85;
	const SEARCHBUG_API_COST = 0.85;
	const MANUAL_SSN_COST = 1.50;

	// Tab type
	type TabType = 'all' | 'instant' | 'manual' | 'notfound' | 'api_failed';

	// State
	let orders = $state<OrderItemResponse[]>([]);
	let failedItems = $state<FailedItemResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let totalCount = $state(0);
	let currentPage = $state(1);
	let pageSize = $state(50);
	let activeTab = $state<TabType>('all');
	let searchQuery = $state('');
	let searchInput = $state('');
	let selectedOrder = $state<OrderItemResponse | null>(null);
	let showDetailDialog = $state(false);

	let totalPages = $derived(Math.ceil(totalCount / pageSize) || 1);
	let isFailedTab = $derived(activeTab === 'notfound' || activeTab === 'api_failed');

	function getItemsCount(order: OrderItemResponse): number {
		return Array.isArray(order.items) ? order.items.length : 0;
	}

	function getOrderInput(order: OrderItemResponse): string {
		const items = Array.isArray(order.items) ? order.items : [];
		if (items.length === 0) return '-';
		const item = items[0];
		const name = [item.firstname, item.lastname].filter(Boolean).join(' ');
		return name || '-';
	}

	function getOrderSSN(order: OrderItemResponse): string {
		const items = Array.isArray(order.items) ? order.items : [];
		if (items.length === 0) return '-';
		const item = items[0];
		if (!item.ssn || item.ssn === 'Not found') return '-';
		const ssn = String(item.ssn).replace(/\D/g, '');
		if (ssn.length === 9) return `***-**-${ssn.slice(5)}`;
		return item.ssn;
	}

	function getOrderDOB(order: OrderItemResponse): string {
		const items = Array.isArray(order.items) ? order.items : [];
		if (items.length === 0) return '-';
		return items[0].dob || '-';
	}

	function calculateCost(order: OrderItemResponse): number {
		const count = getItemsCount(order);
		if (order.order_type === 'instant_ssn') return count * INSTANT_SSN_ATTEMPT_COST;
		if (order.order_type === 'manual_ssn') {
			const found = Number(order.total_price) > 0;
			return SEARCHBUG_API_COST + (found ? MANUAL_SSN_COST : 0);
		}
		return 0;
	}

	function calculateProfit(order: OrderItemResponse): number {
		return Number(order.total_price) - calculateCost(order);
	}

	function calculateROI(order: OrderItemResponse): number {
		const cost = calculateCost(order);
		if (cost === 0) return 0;
		return (calculateProfit(order) / cost) * 100;
	}

	function formatMoney(value: number | string): string {
		return '$' + Number(value).toFixed(2);
	}

	function getStatusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
		switch (status) {
			case 'completed': return 'default';
			case 'pending': return 'secondary';
			case 'failed': return 'destructive';
			case 'cancelled': return 'outline';
			default: return 'secondary';
		}
	}

	function getTypeLabel(type: string): string {
		switch (type) {
			case 'instant_ssn': return 'Instant';
			case 'manual_ssn': return 'Manual';
			case 'reverse_ssn': return 'Reverse';
			default: return type;
		}
	}

	function getTypeFilterParam(): string | undefined {
		if (activeTab === 'instant') return 'instant_ssn';
		if (activeTab === 'manual') return 'manual_ssn';
		return undefined;
	}

	function getReasonFilter(): string | undefined {
		if (activeTab === 'notfound') return 'not_found';
		if (activeTab === 'api_failed') return 'api_error';
		return undefined;
	}

	async function loadData() {
		isLoading = true;
		error = '';
		try {
			if (isFailedTab) {
				const data = await getFailedSearches({
					reason_filter: getReasonFilter(),
					search: searchQuery || undefined,
					limit: pageSize,
					offset: (currentPage - 1) * pageSize
				});
				failedItems = data.items;
				totalCount = data.total_count;
				orders = [];
			} else {
				const params: any = {
					limit: pageSize,
					offset: (currentPage - 1) * pageSize
				};
				const typeFilter = getTypeFilterParam();
				if (typeFilter) params.type_filter = typeFilter;
				if (searchQuery) params.search = searchQuery;

				const data = await getOrders(params);
				orders = data.orders;
				totalCount = data.total_count;
				failedItems = [];
			}
		} catch (err: any) {
			error = handleApiError(err);
		} finally {
			isLoading = false;
		}
	}

	function goPage(page: number) {
		currentPage = page;
		loadData();
	}

	function switchTab(tab: TabType) {
		activeTab = tab;
		currentPage = 1;
		loadData();
	}

	function handleSearch() {
		searchQuery = searchInput.trim();
		currentPage = 1;
		loadData();
	}

	function handleSearchKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') handleSearch();
	}

	function clearSearch() {
		searchInput = '';
		searchQuery = '';
		currentPage = 1;
		loadData();
	}

	function openDetail(order: OrderItemResponse) {
		selectedOrder = order;
		showDetailDialog = true;
	}

	onMount(() => {
		loadData();
	});
</script>

<div class="space-y-4">
	<!-- Tabs + Search + Count -->
	<Card>
		<CardContent class="pt-5 pb-4">
			<div class="flex items-center justify-between gap-4">
				<div class="flex items-center gap-2">
					<Button
						variant={activeTab === 'all' ? 'default' : 'outline'}
						size="sm"
						onclick={() => switchTab('all')}
					>
						{$t('orders.filters.all')}
					</Button>
					<Button
						variant={activeTab === 'instant' ? 'default' : 'outline'}
						size="sm"
						onclick={() => switchTab('instant')}
					>
						Instant
					</Button>
					<Button
						variant={activeTab === 'manual' ? 'default' : 'outline'}
						size="sm"
						onclick={() => switchTab('manual')}
					>
						Manual
					</Button>
					<Button
						variant={activeTab === 'notfound' ? 'default' : 'outline'}
						size="sm"
						onclick={() => switchTab('notfound')}
					>
						Not Found
					</Button>
					<Button
						variant={activeTab === 'api_failed' ? 'default' : 'outline'}
						size="sm"
						onclick={() => switchTab('api_failed')}
					>
						API Failed
					</Button>
				</div>
				<div class="flex items-center gap-2">
					<!-- Compact Search -->
					<div class="flex items-center">
						<input
							type="text"
							bind:value={searchInput}
							onkeydown={handleSearchKeydown}
							placeholder="Username..."
							class="h-8 w-36 rounded-l-md border border-r-0 border-input bg-background px-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
						/>
						<button
							onclick={handleSearch}
							class="flex h-8 items-center rounded-r-md border border-input bg-muted px-2 text-muted-foreground hover:bg-accent hover:text-foreground"
						>
							<SearchIcon class="h-3.5 w-3.5" />
						</button>
						{#if searchQuery}
							<button
								onclick={clearSearch}
								class="ml-1 text-xs text-muted-foreground hover:text-foreground"
							>
								&times;
							</button>
						{/if}
					</div>
					<span class="text-sm text-muted-foreground">{totalCount}</span>
					<Button variant="outline" size="sm" onclick={() => loadData()} disabled={isLoading}>
						<RefreshCw class="mr-1.5 h-3.5 w-3.5" />
						{$t('common.refresh')}
					</Button>
				</div>
			</div>
		</CardContent>
	</Card>

	<!-- Orders table / Not Found table -->
	<Card>
		<CardContent class="p-0">
			{#if isLoading}
				<div class="flex items-center justify-center py-12">
					<Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
				</div>
			{:else if error}
				<Alert variant="destructive" class="m-4">
					<AlertDescription>{error}</AlertDescription>
				</Alert>
			{:else if isFailedTab}
				<!-- Failed / Not Found table -->
				{#if failedItems.length === 0}
					<div class="flex flex-col items-center justify-center py-12 text-center">
						<ShoppingCart class="mb-3 h-10 w-10 text-muted-foreground/50" />
						<p class="text-muted-foreground">No {activeTab === 'notfound' ? 'not-found searches' : 'API failures'}</p>
					</div>
				{:else}
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead class="w-[90px]">{$t('orders.table.id')}</TableHead>
								<TableHead class="w-[80px]">Reason</TableHead>
								<TableHead class="w-[120px]">{$t('orders.table.user')}</TableHead>
								<TableHead>Full Name</TableHead>
								<TableHead>Address</TableHead>
								{#if activeTab === 'api_failed'}
									<TableHead>Error</TableHead>
								{:else}
									<TableHead class="w-[80px] text-right">Time</TableHead>
								{/if}
								<TableHead class="w-[140px]">{$t('orders.table.date')}</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each failedItems as item}
								<TableRow>
									<TableCell class="font-mono text-xs">
										{item.id.slice(0, 8)}
									</TableCell>
									<TableCell>
										<Badge variant={item.reason === 'api_error' ? 'outline' : 'destructive'} class="text-xs">
											{item.reason === 'api_error' ? 'API' : 'NF'}
										</Badge>
									</TableCell>
									<TableCell class="text-sm">
										{item.username}
									</TableCell>
									<TableCell class="text-sm">
										{item.input_fullname}
									</TableCell>
									<TableCell class="text-sm text-muted-foreground">
										{item.input_address}
									</TableCell>
									{#if activeTab === 'api_failed'}
										<TableCell class="max-w-[200px] truncate text-xs text-muted-foreground" title={item.error_message || ''}>
											{item.error_message || '-'}
										</TableCell>
									{:else}
										<TableCell class="text-right text-sm text-muted-foreground">
											{item.search_time != null ? `${item.search_time}s` : '-'}
										</TableCell>
									{/if}
									<TableCell class="text-xs text-muted-foreground">
										{formatDateTime(item.created_at)}
									</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				{/if}
			{:else}
				<!-- Orders table -->
				{#if orders.length === 0}
					<div class="flex flex-col items-center justify-center py-12 text-center">
						<ShoppingCart class="mb-3 h-10 w-10 text-muted-foreground/50" />
						<p class="text-muted-foreground">{$t('orders.noOrders')}</p>
					</div>
				{:else}
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead class="w-[90px]">{$t('orders.table.id')}</TableHead>
								<TableHead class="w-[80px]">{$t('orders.table.type')}</TableHead>
								<TableHead class="w-[120px]">{$t('orders.table.user')}</TableHead>
								<TableHead>Input</TableHead>
								<TableHead class="w-[100px]">SSN</TableHead>
								<TableHead class="w-[90px]">DOB</TableHead>
								<TableHead class="w-[70px] text-right">{$t('orders.table.price')}</TableHead>
								<TableHead class="w-[70px] text-right">Cost</TableHead>
								<TableHead class="w-[70px] text-right">{$t('orders.table.profit')}</TableHead>
								<TableHead class="w-[60px] text-right">ROI</TableHead>
								<TableHead class="w-[130px]">{$t('orders.table.date')}</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each orders as order}
								{@const profit = calculateProfit(order)}
								<TableRow
									class="cursor-pointer hover:bg-muted/50"
									onclick={() => openDetail(order)}
								>
									<TableCell class="font-mono text-xs">
										{order.id.slice(0, 8)}
									</TableCell>
									<TableCell>
										<Badge variant="outline" class="text-xs">
											{getTypeLabel(order.order_type)}
										</Badge>
									</TableCell>
									<TableCell class="text-sm">
										{order.username}
									</TableCell>
									<TableCell class="max-w-[180px] truncate text-sm" title={getOrderInput(order)}>
										{getOrderInput(order)}
									</TableCell>
									<TableCell class="font-mono text-xs">
										{getOrderSSN(order)}
									</TableCell>
									<TableCell class="text-xs">
										{getOrderDOB(order)}
									</TableCell>
									<TableCell class="text-right text-sm font-medium">
										{formatMoney(order.total_price)}
									</TableCell>
									<TableCell class="text-right text-sm text-muted-foreground">
										{formatMoney(calculateCost(order))}
									</TableCell>
									<TableCell class="text-right text-sm font-medium {profit >= 0 ? 'text-green-600' : 'text-red-500'}">
										{formatMoney(profit)}
									</TableCell>
									<TableCell class="text-right text-sm {profit >= 0 ? 'text-green-600' : 'text-red-500'}">
										{calculateROI(order).toFixed(0)}%
									</TableCell>
									<TableCell class="text-xs text-muted-foreground">
										{formatDateTime(order.created_at)}
									</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				{/if}
			{/if}

			<!-- Pagination -->
			{#if !isLoading && !error && totalPages > 1}
				<div class="flex items-center justify-between border-t px-4 py-3">
					<span class="text-sm text-muted-foreground">
						{$t('orders.pagination', { values: { count: totalCount, current: currentPage, total: totalPages } })}
					</span>
					<div class="flex gap-1">
						<Button
							variant="outline"
							size="sm"
							disabled={currentPage <= 1}
							onclick={() => goPage(currentPage - 1)}
						>
							<ChevronLeft class="h-4 w-4" />
						</Button>
						<Button
							variant="outline"
							size="sm"
							disabled={currentPage >= totalPages}
							onclick={() => goPage(currentPage + 1)}
						>
							<ChevronRight class="h-4 w-4" />
						</Button>
					</div>
				</div>
			{/if}
		</CardContent>
	</Card>
</div>

<!-- Order detail dialog -->
<Dialog bind:open={showDetailDialog}>
	<DialogContent class="max-w-2xl">
		<DialogHeader>
			<DialogTitle class="flex items-center gap-2">
				<ShoppingCart class="h-5 w-5" />
				{$t('orders.detail.title')}
			</DialogTitle>
		</DialogHeader>

		{#if selectedOrder}
			{@const profit = calculateProfit(selectedOrder)}
			<div class="space-y-4">
				<div class="grid grid-cols-2 gap-4">
					<div>
						<p class="mb-1 text-xs text-muted-foreground">{$t('orders.detail.orderId')}</p>
						<p class="font-mono text-sm">{selectedOrder.id}</p>
					</div>
					<div>
						<p class="mb-1 text-xs text-muted-foreground">{$t('orders.detail.status')}</p>
						<Badge variant={getStatusVariant(selectedOrder.status)}>
							{selectedOrder.status}
						</Badge>
					</div>
					<div>
						<p class="mb-1 text-xs text-muted-foreground">{$t('orders.detail.type')}</p>
						<Badge variant="outline">{getTypeLabel(selectedOrder.order_type)}</Badge>
					</div>
					<div>
						<p class="mb-1 text-xs text-muted-foreground">{$t('orders.detail.user')}</p>
						<p class="text-sm">{selectedOrder.username}</p>
					</div>
					<div>
						<p class="mb-1 text-xs text-muted-foreground">{$t('orders.detail.userId')}</p>
						<p class="font-mono text-xs">{selectedOrder.user_id}</p>
					</div>
					<div>
						<p class="mb-1 text-xs text-muted-foreground">{$t('orders.detail.date')}</p>
						<p class="text-sm">{formatDateTime(selectedOrder.created_at)}</p>
					</div>
				</div>

				<div class="rounded-md border p-4">
					<div class="grid grid-cols-3 gap-4 text-center">
						<div>
							<p class="text-xs text-muted-foreground">{$t('orders.detail.clientPrice')}</p>
							<p class="text-lg font-bold">{formatMoney(selectedOrder.total_price)}</p>
						</div>
						<div>
							<p class="text-xs text-muted-foreground">{$t('orders.detail.cost', { values: { count: getItemsCount(selectedOrder) } })}</p>
							<p class="text-lg font-bold text-muted-foreground">{formatMoney(calculateCost(selectedOrder))}</p>
						</div>
						<div>
							<p class="text-xs text-muted-foreground">{$t('orders.detail.profit')}</p>
							<p class="text-lg font-bold {profit >= 0 ? 'text-green-600' : 'text-red-500'}">
								{formatMoney(profit)}
							</p>
						</div>
					</div>
				</div>

				{#if selectedOrder.items && Array.isArray(selectedOrder.items)}
					<div class="space-y-3">
						<p class="text-xs font-medium text-muted-foreground">Items ({selectedOrder.items.length})</p>
						{#each selectedOrder.items as item, idx}
							<div class="rounded-md border p-3 space-y-2">
								{#if selectedOrder.items.length > 1}
									<p class="text-xs font-medium text-muted-foreground">#{idx + 1}</p>
								{/if}
								<div class="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
									{#if item.firstname || item.lastname}
										<div>
											<span class="text-xs text-muted-foreground">Name:</span>
											<span class="ml-1">{[item.firstname, item.middlename, item.lastname].filter(Boolean).join(' ')}</span>
										</div>
									{/if}
									{#if item.dob}
										<div>
											<span class="text-xs text-muted-foreground">DOB:</span>
											<span class="ml-1 font-mono">{item.dob}</span>
										</div>
									{/if}
									{#if item.ssn && item.ssn !== 'Not found'}
										<div>
											<span class="text-xs text-muted-foreground">SSN:</span>
											<span class="ml-1 font-mono">{item.ssn}</span>
										</div>
									{/if}
									{#if item.address}
										<div class="col-span-2">
											<span class="text-xs text-muted-foreground">Address:</span>
											<span class="ml-1">{[item.address, item.city, item.state, item.zip].filter(Boolean).join(', ')}</span>
										</div>
									{/if}
									{#if item.phone}
										<div>
											<span class="text-xs text-muted-foreground">Phone:</span>
											<span class="ml-1 font-mono">{item.phone}</span>
										</div>
									{/if}
									{#if item.email}
										<div>
											<span class="text-xs text-muted-foreground">Email:</span>
											<span class="ml-1">{item.email}</span>
										</div>
									{/if}
									{#if item.source}
										<div>
											<span class="text-xs text-muted-foreground">Source:</span>
											<span class="ml-1">{item.source}</span>
										</div>
									{/if}
									<div>
										<span class="text-xs text-muted-foreground">Method:</span>
										{#if item.source === 'manual_ticket'}
											<span class="ml-1 text-orange-500 font-medium">Manual Worker</span>
										{:else if item.search_method === 'searchbug'}
											<span class="ml-1 text-blue-500 font-medium">SearchBug</span>
										{:else if item.search_method === 'whitepages'}
											<span class="ml-1 text-green-500 font-medium">WhitePages</span>
										{:else}
											<span class="ml-1 text-muted-foreground">—</span>
										{/if}
									</div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{/if}
	</DialogContent>
</Dialog>
