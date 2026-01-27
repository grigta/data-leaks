<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Label } from '$lib/components/ui/label';
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
	import { FileText, CheckCircle, XCircle, Clock, Loader2, AlertCircle, Info } from '@lucide/svelte';
	import {
		getTickets,
		getTicket,
		updateTicket,
		moveTicketToOrder,
		getUnassignedTickets,
		claimTicket,
		handleApiError,
		type TicketResponse,
		type MoveTicketToOrderResponse
	} from '$lib/api/client';
	import {
		formatDate,
		formatDateTime,
		truncate,
		calculateProcessingTime,
		calculateWaitingTime
	} from '$lib/utils';
	import { toast } from 'svelte-sonner';
	import { wsManager, TICKET_CREATED, TICKET_UPDATED } from '$lib/websocket/manager';
	import { username } from '$lib/stores/auth';

	// State
	let tickets = $state<TicketResponse[]>([]);
	let unassignedTickets = $state<TicketResponse[]>([]);
	let activeTab = $state<'my' | 'available'>('my');
	let isLoading = $state(true);
	let isLoadingUnassigned = $state(false);
	let error = $state('');
	let statusFilter = $state<string>('pending');
	let selectedTicket = $state<TicketResponse | null>(null);
	let showProcessDialog = $state(false);
	let showViewDialog = $state(false);
	let isProcessing = $state(false);
	let responseData = $state<string>('');
	let newStatus = $state<string>('completed');
	let movingTicketId = $state<string | null>(null);
	let claimingTicketId = $state<string | null>(null);

	// AbortController for canceling requests
	let abortController: AbortController | null = null;

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
			const response = await getTickets({
				status_filter: statusFilter || undefined
			});

			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				// Backend automatically filters to show only tickets assigned to current worker
				tickets = response.tickets;
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

	// Load unassigned tickets
	async function loadUnassignedTickets() {
		isLoadingUnassigned = true;
		error = '';

		try {
			const response = await getUnassignedTickets({ limit: 50 });
			unassignedTickets = response.tickets;
		} catch (err: any) {
			error = handleApiError(err);
			toast.error('Не удалось загрузить доступные тикеты');
		} finally {
			isLoadingUnassigned = false;
		}
	}

	// Claim ticket
	async function handleClaimTicket(ticketId: string) {
		claimingTicketId = ticketId;

		try {
			await claimTicket(ticketId);
			toast.success('Тикет успешно взят');

			// Remove from unassigned list
			unassignedTickets = unassignedTickets.filter(t => t.id !== ticketId);

			// Reload my tickets
			if (activeTab === 'my') {
				await loadTickets();
			}
		} catch (err: any) {
			const errorMsg = handleApiError(err);
			if (errorMsg.includes('already assigned')) {
				toast.error('Этот тикет уже взят другим работником');
				// Reload unassigned tickets
				await loadUnassignedTickets();
			} else {
				toast.error('Не удалось взять тикет');
			}
		} finally {
			claimingTicketId = null;
		}
	}

	// Handle process
	function handleProcess(ticket: TicketResponse) {
		selectedTicket = ticket;
		responseData = '';
		newStatus = 'completed';
		showProcessDialog = true;
	}

	// Handle view
	function handleView(ticket: TicketResponse) {
		selectedTicket = ticket;
		showViewDialog = true;
	}

	// Confirm process
	async function confirmProcess() {
		if (!selectedTicket) return;

		if (!responseData.trim()) {
			toast.error('Введите данные ответа');
			return;
		}

		isProcessing = true;

		try {
			// Try to parse as JSON, otherwise use as plain text
			let parsedData: any;
			try {
				parsedData = JSON.parse(responseData);
			} catch {
				parsedData = { data: responseData };
			}

			await updateTicket(selectedTicket.id, {
				status: newStatus,
				response_data: parsedData
			});

			toast.success('Тикет успешно обновлён');
			showProcessDialog = false;
			selectedTicket = null;
			responseData = '';
			loadTickets();
		} catch (err: any) {
			const errorMsg = handleApiError(err);
			toast.error('Не удалось обновить тикет', {
				description: errorMsg
			});
		} finally {
			isProcessing = false;
		}
	}

	// Handle move to order
	async function handleMoveToOrder(ticket: TicketResponse) {
		if (!ticket.id) return;

		movingTicketId = ticket.id;

		try {
			await moveTicketToOrder(ticket.id);
			toast.success('Тикет успешно перемещён в заказы');
			// Remove ticket from local state
			tickets = tickets.filter((t) => t.id !== ticket.id);
		} catch (err: any) {
			const errorMsg = handleApiError(err);
			toast.error('Не удалось переместить тикет', {
				description: errorMsg
			});
		} finally {
			movingTicketId = null;
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
		// Load tickets based on active tab
		if (activeTab === 'my') {
			loadTickets();
		} else {
			loadUnassignedTickets();
		}
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
		<div class="flex items-center gap-3">
			<h2 class="text-2xl font-bold tracking-tight">Ручная обработка SSN</h2>
			{#if $username}
				<Badge variant="outline">Работник: {$username}</Badge>
			{/if}
		</div>
		<p class="text-muted-foreground">Обработка назначенных тикетов для ручного поиска SSN</p>
	</div>

	<!-- Info alert -->
	<Alert>
		<Info class="h-4 w-4" />
		<AlertDescription>
			{#if activeTab === 'my'}
				Вы просматриваете назначенные вам тикеты. Выполните поиск вручную и предоставьте полную информацию (fullz) в ответе.
			{:else}
				Вы просматриваете доступные тикеты. Нажмите "Взять", чтобы назначить тикет себе.
			{/if}
		</AlertDescription>
	</Alert>

	<!-- Tabs -->
	<div class="flex gap-2 border-b">
		<Button
			variant={activeTab === 'my' ? 'default' : 'ghost'}
			size="sm"
			class="rounded-b-none"
			onclick={() => {
				activeTab = 'my';
				loadTickets();
			}}
		>
			Мои тикеты
			{#if activeTab === 'my' && tickets.filter(t => t.status === 'pending').length > 0}
				<Badge variant="destructive" class="ml-2">
					{tickets.filter(t => t.status === 'pending').length}
				</Badge>
			{/if}
		</Button>
		<Button
			variant={activeTab === 'available' ? 'default' : 'ghost'}
			size="sm"
			class="rounded-b-none"
			onclick={() => {
				activeTab = 'available';
				loadUnassignedTickets();
			}}
		>
			Доступные тикеты
			{#if activeTab === 'available' && unassignedTickets.length > 0}
				<Badge variant="secondary" class="ml-2">
					{unassignedTickets.length}
				</Badge>
			{/if}
		</Button>
	</div>

	<!-- Filter buttons for My Tickets tab -->
	{#if activeTab === 'my'}
	<div class="flex gap-2">
		<Button
			variant={statusFilter === 'pending' ? 'default' : 'outline'}
			size="sm"
			onclick={() => {
				statusFilter = 'pending';
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
				loadTickets();
			}}
		>
			<XCircle class="mr-1 h-3 w-3" />
			Отклонённые
		</Button>
	</div>
	{/if}

	<!-- Error alert -->
	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- My Tickets grid -->
	{#if activeTab === 'my'}
	{#if isLoading}
		<div class="flex items-center justify-center py-12">
			<Loader2 class="h-8 w-8 animate-spin text-primary" />
		</div>
	{:else if tickets.length === 0}
		<Card>
			<CardContent class="py-12">
				<div class="flex flex-col items-center justify-center text-center">
					<FileText class="h-12 w-12 text-muted-foreground mb-4" />
					<p class="text-muted-foreground">
						{#if statusFilter === 'pending'}
							Нет ожидающих тикетов, назначенных вам
						{:else if statusFilter === 'processing'}
							Нет тикетов в обработке
						{:else if statusFilter === 'completed'}
							Нет завершённых тикетов
						{:else if statusFilter === 'rejected'}
							Нет отклонённых тикетов
						{:else}
							Нет тикетов, назначенных вам
						{/if}
					</p>
				</div>
			</CardContent>
		</Card>
	{:else}
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
			{#each tickets as ticket}
				{@const StatusIcon = getStatusIcon(ticket.status)}
				<Card class="flex flex-col h-full hover:shadow-md transition-shadow">
					<CardHeader class="pb-3">
						<div class="flex items-start justify-between">
							<div class="flex-1">
								<p class="text-xs text-muted-foreground font-mono mb-1">
									{truncate(ticket.id, 12)}
								</p>
								<p class="text-sm font-medium text-muted-foreground">
									{ticket.username}
								</p>
							</div>
							<Badge variant={getStatusBadgeVariant(ticket.status)} class="ml-2">
								<StatusIcon class="mr-1 h-3 w-3" />
								{ticket.status === 'pending'
									? 'Ожидает'
									: ticket.status === 'processing'
										? 'В работе'
										: ticket.status === 'completed'
											? 'Завершён'
											: 'Отклонён'}
							</Badge>
						</div>
					</CardHeader>
					<CardContent class="flex-1 space-y-3">
						<!-- User info -->
						<div>
							<p class="font-semibold text-base">
								{ticket.firstname}
								{ticket.lastname}
							</p>
							<p class="text-sm text-muted-foreground mt-1">
								{truncate(ticket.address, 50)}
							</p>
						</div>

						<!-- Response data preview -->
						{#if ticket.response_data}
							<div class="pt-2 border-t">
								<p class="text-xs text-muted-foreground mb-1">Данные ответа:</p>
								<p class="text-xs font-mono text-muted-foreground">
									{truncate(JSON.stringify(ticket.response_data), 100)}
								</p>
							</div>
						{/if}

						<!-- Time display -->
						{#if ticket.status === 'completed' || ticket.status === 'rejected'}
							<!-- Show processing time for completed/rejected tickets -->
							<div class="flex items-center gap-2 text-xs text-muted-foreground pt-2">
								<Clock class="h-3 w-3" />
								<span
									>Время обработки: {calculateProcessingTime(
										ticket.created_at,
										ticket.updated_at
									)}</span
								>
							</div>
						{:else}
							<!-- Show waiting time for pending/processing tickets -->
							<div class="flex items-center gap-2 text-xs text-muted-foreground pt-2">
								<Clock class="h-3 w-3" />
								<span>Время ожидания: {calculateWaitingTime(ticket.created_at)}</span>
							</div>
						{/if}
					</CardContent>
					<div class="border-t p-4 flex gap-2">
						{#if ticket.status === 'completed'}
							<Button
								size="sm"
								class="flex-1"
								onclick={() => handleMoveToOrder(ticket)}
								disabled={movingTicketId === ticket.id}
							>
								{#if movingTicketId === ticket.id}
									<Loader2 class="mr-1 h-3 w-3 animate-spin" />
								{/if}
								Отправить в корзину
							</Button>
							<Button size="sm" variant="ghost" onclick={() => handleView(ticket)}>
								Просмотр
							</Button>
						{:else if ticket.status === 'pending' || ticket.status === 'processing'}
							<Button size="sm" class="flex-1" onclick={() => handleProcess(ticket)}>
								<FileText class="h-4 w-4 mr-1" />
								Обработать
							</Button>
						{:else}
							<Button size="sm" class="flex-1" variant="outline" onclick={() => handleView(ticket)}>
								Просмотр
							</Button>
						{/if}
					</div>
				</Card>
			{/each}
		</div>
	{/if}
	{/if}

	<!-- Available Tickets grid -->
	{#if activeTab === 'available'}
	{#if isLoadingUnassigned}
		<div class="flex items-center justify-center py-12">
			<Loader2 class="h-8 w-8 animate-spin text-primary" />
		</div>
	{:else if unassignedTickets.length === 0}
		<Card>
			<CardContent class="py-12">
				<div class="flex flex-col items-center justify-center text-center">
					<FileText class="h-12 w-12 text-muted-foreground mb-4" />
					<p class="text-muted-foreground">
						Нет доступных тикетов для взятия
					</p>
				</div>
			</CardContent>
		</Card>
	{:else}
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
			{#each unassignedTickets as ticket}
				{@const StatusIcon = getStatusIcon(ticket.status)}
				<Card class="flex flex-col h-full hover:shadow-md transition-shadow">
					<CardHeader class="pb-3">
						<div class="flex items-start justify-between">
							<div class="flex-1">
								<p class="text-xs text-muted-foreground font-mono mb-1">
									{truncate(ticket.id, 12)}
								</p>
								<p class="text-sm font-medium text-muted-foreground">
									{ticket.username}
								</p>
							</div>
							<Badge variant="secondary">
								<Clock class="mr-1 h-3 w-3" />
								Доступен
							</Badge>
						</div>
					</CardHeader>
					<CardContent class="flex-1 space-y-3">
						<!-- User info -->
						<div>
							<p class="font-semibold text-base">
								{ticket.firstname}
								{ticket.lastname}
							</p>
							<p class="text-sm text-muted-foreground mt-1">
								{truncate(ticket.address, 50)}
							</p>
						</div>

						<!-- Waiting time -->
						<div class="flex items-center gap-2 text-xs text-muted-foreground pt-2">
							<Clock class="h-3 w-3" />
							<span>Время ожидания: {calculateWaitingTime(ticket.created_at)}</span>
						</div>

						<!-- Claim button -->
						<Button
							class="w-full mt-2"
							size="sm"
							disabled={claimingTicketId === ticket.id}
							onclick={() => handleClaimTicket(ticket.id)}
						>
							{#if claimingTicketId === ticket.id}
								<Loader2 class="mr-2 h-3 w-3 animate-spin" />
								Беру...
							{:else}
								Взять тикет
							{/if}
						</Button>
					</CardContent>
				</Card>
			{/each}
		</div>
	{/if}
	{/if}
</div>

<!-- Process Dialog -->
<Dialog bind:open={showProcessDialog}>
	<DialogContent class="max-w-2xl">
		<DialogHeader>
			<DialogTitle>Обработать тикет</DialogTitle>
		</DialogHeader>
		<div class="space-y-4 py-4">
			{#if selectedTicket}
				<div class="grid grid-cols-2 gap-4 pb-4 border-b">
					<div>
						<Label class="text-muted-foreground">ID тикета</Label>
						<p class="font-mono text-sm">{truncate(selectedTicket.id, 16)}</p>
					</div>
					<div>
						<Label class="text-muted-foreground">Имя пользователя клиента</Label>
						<p class="text-sm">{selectedTicket.username}</p>
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
						<Label class="text-muted-foreground">Полный адрес</Label>
						<p class="text-sm">{selectedTicket.address}</p>
					</div>
				</div>

				<Alert>
					<AlertCircle class="h-4 w-4" />
					<AlertDescription>
						Выполните ручной поиск SSN, используя указанную выше информацию, и предоставьте полные данные fullz ниже.
					</AlertDescription>
				</Alert>

				<div class="space-y-2">
					<Label for="response-data">Полная информация (Fullz)</Label>
					<Textarea
						id="response-data"
						bind:value={responseData}
						placeholder="Введите полные данные записи SSN (SSN, дата рождения, телефон, email и т.д.)&#10;&#10;Вы можете ввести структурированные данные JSON или простой текст."
						rows={12}
						class="font-mono text-sm"
					/>
					<p class="text-xs text-muted-foreground">
						Подсказка: Вы можете ввести структурированные данные JSON или простой текст. Клиент получит эту информацию. ({responseData.length} символов)
					</p>
				</div>

				<div class="space-y-2">
					<Label for="status-select">Статус</Label>
					<select
						id="status-select"
						bind:value={newStatus}
						class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
					>
						<option value="completed">Завершено</option>
						<option value="rejected">Отклонено (поиск не удался)</option>
					</select>
				</div>
			{/if}

			<div class="flex gap-2">
				<Button
					class="flex-1"
					onclick={confirmProcess}
					disabled={isProcessing || !responseData.trim()}
				>
					{#if isProcessing}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{/if}
					Отправить
				</Button>
				<Button
					variant="outline"
					class="flex-1"
					onclick={() => {
						showProcessDialog = false;
						selectedTicket = null;
						responseData = '';
					}}
					disabled={isProcessing}
				>
					Отмена
				</Button>
			</div>
		</div>
	</DialogContent>
</Dialog>

<!-- View Dialog -->
<Dialog bind:open={showViewDialog}>
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
					<div class="col-span-2">
						<Label class="text-muted-foreground">Адрес</Label>
						<p class="text-sm">{selectedTicket.address}</p>
					</div>
					{#if selectedTicket.response_data}
						<div class="col-span-2">
							<Label class="text-muted-foreground">Данные ответа</Label>
							<pre class="mt-2 rounded-md bg-muted p-3 text-xs overflow-auto max-h-64">{JSON.stringify(
									selectedTicket.response_data,
									null,
									2
								)}</pre>
						</div>
					{/if}
					<div>
						<Label class="text-muted-foreground">Завершено</Label>
						<p class="text-sm">{formatDateTime(selectedTicket.updated_at)}</p>
					</div>
				</div>

				<div class="flex justify-end">
					<Button
						variant="outline"
						onclick={() => {
							showViewDialog = false;
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
