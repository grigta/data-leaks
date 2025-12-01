<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
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
	import { Label } from '$lib/components/ui/label';
	import {
		FileText,
		Eye,
		UserCheck,
		Clock,
		CheckCircle,
		XCircle,
		Loader2,
		ChevronLeft,
		ChevronRight
	} from '@lucide/svelte';
	import {
		getTickets,
		getTicket,
		assignTicket,
		getUserTable,
		handleApiError,
		type TicketResponse,
		type WorkerResponse
	} from '$lib/api/client';
	import { formatDate, formatDateTime, truncate } from '$lib/utils';
	import { toast } from 'svelte-sonner';
	import { wsManager, TICKET_CREATED, TICKET_UPDATED } from '$lib/websocket/manager';

	// State
	let tickets = $state<TicketResponse[]>([]);
	let workers = $state<WorkerResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let statusFilter = $state<string | null>(null);
	let selectedTicket = $state<TicketResponse | null>(null);
	let showDetailsDialog = $state(false);
	let showAssignDialog = $state(false);
	let selectedWorkerId = $state<string>('');
	let isAssigning = $state(false);
	let currentPage = $state(1);
	let pageSize = $state(50);
	let totalCount = $state(0);

	// AbortController for canceling requests
	let abortController: AbortController | null = null;

	// Computed
	let totalPages = $derived(Math.ceil(totalCount / pageSize));
	let startIndex = $derived((currentPage - 1) * pageSize + 1);
	let endIndex = $derived(Math.min(currentPage * pageSize, totalCount));

	// Load tickets
	async function loadTickets() {
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
			const response = await getTickets({
				status_filter: statusFilter || undefined,
				limit: pageSize,
				offset
			});

			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				tickets = response.tickets;
				totalCount = response.total_count;
			}
		} catch (err: any) {
			if (!currentController.signal.aborted) {
				error = handleApiError(err);
				toast.error('Не удалось загрузить тикеты');
			}
		} finally {
			if (!currentController.signal.aborted) {
				isLoading = false;
			}
		}
	}

	// Load workers
	async function loadWorkers() {
		try {
			const response = await getUserTable();
			workers = response.users.filter((user: any) => user.worker_role === true) as WorkerResponse[];
		} catch (err: any) {
			console.error('Failed to load workers:', err);
		}
	}

	// Handle view details
	function handleViewDetails(ticket: TicketResponse) {
		selectedTicket = ticket;
		showDetailsDialog = true;
	}

	// Handle assign
	function handleAssign(ticket: TicketResponse) {
		selectedTicket = ticket;
		selectedWorkerId = '';
		if (workers.length === 0) {
			loadWorkers();
		}
		showAssignDialog = true;
	}

	// Confirm assign
	async function confirmAssign() {
		if (!selectedTicket || !selectedWorkerId) {
			toast.error('Please select a worker');
			return;
		}

		isAssigning = true;

		try {
			await assignTicket(selectedTicket.id, selectedWorkerId);
			toast.success('Тикет успешно назначен');
			showAssignDialog = false;
			selectedTicket = null;
			selectedWorkerId = '';
			loadTickets();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isAssigning = false;
		}
	}

	// Get status badge variant
	function getStatusBadgeVariant(status: string): 'default' | 'secondary' | 'destructive' {
		if (status === 'pending') return 'secondary';
		if (status === 'processing') return 'default';
		if (status === 'completed') return 'default';
		if (status === 'rejected') return 'destructive';
		return 'secondary';
	}

	// Get status icon
	function getStatusIcon(status: string) {
		if (status === 'pending') return Clock;
		if (status === 'processing') return Loader2;
		if (status === 'completed') return CheckCircle;
		if (status === 'rejected') return XCircle;
		return Clock;
	}

	// Go to page
	function goToPage(page: number) {
		if (page >= 1 && page <= totalPages) {
			currentPage = page;
			loadTickets();
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

	// WebSocket unsubscribe functions
	let unsubscribeTicketCreated: (() => void) | null = null;
	let unsubscribeTicketUpdated: (() => void) | null = null;

	// Setup WebSocket
	function setupWebSocket() {
		unsubscribeTicketCreated = wsManager.on(TICKET_CREATED, () => {
			console.log('New ticket created, reloading list');
			loadTickets();
		});

		unsubscribeTicketUpdated = wsManager.on(TICKET_UPDATED, () => {
			console.log('Ticket updated, reloading list');
			loadTickets();
		});
	}

	// Cleanup WebSocket
	function cleanupWebSocket() {
		// Unsubscribe from all WebSocket events
		if (unsubscribeTicketCreated) {
			unsubscribeTicketCreated();
			unsubscribeTicketCreated = null;
		}
		if (unsubscribeTicketUpdated) {
			unsubscribeTicketUpdated();
			unsubscribeTicketUpdated = null;
		}
	}

	onMount(() => {
		loadTickets();
		setupWebSocket();
	});

	onDestroy(() => {
		// Cancel any pending requests
		if (abortController) {
			abortController.abort();
		}

		cleanupWebSocket();
	});
</script>

<div class="space-y-6">
	<!-- Header -->
	<div>
		<h2 class="text-2xl font-bold tracking-tight">История тикетов</h2>
		<p class="text-muted-foreground">Просмотр и управление всеми тикетами ручного поиска SSN</p>
	</div>

	<!-- Filter buttons -->
	<div class="flex gap-2">
		<Button
			variant={statusFilter === null ? 'default' : 'outline'}
			size="sm"
			onclick={() => {
				statusFilter = null;
				currentPage = 1;
				loadTickets();
			}}
		>
			Все
		</Button>
		<Button
			variant={statusFilter === 'pending' ? 'default' : 'outline'}
			size="sm"
			onclick={() => {
				statusFilter = 'pending';
				currentPage = 1;
				loadTickets();
			}}
		>
			<Clock class="mr-1 h-3 w-3" />
			Ожидающие
		</Button>
		<Button
			variant={statusFilter === 'processing' ? 'default' : 'outline'}
			size="sm"
			onclick={() => {
				statusFilter = 'processing';
				currentPage = 1;
				loadTickets();
			}}
		>
			<Loader2 class="mr-1 h-3 w-3" />
			В обработке
		</Button>
		<Button
			variant={statusFilter === 'completed' ? 'default' : 'outline'}
			size="sm"
			onclick={() => {
				statusFilter = 'completed';
				currentPage = 1;
				loadTickets();
			}}
		>
			<CheckCircle class="mr-1 h-3 w-3" />
			Завершённые
		</Button>
		<Button
			variant={statusFilter === 'rejected' ? 'default' : 'outline'}
			size="sm"
			onclick={() => {
				statusFilter = 'rejected';
				currentPage = 1;
				loadTickets();
			}}
		>
			<XCircle class="mr-1 h-3 w-3" />
			Отклонённые
		</Button>
	</div>

	<!-- Error alert -->
	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Tickets table -->
	<Card>
		<CardHeader>
			<div class="flex items-center justify-between">
				<CardTitle>Тикеты</CardTitle>
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
			{:else if tickets.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-muted-foreground">
						{#if statusFilter}
							Тикеты {statusFilter} не найдены
						{:else}
							Тикеты не найдены
						{/if}
					</p>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>ID</TableHead>
								<TableHead>Клиент</TableHead>
								<TableHead>Имя</TableHead>
								<TableHead>Статус</TableHead>
								<TableHead>Работник</TableHead>
								<TableHead>Дата создания</TableHead>
								<TableHead class="text-right">Действия</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each tickets as ticket}
								{@const StatusIcon = getStatusIcon(ticket.status)}
								<TableRow>
									<TableCell class="font-mono text-xs">
										{truncate(ticket.id, 8)}
									</TableCell>
									<TableCell class="font-medium">{ticket.username}</TableCell>
									<TableCell>
										{ticket.firstname} {ticket.lastname}
									</TableCell>
									<TableCell>
										<Badge variant={getStatusBadgeVariant(ticket.status)}>
											<StatusIcon class="mr-1 h-3 w-3" />
											{ticket.status.charAt(0).toUpperCase() + ticket.status.slice(1)}
										</Badge>
									</TableCell>
									<TableCell>
										{#if ticket.worker_username}
											<span class="font-medium">{ticket.worker_username}</span>
										{:else}
											<span class="text-muted-foreground">Не назначен</span>
										{/if}
									</TableCell>
									<TableCell>{formatDateTime(ticket.created_at)}</TableCell>
									<TableCell class="text-right">
										<div class="flex justify-end gap-2">
											<Button
												variant="ghost"
												size="sm"
												onclick={() => handleViewDetails(ticket)}
											>
												<Eye class="h-4 w-4 mr-1" />
												Просмотр
											</Button>
											{#if (ticket.status === 'pending' || ticket.status === 'processing') && !ticket.worker_id}
												<Button
													variant="ghost"
													size="sm"
													onclick={() => handleAssign(ticket)}
												>
													<UserCheck class="h-4 w-4 mr-1" />
													Назначить
												</Button>
											{/if}
										</div>
									</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				</div>

				<!-- Pagination -->
				{#if totalPages > 1}
					<div class="mt-4 flex items-center justify-between border-t pt-4">
						<div class="text-sm text-muted-foreground">Страница {currentPage} из {totalPages}</div>
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
</div>

<!-- Details Dialog -->
<Dialog bind:open={showDetailsDialog}>
	<DialogContent class="max-w-2xl">
		<DialogHeader>
			<DialogTitle>Детали тикета</DialogTitle>
		</DialogHeader>
		<div class="space-y-4 py-4">
			{#if selectedTicket}
				<div class="grid grid-cols-2 gap-4">
					<div>
						<Label class="text-muted-foreground">ID тикета</Label>
						<p class="font-mono text-sm">{selectedTicket.id}</p>
					</div>
					<div>
						<Label class="text-muted-foreground">Статус</Label>
						<div class="mt-1">
							<Badge variant={getStatusBadgeVariant(selectedTicket.status)}>
								{selectedTicket.status.charAt(0).toUpperCase() + selectedTicket.status.slice(1)}
							</Badge>
						</div>
					</div>
					<div>
						<Label class="text-muted-foreground">Имя клиента</Label>
						<p class="text-sm">{selectedTicket.username}</p>
					</div>
					<div>
						<Label class="text-muted-foreground">Работник</Label>
						<p class="text-sm">
							{selectedTicket.worker_username || 'Не назначен'}
						</p>
					</div>
					<div>
						<Label class="text-muted-foreground">Имя</Label>
						<p class="text-sm">{selectedTicket.firstname}</p>
					</div>
					<div>
						<Label class="text-muted-foreground">Фамилия</Label>
						<p class="text-sm">{selectedTicket.lastname}</p>
					</div>
					<div class="col-span-2">
						<Label class="text-muted-foreground">Адрес</Label>
						<p class="text-sm">{selectedTicket.address}</p>
					</div>
					{#if selectedTicket.response_data}
						<div class="col-span-2">
							<Label class="text-muted-foreground">Данные ответа</Label>
							<pre class="mt-2 rounded-md bg-muted p-3 text-xs overflow-auto">{JSON.stringify(
									selectedTicket.response_data,
									null,
									2
								)}</pre>
						</div>
					{/if}
					<div>
						<Label class="text-muted-foreground">Создан</Label>
						<p class="text-sm">{formatDateTime(selectedTicket.created_at)}</p>
					</div>
					<div>
						<Label class="text-muted-foreground">Обновлён</Label>
						<p class="text-sm">{formatDateTime(selectedTicket.updated_at)}</p>
					</div>
				</div>

				<div class="flex justify-end">
					<Button
						variant="outline"
						onclick={() => {
							showDetailsDialog = false;
							selectedTicket = null;
						}}
					>
						Закрыть
					</Button>
				</div>
			{/if}
		</div>
	</DialogContent>
</Dialog>

<!-- Assignment Dialog -->
<Dialog bind:open={showAssignDialog}>
	<DialogContent>
		<DialogHeader>
			<DialogTitle>Назначить тикет работнику</DialogTitle>
		</DialogHeader>
		<div class="space-y-4 py-4">
			{#if selectedTicket}
				<div class="space-y-2">
					<div>
						<Label class="text-muted-foreground">ID тикета</Label>
						<p class="font-mono text-sm">{truncate(selectedTicket.id, 16)}</p>
					</div>
					<div>
						<Label class="text-muted-foreground">Клиент</Label>
						<p class="text-sm">{selectedTicket.username}</p>
					</div>
					<div>
						<Label class="text-muted-foreground">Имя</Label>
						<p class="text-sm">
							{selectedTicket.firstname}
							{selectedTicket.lastname}
						</p>
					</div>
				</div>

				<div class="space-y-2">
					<Label for="worker-select">Выберите работника</Label>
					<select
						id="worker-select"
						bind:value={selectedWorkerId}
						class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
					>
						<option value="">-- Выберите работника --</option>
						{#each workers as worker}
							<option value={worker.id}>
								{worker.username} ({worker.email})
							</option>
						{/each}
					</select>
				</div>

				<Alert>
					<AlertDescription>
						Назначение изменит статус на 'в обработке', если сейчас ожидает
					</AlertDescription>
				</Alert>
			{/if}

			<div class="flex gap-2">
				<Button
					class="flex-1"
					onclick={confirmAssign}
					disabled={isAssigning || !selectedWorkerId}
				>
					{#if isAssigning}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{/if}
					Назначить
				</Button>
				<Button
					variant="outline"
					class="flex-1"
					onclick={() => {
						showAssignDialog = false;
						selectedTicket = null;
						selectedWorkerId = '';
					}}
					disabled={isAssigning}
				>
					Отмена
				</Button>
			</div>
		</div>
	</DialogContent>
</Dialog>
