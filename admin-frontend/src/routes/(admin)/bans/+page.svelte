<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
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
		getBannedUsers,
		unbanUser,
		type BannedUserResponse,
		handleApiError
	} from '$lib/api/client';
	import { formatDate } from '$lib/utils';
	import { Search, Loader2, ChevronLeft, ChevronRight, UserX } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';

	// State
	let users = $state<BannedUserResponse[]>([]);
	let totalCount = $state(0);
	let currentPage = $state(1);
	let pageSize = $state(50);
	let searchQuery = $state('');
	let isLoading = $state(true);
	let error = $state('');
	let isUnbanning = $state<string | null>(null);

	// Debounced search
	let searchTimeout: ReturnType<typeof setTimeout> | null = null;

	// Computed values
	let totalPages = $derived(Math.ceil(totalCount / pageSize));
	let startIndex = $derived((currentPage - 1) * pageSize + 1);
	let endIndex = $derived(Math.min(currentPage * pageSize, totalCount));

	// Load banned users
	async function loadBannedUsers() {
		isLoading = true;
		error = '';

		try {
			const offset = (currentPage - 1) * pageSize;
			const response = await getBannedUsers({
				limit: pageSize,
				offset,
				search: searchQuery || undefined
			});

			users = response.users;
			totalCount = response.total_count;
		} catch (err: any) {
			error = handleApiError(err);
		} finally {
			isLoading = false;
		}
	}

	// Handle search input
	function handleSearchInput() {
		if (searchTimeout) {
			clearTimeout(searchTimeout);
		}

		searchTimeout = setTimeout(() => {
			currentPage = 1; // Reset to first page on search
			loadBannedUsers();
		}, 500);
	}

	// Handle unban user
	async function handleUnban(userId: string, username: string) {
		if (!confirm(`Вы уверены, что хотите разбанить пользователя ${username}?`)) {
			return;
		}

		isUnbanning = userId;

		try {
			const response = await unbanUser(userId);
			toast.success(response.message || `Пользователь ${username} успешно разбанен`);
			await loadBannedUsers(); // Reload list to reflect changes
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isUnbanning = null;
		}
	}

	// Pagination
	function goToPage(page: number) {
		if (page >= 1 && page <= totalPages) {
			currentPage = page;
			loadBannedUsers();
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

	onMount(() => {
		loadBannedUsers();
	});

	onDestroy(() => {
		if (searchTimeout !== null) {
			clearTimeout(searchTimeout);
			searchTimeout = null;
		}
	});
</script>

<div class="space-y-6">
	<!-- Header -->
	<div>
		<h2 class="text-2xl font-bold tracking-tight">Список банов</h2>
		<p class="text-muted-foreground">Управление забаненными пользователями</p>
	</div>

	<!-- Search -->
	<Card>
		<CardContent class="pt-6">
			<div class="relative">
				<Search class="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
				<Input
					placeholder="Поиск по имени пользователя..."
					class="pl-8"
					bind:value={searchQuery}
					oninput={handleSearchInput}
				/>
			</div>
		</CardContent>
	</Card>

	<!-- Error Alert -->
	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Users Table -->
	<Card>
		<CardHeader>
			<div class="flex items-center justify-between">
				<CardTitle>Забаненные пользователи</CardTitle>
				{#if !isLoading && totalCount > 0}
					<p class="text-sm text-muted-foreground">
						Показано {startIndex}-{endIndex} из {totalCount}
					</p>
				{/if}
			</div>
		</CardHeader>
		<CardContent>
			{#if isLoading}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
				</div>
			{:else if users.length === 0}
				<div class="text-center py-8">
					<p class="text-muted-foreground">
						{searchQuery ? 'Пользователи по поиску не найдены' : 'Забаненные пользователи не найдены'}
					</p>
				</div>
			{:else}
				<div class="rounded-md border">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>Имя пользователя</TableHead>
								<TableHead>Причина бана</TableHead>
								<TableHead>Дата бана</TableHead>
								<TableHead>Дата регистрации</TableHead>
								<TableHead class="text-right">Действия</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each users as user}
								<TableRow>
									<TableCell class="font-medium">{user.username}</TableCell>
									<TableCell>{user.ban_reason}</TableCell>
									<TableCell>{formatDate(user.banned_at)}</TableCell>
									<TableCell>{formatDate(user.created_at)}</TableCell>
									<TableCell class="text-right">
										<Button
											variant="outline"
											size="sm"
											disabled={isUnbanning === user.id}
											onclick={() => handleUnban(user.id, user.username)}
										>
											{#if isUnbanning === user.id}
												<Loader2 class="h-4 w-4 animate-spin mr-2" />
											{:else}
												<UserX class="h-4 w-4 mr-2" />
											{/if}
											Разбанить
										</Button>
									</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				</div>
			{/if}
		</CardContent>
	</Card>

	<!-- Pagination -->
	{#if totalPages > 1}
		<div class="flex items-center justify-center space-x-2">
			<Button
				variant="outline"
				size="sm"
				onclick={() => goToPage(currentPage - 1)}
				disabled={currentPage === 1}
			>
				<ChevronLeft class="h-4 w-4" />
				Назад
			</Button>

			{#each getPageNumbers() as page}
				<Button
					variant={currentPage === page ? 'default' : 'outline'}
					size="sm"
					onclick={() => goToPage(page)}
				>
					{page}
				</Button>
			{/each}

			<Button
				variant="outline"
				size="sm"
				onclick={() => goToPage(currentPage + 1)}
				disabled={currentPage === totalPages}
			>
				Вперёд
				<ChevronRight class="h-4 w-4" />
			</Button>
		</div>
	{/if}
</div>
