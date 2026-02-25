<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Badge } from '$lib/components/ui/badge';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Label } from '$lib/components/ui/label';
	import { Textarea } from '$lib/components/ui/textarea';
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
		DialogDescription,
		DialogFooter,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import {
		DropdownMenu,
		DropdownMenuContent,
		DropdownMenuItem,
		DropdownMenuTrigger
	} from '$lib/components/ui/dropdown-menu';
	import {
		getProfitUsers,
		addUserBalance,
		setUserSearchMode,
		banUser,
		unbanUser,
		getCustomPricingByUserId,
		createCustomPricing,
		updateCustomPricing,
		type ProfitUserItem,
		handleApiError
	} from '$lib/api/client';
	import { formatCurrency, formatDate } from '$lib/utils';
	import {
		Search,
		ChevronUp,
		ChevronDown,
		Loader2,
		ChevronLeft,
		ChevronRight,
		Ban,
		ShieldOff,
		Plus,
		RefreshCw,
		Settings2,
		Pencil
	} from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { t } from '$lib/i18n';

	// State
	let users = $state<ProfitUserItem[]>([]);
	let totalCount = $state(0);
	let currentPage = $state(1);
	let pageSize = $state(50);
	let searchQuery = $state('');
	let sortBy = $state('total_profit');
	let sortOrder = $state<'asc' | 'desc'>('desc');
	let isLoading = $state(true);
	let error = $state('');
	let selectedPeriod = $state('all');

	// Add balance dialog
	let showAddBalanceDialog = $state(false);
	let addBalanceUser = $state<ProfitUserItem | null>(null);
	let addBalanceAmount = $state('');
	let isAddingBalance = $state(false);

	// Price dialog
	let showPriceDialog = $state(false);
	let priceUser = $state<ProfitUserItem | null>(null);
	let priceAmount = $state('');
	let isSavingPrice = $state(false);
	let existingPricingId = $state<string | null>(null);

	// Ban dialog
	let showBanDialog = $state(false);
	let banTargetUser = $state<ProfitUserItem | null>(null);
	let banReason = $state('');
	let isBanning = $state(false);

	// Debounce
	let searchTimeout: ReturnType<typeof setTimeout> | null = null;
	let abortController: AbortController | null = null;

	// Computed
	let totalPages = $derived(Math.ceil(totalCount / pageSize));
	let startIndex = $derived((currentPage - 1) * pageSize + 1);
	let endIndex = $derived(Math.min(currentPage * pageSize, totalCount));

	const periods = [
		{ value: '1d', labelKey: 'users.periods.24h' },
		{ value: '7d', labelKey: 'users.periods.7d' },
		{ value: '30d', labelKey: 'users.periods.30d' },
		{ value: 'all', labelKey: 'users.periods.all' }
	];

	async function loadUsers() {
		if (abortController) abortController.abort();
		abortController = new AbortController();
		const ctrl = abortController;

		isLoading = true;
		error = '';
		try {
			const offset = (currentPage - 1) * pageSize;
			const response = await getProfitUsers({
				period: selectedPeriod,
				limit: pageSize,
				offset,
				search: searchQuery || undefined,
				sort_by: sortBy,
				sort_order: sortOrder
			});
			if (!ctrl.signal.aborted) {
				users = response.users;
				totalCount = response.total_count;
			}
		} catch (err: any) {
			if (!ctrl.signal.aborted) {
				error = handleApiError(err);
			}
		} finally {
			if (!ctrl.signal.aborted) isLoading = false;
		}
	}

	function handleSearchInput() {
		if (searchTimeout) clearTimeout(searchTimeout);
		searchTimeout = setTimeout(() => {
			currentPage = 1;
			loadUsers();
		}, 500);
	}

	function handleSort(column: string) {
		if (sortBy === column) {
			sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
		} else {
			sortBy = column;
			sortOrder = 'desc';
		}
		loadUsers();
	}

	function handlePeriodChange(period: string) {
		selectedPeriod = period;
		currentPage = 1;
		loadUsers();
	}

	function goToPage(page: number) {
		if (page >= 1 && page <= totalPages) {
			currentPage = page;
			loadUsers();
		}
	}

	function getPageNumbers(): number[] {
		const pages: number[] = [];
		const maxPages = 5;
		let startPage = Math.max(1, currentPage - Math.floor(maxPages / 2));
		let endPage = Math.min(totalPages, startPage + maxPages - 1);
		if (endPage - startPage + 1 < maxPages) {
			startPage = Math.max(1, endPage - maxPages + 1);
		}
		for (let i = startPage; i <= endPage; i++) pages.push(i);
		return pages;
	}

	function fmtPct(val: number): string {
		if (val === 0) return '-';
		return val.toFixed(1) + '%';
	}

	// --- Add Balance ---
	function openAddBalance(user: ProfitUserItem) {
		addBalanceUser = user;
		addBalanceAmount = '';
		showAddBalanceDialog = true;
	}

	async function handleAddBalance() {
		if (!addBalanceUser) return;
		const amount = parseFloat(addBalanceAmount);
		if (isNaN(amount) || amount <= 0) {
			toast.error($t('users.addBalance.invalidAmount'));
			return;
		}
		isAddingBalance = true;
		try {
			const res = await addUserBalance(addBalanceUser.id, amount);
			toast.success(res.message);
			showAddBalanceDialog = false;
			await loadUsers();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isAddingBalance = false;
		}
	}

	// --- Search Mode ---
	async function handleSearchModeChange(user: ProfitUserItem, mode: string) {
		try {
			const res = await setUserSearchMode(user.id, mode);
			toast.success(res.message);
			// Update in-place
			const idx = users.findIndex((u) => u.id === user.id);
			if (idx !== -1) {
				users[idx] = { ...users[idx], search_mode: mode };
			}
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// --- Price ---
	let existingManualPricingId = $state<string | null>(null);

	async function openPriceDialog(user: ProfitUserItem) {
		priceUser = user;
		priceAmount = user.search_price.toFixed(2);
		existingPricingId = null;
		existingManualPricingId = null;
		showPriceDialog = true;
		// Check if custom pricing exists for both services
		try {
			const pricings = await getCustomPricingByUserId(user.id);
			const instant = pricings.find((p) => p.service_name === 'instant_ssn' && p.is_active);
			if (instant) existingPricingId = instant.id;
			const manual = pricings.find((p) => p.service_name === 'manual_ssn' && p.is_active);
			if (manual) existingManualPricingId = manual.id;
		} catch {}
	}

	async function handleSavePrice() {
		if (!priceUser) return;
		const price = parseFloat(priceAmount);
		if (isNaN(price) || price < 0) {
			toast.error($t('users.changePrice.invalidPrice'));
			return;
		}
		isSavingPrice = true;
		try {
			const priceStr = price.toFixed(2);
			// Save instant_ssn price
			if (existingPricingId) {
				await updateCustomPricing(existingPricingId, { price: priceStr });
			} else {
				await createCustomPricing({
					user_id: priceUser.id,
					service_name: 'instant_ssn',
					price: priceStr
				});
			}
			// Save manual_ssn price (same value)
			if (existingManualPricingId) {
				await updateCustomPricing(existingManualPricingId, { price: priceStr });
			} else {
				await createCustomPricing({
					user_id: priceUser.id,
					service_name: 'manual_ssn',
					price: priceStr
				});
			}
			toast.success($t('users.changePrice.updated', { username: priceUser.username, price: priceStr }));
			showPriceDialog = false;
			await loadUsers();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isSavingPrice = false;
		}
	}

	// --- Ban ---
	function openBanDialog(user: ProfitUserItem) {
		banTargetUser = user;
		banReason = '';
		showBanDialog = true;
	}

	async function handleBanUser() {
		if (!banTargetUser || banReason.trim().length < 3) {
			toast.error($t('users.banUser.reasonRequired'));
			return;
		}
		isBanning = true;
		try {
			const res = await banUser(banTargetUser.id, banReason.trim());
			toast.success(res.message);
			showBanDialog = false;
			await loadUsers();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isBanning = false;
		}
	}

	async function handleUnbanUser(user: ProfitUserItem) {
		try {
			const res = await unbanUser(user.id);
			toast.success(res.message);
			await loadUsers();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	function sortIcon(column: string): typeof ChevronUp | typeof ChevronDown | null {
		if (sortBy !== column) return null;
		return sortOrder === 'asc' ? ChevronUp : ChevronDown;
	}

	onMount(() => {
		loadUsers();
		return () => {
			if (abortController) abortController.abort();
		};
	});
</script>

<div class="space-y-3">
	<!-- Header: title + search + period buttons -->
	<div class="flex items-center gap-3">
		<h2 class="text-lg font-semibold whitespace-nowrap">{$t('users.title')}</h2>
		{#if totalCount > 0}
			<span class="text-xs text-muted-foreground whitespace-nowrap">{$t('common.pagination.showing', { start: startIndex, end: endIndex, total: totalCount })}</span>
		{/if}
		<div class="relative w-60">
			<Search class="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
			<Input
				placeholder={$t('common.search')}
				bind:value={searchQuery}
				oninput={handleSearchInput}
				class="h-8 pl-8 text-sm"
			/>
		</div>
		<div class="flex items-center gap-1 ml-auto">
			{#each periods as period}
				<Button
					variant={selectedPeriod === period.value ? 'default' : 'outline'}
					size="sm"
					class="h-8 px-3 text-xs"
					onclick={() => handlePeriodChange(period.value)}
				>
					{$t(period.labelKey)}
				</Button>
			{/each}
			<Button variant="outline" size="sm" class="h-8 w-8 p-0" onclick={loadUsers} disabled={isLoading}>
				{#if isLoading}
					<Loader2 class="h-3.5 w-3.5 animate-spin" />
				{:else}
					<RefreshCw class="h-3.5 w-3.5" />
				{/if}
			</Button>
		</div>
	</div>

	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Table -->
	<Card>
		<CardContent class="pt-4">
			{#if isLoading && users.length === 0}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-8 w-8 animate-spin text-primary" />
				</div>
			{:else if users.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-muted-foreground">{$t('users.noUsers')}</p>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>
									<Button variant="ghost" size="sm" class="h-8 px-2" onclick={() => handleSort('username')}>
										{$t('users.table.user')}
										{#if sortBy === 'username'}
											{#if sortOrder === 'asc'}<ChevronUp class="ml-1 h-3 w-3" />{:else}<ChevronDown class="ml-1 h-3 w-3" />{/if}
										{/if}
									</Button>
								</TableHead>
								<TableHead>{$t('users.table.price')}</TableHead>
								<TableHead>{$t('users.table.type')}</TableHead>
								<TableHead>
									<Button variant="ghost" size="sm" class="h-8 px-2" onclick={() => handleSort('total_profit')}>
										{$t('users.table.totalProfit')}
										{#if sortBy === 'total_profit'}
											{#if sortOrder === 'asc'}<ChevronUp class="ml-1 h-3 w-3" />{:else}<ChevronDown class="ml-1 h-3 w-3" />{/if}
										{/if}
									</Button>
								</TableHead>
								<TableHead>
									<Button variant="ghost" size="sm" class="h-8 px-2" onclick={() => handleSort('instant_profit')}>
										{$t('users.table.instProfit')}
										{#if sortBy === 'instant_profit'}
											{#if sortOrder === 'asc'}<ChevronUp class="ml-1 h-3 w-3" />{:else}<ChevronDown class="ml-1 h-3 w-3" />{/if}
										{/if}
									</Button>
								</TableHead>
								<TableHead>{$t('users.table.roiInst')}</TableHead>
								<TableHead>{$t('users.table.successInst')}</TableHead>
								<TableHead>
									<Button variant="ghost" size="sm" class="h-8 px-2" onclick={() => handleSort('manual_profit')}>
										{$t('users.table.manualProfit')}
										{#if sortBy === 'manual_profit'}
											{#if sortOrder === 'asc'}<ChevronUp class="ml-1 h-3 w-3" />{:else}<ChevronDown class="ml-1 h-3 w-3" />{/if}
										{/if}
									</Button>
								</TableHead>
								<TableHead>{$t('users.table.roiManual')}</TableHead>
								<TableHead>{$t('users.table.successManual')}</TableHead>
								<TableHead>
									<Button variant="ghost" size="sm" class="h-8 px-2" onclick={() => handleSort('total_deposited')}>
										{$t('users.table.deposit')}
										{#if sortBy === 'total_deposited'}
											{#if sortOrder === 'asc'}<ChevronUp class="ml-1 h-3 w-3" />{:else}<ChevronDown class="ml-1 h-3 w-3" />{/if}
										{/if}
									</Button>
								</TableHead>
								<TableHead>
									<Button variant="ghost" size="sm" class="h-8 px-2" onclick={() => handleSort('balance')}>
										{$t('users.table.balance')}
										{#if sortBy === 'balance'}
											{#if sortOrder === 'asc'}<ChevronUp class="ml-1 h-3 w-3" />{:else}<ChevronDown class="ml-1 h-3 w-3" />{/if}
										{/if}
									</Button>
								</TableHead>
								<TableHead>
									<Button variant="ghost" size="sm" class="h-8 px-2" onclick={() => handleSort('created_at')}>
										{$t('users.table.regDate')}
										{#if sortBy === 'created_at'}
											{#if sortOrder === 'asc'}<ChevronUp class="ml-1 h-3 w-3" />{:else}<ChevronDown class="ml-1 h-3 w-3" />{/if}
										{/if}
									</Button>
								</TableHead>
								<TableHead>{$t('users.table.addBal')}</TableHead>
								<TableHead>{$t('users.table.ban')}</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each users as user}
								<TableRow>
									<TableCell class="font-medium">
										{user.username}
										{#if user.is_banned}
											<Badge variant="destructive" class="ml-1 text-xs">ban</Badge>
										{/if}
									</TableCell>
									<TableCell class="font-mono text-xs">
										<button class="inline-flex items-center gap-1 cursor-pointer hover:text-primary" onclick={() => openPriceDialog(user)}>
											{formatCurrency(user.search_price)}
											<Pencil class="h-3 w-3 opacity-50" />
										</button>
									</TableCell>
									<TableCell>
										<DropdownMenu>
											<DropdownMenuTrigger>
												{#snippet child({ props })}
													<Button {...props} variant="outline" size="sm" class="h-7 text-xs">
														{$t('users.searchModes.' + user.search_mode)}
														<Settings2 class="ml-1 h-3 w-3" />
													</Button>
												{/snippet}
											</DropdownMenuTrigger>
											<DropdownMenuContent>
												<DropdownMenuItem onclick={() => handleSearchModeChange(user, 'auto')}>
													{$t('users.searchModes.auto')}
												</DropdownMenuItem>
												<DropdownMenuItem onclick={() => handleSearchModeChange(user, 'instant')}>
													{$t('users.instantLabel')}
												</DropdownMenuItem>
												<DropdownMenuItem onclick={() => handleSearchModeChange(user, 'manual')}>
													{$t('users.manualLabel')}
												</DropdownMenuItem>
											</DropdownMenuContent>
										</DropdownMenu>
									</TableCell>
									<TableCell class="font-mono font-semibold {user.total_profit >= 0 ? 'text-green-600' : 'text-red-600'}">
										{formatCurrency(user.total_profit)}
									</TableCell>
									<TableCell class="font-mono text-xs">
										{formatCurrency(user.instant_profit)}
									</TableCell>
									<TableCell class="text-xs">{fmtPct(user.instant_roi)}</TableCell>
									<TableCell class="text-xs">{fmtPct(user.instant_success_rate)}</TableCell>
									<TableCell class="font-mono text-xs">
										{formatCurrency(user.manual_profit)}
									</TableCell>
									<TableCell class="text-xs">{fmtPct(user.manual_roi)}</TableCell>
									<TableCell class="text-xs">{fmtPct(user.manual_success_rate)}</TableCell>
									<TableCell class="font-mono text-xs">
										{formatCurrency(user.total_deposited)}
									</TableCell>
									<TableCell class="font-mono text-xs">
										{formatCurrency(user.balance)}
									</TableCell>
									<TableCell class="text-xs">{formatDate(user.created_at)}</TableCell>
									<TableCell>
										<Button variant="outline" size="sm" class="h-7 text-xs" onclick={() => openAddBalance(user)}>
											<Plus class="h-3 w-3" />
										</Button>
									</TableCell>
									<TableCell>
										{#if user.is_banned}
											<Button variant="outline" size="sm" class="h-7 text-xs text-green-600 border-green-600 hover:bg-green-50 dark:hover:bg-green-950" onclick={() => handleUnbanUser(user)}>
												<ShieldOff class="h-3 w-3" />
											</Button>
										{:else}
											<Button variant="destructive" size="sm" class="h-7 text-xs" onclick={() => openBanDialog(user)}>
												<Ban class="h-3 w-3" />
											</Button>
										{/if}
									</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				</div>

				<!-- Pagination -->
				{#if totalPages > 1}
					<div class="mt-4 flex items-center justify-between border-t pt-4">
						<div class="text-sm text-muted-foreground">
							{$t('common.pagination.page', { current: currentPage, total: totalPages })}
						</div>
						<div class="flex items-center gap-2">
							<Button variant="outline" size="sm" onclick={() => goToPage(currentPage - 1)} disabled={currentPage === 1}>
								<ChevronLeft class="h-4 w-4" />
							</Button>
							<div class="flex gap-1">
								{#each getPageNumbers() as pageNum}
									<Button
										variant={currentPage === pageNum ? 'default' : 'outline'}
										size="sm"
										class="w-10"
										onclick={() => goToPage(pageNum)}
									>
										{pageNum}
									</Button>
								{/each}
							</div>
							<Button variant="outline" size="sm" onclick={() => goToPage(currentPage + 1)} disabled={currentPage === totalPages}>
								<ChevronRight class="h-4 w-4" />
							</Button>
						</div>
					</div>
				{/if}
			{/if}
		</CardContent>
	</Card>

	<!-- Add Balance Dialog -->
	<Dialog bind:open={showAddBalanceDialog}>
		<DialogContent>
			<DialogHeader>
				<DialogTitle>{$t('users.addBalance.title')}</DialogTitle>
				<DialogDescription>
					{#if addBalanceUser}
						{@html $t('users.addBalance.description', { username: addBalanceUser.username, balance: formatCurrency(addBalanceUser.balance) })}
					{/if}
				</DialogDescription>
			</DialogHeader>
			<div class="space-y-4">
				<div class="space-y-2">
					<Label for="add-balance-amount">{$t('users.addBalance.amount')}</Label>
					<Input
						id="add-balance-amount"
						type="number"
						step="0.01"
						min="0.01"
						bind:value={addBalanceAmount}
						placeholder={$t('users.addBalance.placeholder')}
						disabled={isAddingBalance}
					/>
				</div>
			</div>
			<DialogFooter>
				<Button variant="outline" onclick={() => (showAddBalanceDialog = false)} disabled={isAddingBalance}>
					{$t('common.cancel')}
				</Button>
				<Button onclick={handleAddBalance} disabled={isAddingBalance || !addBalanceAmount}>
					{#if isAddingBalance}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						{$t('users.addBalance.adding')}
					{:else}
						<Plus class="mr-2 h-4 w-4" />
						{$t('users.addBalance.add')}
					{/if}
				</Button>
			</DialogFooter>
		</DialogContent>
	</Dialog>

	<!-- Price Dialog -->
	<Dialog bind:open={showPriceDialog}>
		<DialogContent>
			<DialogHeader>
				<DialogTitle>{$t('users.changePrice.title')}</DialogTitle>
				<DialogDescription>
					{#if priceUser}
						{@html $t('users.changePrice.description', { username: priceUser.username })}
					{/if}
				</DialogDescription>
			</DialogHeader>
			<div class="space-y-4">
				<div class="space-y-2">
					<Label for="price-amount">{$t('users.changePrice.price')}</Label>
					<Input
						id="price-amount"
						type="number"
						step="0.01"
						min="0"
						bind:value={priceAmount}
						placeholder={$t('users.changePrice.placeholder')}
						disabled={isSavingPrice}
					/>
				</div>
			</div>
			<DialogFooter>
				<Button variant="outline" onclick={() => (showPriceDialog = false)} disabled={isSavingPrice}>
					{$t('common.cancel')}
				</Button>
				<Button onclick={handleSavePrice} disabled={isSavingPrice || !priceAmount}>
					{#if isSavingPrice}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						{$t('common.saving')}
					{:else}
						{$t('common.save')}
					{/if}
				</Button>
			</DialogFooter>
		</DialogContent>
	</Dialog>

	<!-- Ban Dialog -->
	<Dialog bind:open={showBanDialog}>
		<DialogContent>
			<DialogHeader>
				<DialogTitle>{$t('users.banUser.title')}</DialogTitle>
				<DialogDescription>
					{#if banTargetUser}
						{@html $t('users.banUser.description', { username: banTargetUser.username })}
					{/if}
				</DialogDescription>
			</DialogHeader>
			<div class="space-y-4">
				<div class="space-y-2">
					<Label for="ban-reason">{$t('users.banUser.reason')}</Label>
					<Textarea
						id="ban-reason"
						bind:value={banReason}
						placeholder={$t('users.banUser.reasonPlaceholder')}
						rows={3}
						disabled={isBanning}
					/>
				</div>
			</div>
			<DialogFooter>
				<Button variant="outline" onclick={() => (showBanDialog = false)} disabled={isBanning}>
					{$t('common.cancel')}
				</Button>
				<Button variant="destructive" onclick={handleBanUser} disabled={isBanning || banReason.trim().length < 3}>
					{#if isBanning}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						{$t('users.banUser.banning')}
					{:else}
						<Ban class="mr-2 h-4 w-4" />
						{$t('users.banUser.banButton')}
					{/if}
				</Button>
			</DialogFooter>
		</DialogContent>
	</Dialog>
</div>
