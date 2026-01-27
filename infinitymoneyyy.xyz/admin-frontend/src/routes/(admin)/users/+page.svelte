<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
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
		getUserTable,
		type UserTableItem,
		handleApiError,
		banUser
	} from '$lib/api/client';
	import { formatCurrency, formatDate } from '$lib/utils';
	import { Search, ChevronUp, ChevronDown, Loader2, ChevronLeft, ChevronRight, Tag, X, Ban } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import {
		Dialog,
		DialogContent,
		DialogDescription,
		DialogFooter,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Label } from '$lib/components/ui/label';

	// State
	let users = $state<UserTableItem[]>([]);
	let totalCount = $state(0);
	let currentPage = $state(1);
	let pageSize = $state(50);
	let searchQuery = $state('');
	let couponFilter = $state('');
	let sortBy = $state('created_at');
	let sortOrder = $state<'asc' | 'desc'>('desc');
	let isLoading = $state(true);
	let error = $state('');

	// Ban dialog state
	let showBanDialog = $state(false);
	let selectedUser = $state<UserTableItem | null>(null);
	let banReason = $state('');
	let isBanning = $state(false);

	// Debounced search and filter
	let searchTimeout: ReturnType<typeof setTimeout> | null = null;
	let couponTimeout: ReturnType<typeof setTimeout> | null = null;

	// AbortController for canceling requests
	let abortController: AbortController | null = null;

	// Computed values
	let totalPages = $derived(Math.ceil(totalCount / pageSize));
	let startIndex = $derived((currentPage - 1) * pageSize + 1);
	let endIndex = $derived(Math.min(currentPage * pageSize, totalCount));

	// Load users
	async function loadUsers() {
		// Cancel previous request if exists
		if (abortController) {
			abortController.abort();
		}

		abortController = new AbortController();
		const currentController = abortController;

		isLoading = true;
		error = '';

		try {
			const offset = (currentPage - 1) * pageSize;
			const response = await getUserTable({
				limit: pageSize,
				offset,
				search: searchQuery || undefined,
				sort_by: sortBy,
				sort_order: sortOrder,
				coupon_code: couponFilter || undefined
			});

			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				users = response.users;
				totalCount = response.total_count;
			}
		} catch (err: any) {
			if (!currentController.signal.aborted) {
				error = handleApiError(err);
			}
		} finally {
			if (!currentController.signal.aborted) {
				isLoading = false;
			}
		}
	}

	// Handle search input
	function handleSearchInput() {
		if (searchTimeout) {
			clearTimeout(searchTimeout);
		}

		searchTimeout = setTimeout(() => {
			currentPage = 1; // Reset to first page on search
			loadUsers();
		}, 500);
	}

	// Handle coupon filter input
	function handleCouponFilterInput() {
		if (couponTimeout) {
			clearTimeout(couponTimeout);
		}

		couponTimeout = setTimeout(() => {
			currentPage = 1; // Reset to first page on filter change
			loadUsers();
		}, 500);
	}

	// Clear all filters
	function clearFilters() {
		searchQuery = '';
		couponFilter = '';
		currentPage = 1;
		loadUsers();
	}

	// Handle sort
	function handleSort(column: string) {
		if (sortBy === column) {
			sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
		} else {
			sortBy = column;
			sortOrder = 'asc';
		}
		loadUsers();
	}

	// Pagination
	function goToPage(page: number) {
		if (page >= 1 && page <= totalPages) {
			currentPage = page;
			loadUsers();
		}
	}

	// Get page numbers to display
	function getPageNumbers(): number[] {
		const pages: number[] = [];
		const maxPages = 5;
		let startPage = Math.max(1, currentPage - Math.floor(maxPages / 2));
		let endPage = Math.min(totalPages, startPage + maxPages - 1);

		if (endPage - startPage + 1 < maxPages) {
			startPage = Math.max(1, endPage - maxPages + 1);
		}

		for (let i = startPage; i <= endPage; i++) {
			pages.push(i);
		}

		return pages;
	}

	// Open ban dialog
	function openBanDialog(user: UserTableItem) {
		selectedUser = user;
		banReason = '';
		showBanDialog = true;
	}

	// Close ban dialog
	function closeBanDialog() {
		showBanDialog = false;
		selectedUser = null;
		banReason = '';
	}

	// Handle ban user
	async function handleBanUser() {
		if (!selectedUser || !banReason.trim()) {
			toast.error('Укажите причину бана');
			return;
		}

		if (banReason.trim().length < 3) {
			toast.error('Причина бана должна содержать минимум 3 символа');
			return;
		}

		isBanning = true;
		try {
			const response = await banUser(selectedUser.id, banReason.trim());
			toast.success(response.message);
			closeBanDialog();
			await loadUsers(); // Reload users list
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isBanning = false;
		}
	}

	onMount(() => {
		loadUsers();

		return () => {
			// Cancel any pending requests
			if (abortController) {
				abortController.abort();
			}
		};
	});
</script>

<div class="space-y-6">
	<!-- Header -->
	<div>
		<h2 class="text-2xl font-bold tracking-tight">Управление пользователями</h2>
		<p class="text-muted-foreground">Просмотр и управление пользователями платформы</p>
	</div>

	<!-- Search and Filter bar -->
	<Card>
		<CardContent class="pt-6">
			<div class="space-y-3">
				<div class="flex items-center gap-2">
					<div class="relative flex-1">
						<Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
						<Input
							placeholder="Поиск по имени пользователя или email..."
							bind:value={searchQuery}
							oninput={handleSearchInput}
							class="pl-9"
						/>
					</div>
					<div class="relative flex-1">
						<Tag class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
						<Input
							placeholder="Фильтр по купону..."
							bind:value={couponFilter}
							oninput={handleCouponFilterInput}
							class="pl-9"
						/>
					</div>
					{#if searchQuery || couponFilter}
						<Button variant="outline" size="icon" onclick={clearFilters}>
							<X class="h-4 w-4" />
						</Button>
					{/if}
				</div>
				{#if searchQuery || couponFilter}
					<div class="flex items-center gap-2 text-sm text-muted-foreground">
						<span>Активные фильтры:</span>
						{#if searchQuery}
							<Badge variant="secondary">Поиск: {searchQuery}</Badge>
						{/if}
						{#if couponFilter}
							<Badge variant="secondary">Купон: {couponFilter.toUpperCase()}</Badge>
						{/if}
					</div>
				{/if}
			</div>
		</CardContent>
	</Card>

	<!-- Error alert -->
	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Users table -->
	<Card>
		<CardHeader>
			<div class="flex items-center justify-between">
				<CardTitle>Пользователи</CardTitle>
				{#if totalCount > 0}
					<p class="text-sm text-muted-foreground">
						Показаны {startIndex}-{endIndex} из {totalCount}
					</p>
				{/if}
			</div>
		</CardHeader>
		<CardContent>
			{#if isLoading}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-8 w-8 animate-spin text-primary" />
				</div>
			{:else if users.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-muted-foreground">
						{searchQuery ? 'Пользователи по поиску не найдены' : 'Пользователи не найдены'}
					</p>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>
									<Button
										variant="ghost"
										size="sm"
										class="h-8 px-2"
										onclick={() => handleSort('username')}
									>
										Имя пользователя
										{#if sortBy === 'username'}
											{#if sortOrder === 'asc'}
												<ChevronUp class="ml-1 h-3 w-3" />
											{:else}
												<ChevronDown class="ml-1 h-3 w-3" />
											{/if}
										{/if}
									</Button>
								</TableHead>
								<TableHead class="text-right">
									<Button
										variant="ghost"
										size="sm"
										class="h-8 px-2"
										onclick={() => handleSort('balance')}
									>
										Баланс
										{#if sortBy === 'balance'}
											{#if sortOrder === 'asc'}
												<ChevronUp class="ml-1 h-3 w-3" />
											{:else}
												<ChevronDown class="ml-1 h-3 w-3" />
											{/if}
										{/if}
									</Button>
								</TableHead>
								<TableHead class="text-right">
									<Button
										variant="ghost"
										size="sm"
										class="h-8 px-2"
										onclick={() => {}}
									>
										Всего пополнено
									</Button>
								</TableHead>
								<TableHead class="text-right">
									<Button
										variant="ghost"
										size="sm"
										class="h-8 px-2"
										onclick={() => handleSort('total_spent')}
									>
										Всего потрачено
										{#if sortBy === 'total_spent'}
											{#if sortOrder === 'asc'}
												<ChevronUp class="ml-1 h-3 w-3" />
											{:else}
												<ChevronDown class="ml-1 h-3 w-3" />
											{/if}
										{/if}
									</Button>
								</TableHead>
								<TableHead>Применённые купоны</TableHead>
								<TableHead>
									<Button
										variant="ghost"
										size="sm"
										class="h-8 px-2"
										onclick={() => handleSort('created_at')}
									>
										Создан
										{#if sortBy === 'created_at'}
											{#if sortOrder === 'asc'}
												<ChevronUp class="ml-1 h-3 w-3" />
											{:else}
												<ChevronDown class="ml-1 h-3 w-3" />
											{/if}
										{/if}
									</Button>
								</TableHead>
								<TableHead>Статус</TableHead>
								<TableHead>Действия</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each users as user}
								<TableRow>
									<TableCell class="font-medium">{user.username}</TableCell>
									<TableCell class="text-right font-mono">
										{formatCurrency(user.balance)}
									</TableCell>
									<TableCell class="text-right font-mono">
										{formatCurrency(user.total_deposited)}
									</TableCell>
									<TableCell class="text-right font-mono">
										{formatCurrency(user.total_spent)}
									</TableCell>
									<TableCell>
										{#if user.applied_coupons.length > 0}
											<div class="flex flex-wrap gap-1">
												{#each user.applied_coupons as coupon}
													<Badge variant="outline" class="font-mono text-xs">
														{coupon}
													</Badge>
												{/each}
											</div>
										{:else}
											<span class="text-muted-foreground">Нет</span>
										{/if}
									</TableCell>
									<TableCell>{formatDate(user.created_at)}</TableCell>
									<TableCell>
										{#if user.is_banned}
											<Badge variant="destructive">Забанен</Badge>
										{:else}
											<Badge variant="default">Активен</Badge>
										{/if}
									</TableCell>
									<TableCell>
										{#if !user.is_banned}
											<Button
												variant="destructive"
												size="sm"
												onclick={() => openBanDialog(user)}
											>
												<Ban class="mr-1 h-3 w-3" />
												Ban
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
							Страница {currentPage} из {totalPages}
						</div>
						<div class="flex items-center gap-2">
							<Button
								variant="outline"
								size="sm"
								onclick={() => goToPage(currentPage - 1)}
								disabled={currentPage === 1}
							>
								<ChevronLeft class="h-4 w-4" />
								Предыдущая
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

							<Button
								variant="outline"
								size="sm"
								onclick={() => goToPage(currentPage + 1)}
								disabled={currentPage === totalPages}
							>
								Следующая
								<ChevronRight class="h-4 w-4" />
							</Button>
						</div>
					</div>
				{/if}
			{/if}
		</CardContent>
	</Card>

	<!-- Ban User Dialog -->
	<Dialog bind:open={showBanDialog}>
		<DialogContent>
			<DialogHeader>
				<DialogTitle>Забанить пользователя</DialogTitle>
				<DialogDescription>
					{#if selectedUser}
						Вы собираетесь забанить пользователя <strong>{selectedUser.username}</strong>.
						Укажите причину бана (минимум 3 символа).
					{/if}
				</DialogDescription>
			</DialogHeader>

			<div class="space-y-4">
				<div class="space-y-2">
					<Label for="ban-reason">Причина бана</Label>
					<Textarea
						id="ban-reason"
						bind:value={banReason}
						placeholder="Например: нарушение правил использования сервиса, попытка обхода системы..."
						rows={4}
						disabled={isBanning}
					/>
					<p class="text-sm text-muted-foreground">
						{banReason.length} / 500 символов
					</p>
				</div>
			</div>

			<DialogFooter>
				<Button variant="outline" onclick={closeBanDialog} disabled={isBanning}>
					Отмена
				</Button>
				<Button
					variant="destructive"
					onclick={handleBanUser}
					disabled={isBanning || banReason.trim().length < 3}
				>
					{#if isBanning}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						Бан...
					{:else}
						<Ban class="mr-2 h-4 w-4" />
						Забанить
					{/if}
				</Button>
			</DialogFooter>
		</DialogContent>
	</Dialog>
</div>
