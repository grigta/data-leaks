<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { dev } from '$app/environment';
	import { z } from 'zod';
	import {
		createManualSSNTicket,
		getMyTickets,
		moveTicketToOrder,
		getUnviewedTicketsCount,
		markTicketsAsViewed,
		type TicketResponse,
		type CreateManualSSNTicketRequest,
		handleApiError,
		getMaintenanceStatus
	} from '$lib/api/client';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Badge } from '$lib/components/ui/badge';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import FileText from '@lucide/svelte/icons/file-text';
	import Send from '@lucide/svelte/icons/send';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Clock from '@lucide/svelte/icons/clock';
	import CheckCircle from '@lucide/svelte/icons/check-circle';
	import XCircle from '@lucide/svelte/icons/x-circle';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Check from '@lucide/svelte/icons/check';
	import Copy from '@lucide/svelte/icons/copy';
	import Wrench from '@lucide/svelte/icons/wrench';
	import ShoppingCart from '@lucide/svelte/icons/shopping-cart';
	import { parseFullName } from '$lib/utils';
	import { t } from '$lib/i18n';
	import { toast } from 'svelte-sonner';
	import { wsManager, wsConnected, TICKET_UPDATED } from '$lib/websocket/client';
	import { user } from '$lib/stores/auth';
	import { MANUAL_SSN_COST } from '$lib/constants/pricing';
	import { unviewedTicketsCount, loadUnviewedTicketsCount } from '$lib/stores/tickets';

	// Utility Functions
	// Field labels mapping for response_data keys
	const fieldLabels: Record<string, string> = {
		ssn: 'SSN',
		dob: 'Дата рождения',
		date_of_birth: 'Дата рождения',
		phone: 'Телефон',
		email: 'Email',
		address: 'Адрес',
		city: 'Город',
		state: 'Штат',
		zip: 'ZIP код',
		age: 'Возраст',
		gender: 'Пол'
	};

	function getFieldLabel(key: string): string {
		return fieldLabels[key.toLowerCase()] || key;
	}

	function calculateProcessingMinutes(createdAt: string, updatedAt: string): number {
		try {
			const created = new Date(createdAt);
			const updated = new Date(updatedAt);
			const diffMs = updated.getTime() - created.getTime();

			if (diffMs <= 0) {
				return 0;
			}

			const diffMinutes = Math.ceil(diffMs / 60000);
			return diffMinutes >= 1 ? diffMinutes : 1;
		} catch (error) {
			console.error('Error calculating processing time:', error);
			return 0;
		}
	}

	async function copyToClipboard(text: string, label: string) {
		try {
			await navigator.clipboard.writeText(text);
			toast.success(`${label} скопировано в буфер обмена`);
		} catch (error) {
			console.error('Failed to copy:', error);
			toast.error('Ошибка при копировании');
		}
	}

	async function copyAllTicketData(ticket: TicketResponse) {
		const lines: string[] = [];

		// Add basic info
		lines.push(`Имя: ${ticket.firstname} ${ticket.lastname}`);
		lines.push(`Адрес: ${ticket.address}`);

		// Add response data fields
		if (ticket.response_data) {
			for (const [key, value] of Object.entries(ticket.response_data)) {
				if (key !== 'reason' && value) {
					const label = getFieldLabel(key);
					lines.push(`${label}: ${value}`);
				}
			}
		}

		const allText = lines.join('\n');
		await copyToClipboard(allText, 'Все данные');
	}

	// Validation Schema
	const ticketSchema = z.object({
		fullname: z.string().min(1, 'Full name is required'),
		address: z.string().min(1, 'Full address is required')
	});

	// State Variables
	let form = $state({
		fullname: '',
		address: ''
	});

	let errors = $state<{
		fullname?: string[];
		address?: string[];
	}>({});

	let isSubmitting = $state(false);
	let errorMessage = $state('');
	let successMessage = $state('');
	let myTickets = $state<TicketResponse[]>([]);
	let isLoadingTickets = $state(false);
	let unsubscribeTicketUpdate: (() => void) | null = null;
	let movingTickets = $state<Set<string>>(new Set());
	let isMovingAll = $state(false);
	let isMaintenanceMode = $state(false);
	let maintenanceMessage = $state<string | null>(null);
	let isCheckingMaintenance = $state(true);

	// Functions
	async function checkMaintenanceMode() {
		try {
			const status = await getMaintenanceStatus('manual_ssn');
			isMaintenanceMode = status.is_active;
			maintenanceMessage = status.message || null;
			isCheckingMaintenance = false;
		} catch (error: any) {
			console.error('[MANUAL-SSN] Error checking maintenance mode:', error);
			// On error, assume not in maintenance
			isMaintenanceMode = false;
			isCheckingMaintenance = false;
		}
	}

	function clearForm() {
		form.fullname = '';
		form.address = '';
		errors = {};
		errorMessage = '';
		successMessage = '';
	}

	async function handleSubmit(e: Event) {
		e.preventDefault();

		// Clear previous errors and messages
		errors = {};
		errorMessage = '';
		successMessage = '';

		// Check user balance
		if ($user && $user.balance < MANUAL_SSN_COST) {
			errorMessage = $t('search.manualSsn.insufficientBalance', {
				required: MANUAL_SSN_COST.toFixed(2),
				available: $user.balance.toFixed(2)
			});
			toast.error(errorMessage);
			return;
		}

		// Validate form with Zod
		const result = ticketSchema.safeParse(form);
		if (!result.success) {
			const fieldErrors = result.error.flatten().fieldErrors;
			errors.fullname = fieldErrors.fullname;
			errors.address = fieldErrors.address;
			return;
		}

		// Additional check for form.fullname
		if (!form.fullname || typeof form.fullname !== 'string') {
			errors.fullname = ['Please enter a valid full name'];
			return;
		}

		// Parse full name into first and last name
		const { firstname, lastname } = parseFullName(form.fullname);
		if (!firstname || !lastname) {
			errors.fullname = ['Please enter both first and last name (e.g., "John Doe")'];
			return;
		}

		isSubmitting = true;

		try {
			// Send to API with parsed names
			const response = await createManualSSNTicket({
				firstname,
				lastname,
				address: form.address
			});
			const translatedSuccess = $t('search.manualSsn.successMessage', { ticketId: response.id });
			toast.success(translatedSuccess);
			successMessage = translatedSuccess;
			clearForm();
			await loadMyTickets();
		} catch (error) {
			const message = handleApiError(error);
			errorMessage = message;
			toast.error(`Failed to create ticket: ${message}`);
		} finally {
			isSubmitting = false;
		}
	}

	async function loadMyTickets() {
		isLoadingTickets = true;
		try {
			const response = await getMyTickets({ limit: 50, offset: 0 });
			// Sort by created_at descending (newest first)
			myTickets = response.tickets.sort((a, b) =>
				new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
			);
			// Automatically mark completed tickets as viewed after loading
			await markCompletedTicketsAsViewed();
			// Reload unviewed count from store
			await loadUnviewedTicketsCount();
		} catch (error) {
			console.error('Failed to load tickets:', error);
			toast.error('Failed to load your requests');
		} finally {
			isLoadingTickets = false;
		}
	}

	async function markCompletedTicketsAsViewed() {
		const completedUnviewedTickets = myTickets.filter(
			t => t.status === 'completed' && !t.is_viewed
		);

		if (completedUnviewedTickets.length === 0) return;

		const ticketIds = completedUnviewedTickets.map(t => t.id);

		try {
			await markTicketsAsViewed(ticketIds);
			// Update local state
			myTickets = myTickets.map(t => {
				if (ticketIds.includes(t.id)) {
					return { ...t, is_viewed: true };
				}
				return t;
			});
			// Reload unviewed count from store
			await loadUnviewedTicketsCount();
		} catch (error) {
			console.error('Failed to mark tickets as viewed:', error);
		}
	}

	function getStatusBadgeVariant(status: string): 'default' | 'secondary' | 'destructive' {
		switch (status) {
			case 'pending':
				return 'secondary';
			case 'processing':
				return 'default';
			case 'completed':
				return 'default';
			case 'rejected':
				return 'destructive';
			default:
				return 'secondary';
		}
	}

	function getStatusIcon(status: string) {
		switch (status) {
			case 'pending':
				return Clock;
			case 'processing':
				return Loader2;
			case 'completed':
				return CheckCircle;
			case 'rejected':
				return XCircle;
			default:
				return Clock;
		}
	}

	function setupWebSocket() {
		// Register event handler for ticket updates
		// WebSocket connection is managed by the layout
		unsubscribeTicketUpdate = wsManager.on(TICKET_UPDATED, handleTicketUpdate);
		dev && console.log('[Manual SSN] WebSocket event handler registered');
	}

	function handleTicketUpdate(data: any) {
		dev && console.log('[Manual SSN] Ticket update received:', data);

		// Check if the updated ticket belongs to current user
		if ($user && data.user_id === $user.id) {
			// Reload tickets to show updated status
			loadMyTickets();
			toast.info(`Ticket updated: ${data.status}`);
		}
	}

	function cleanupWebSocket() {
		if (unsubscribeTicketUpdate) {
			unsubscribeTicketUpdate();
			dev && console.log('[Manual SSN] WebSocket event handler unregistered');
		}
	}

	async function handleMoveToOrder(ticketId: string) {
		movingTickets.add(ticketId);
		movingTickets = new Set(movingTickets); // Trigger reactivity

		try {
			await moveTicketToOrder(ticketId);
			toast.success('Запрос отправлен в корзину');

			// Remove ticket from local list
			myTickets = myTickets.filter(t => t.id !== ticketId);
		} catch (error) {
			const message = handleApiError(error);
			toast.error(`Ошибка при перемещении: ${message}`);
		} finally {
			movingTickets.delete(ticketId);
			movingTickets = new Set(movingTickets); // Trigger reactivity
		}
	}

	async function handleMoveAllCompletedToOrders() {
		const completedTickets = myTickets.filter(t => t.status === 'completed');
		if (completedTickets.length === 0) return;

		isMovingAll = true;
		let successCount = 0;
		let errorCount = 0;

		for (const ticket of completedTickets) {
			try {
				await moveTicketToOrder(ticket.id);
				successCount++;
				// Remove ticket from local list immediately
				myTickets = myTickets.filter(t => t.id !== ticket.id);
			} catch (error) {
				errorCount++;
				console.error(`Failed to move ticket ${ticket.id}:`, error);
			}
		}

		isMovingAll = false;

		if (successCount > 0) {
			toast.success(`Перенесено в корзину: ${successCount} ${successCount === 1 ? 'запрос' : 'запросов'}`);
		}
		if (errorCount > 0) {
			toast.error(`Не удалось перенести: ${errorCount} ${errorCount === 1 ? 'запрос' : 'запросов'}`);
		}
	}

	// Lifecycle
	onMount(() => {
		checkMaintenanceMode();
		loadMyTickets();
		setupWebSocket();
	});

	onDestroy(() => {
		cleanupWebSocket();
	});
</script>

<div class="container mx-auto max-w-7xl px-4 py-8">
	<!-- Two-column layout: Form on left, Tickets on right -->
	<div class="grid grid-cols-1 gap-6 lg:grid-cols-[400px_1fr]">
		<!-- Left Column: Submission Form -->
		<div class="lg:sticky lg:top-4 lg:self-start">
			<Card>
				<CardHeader>
					<div class="flex items-center gap-2">
						<FileText class="h-6 w-6" />
						<CardTitle>{$t('search.manualSsn.title')}</CardTitle>
					</div>
					<p class="text-sm text-muted-foreground">
						{$t('search.manualSsn.subtitle')}
					</p>
					<div class="mt-2 rounded-md bg-muted px-3 py-2">
						<p class="text-sm font-medium">
							{$t('search.manualSsn.costInfo', { cost: MANUAL_SSN_COST.toFixed(2) })}
						</p>
					</div>
				</CardHeader>
				<CardContent>
					{#if isCheckingMaintenance}
						<div class="flex justify-center items-center py-12">
							<Loader2 class="h-8 w-8 animate-spin" />
						</div>
					{:else if isMaintenanceMode}
						<div class="flex flex-col items-center justify-center py-8 gap-4">
							<div class="rounded-full bg-orange-100 p-4">
								<Wrench class="h-12 w-12 text-orange-600" />
							</div>
							<div class="text-center space-y-2">
								<h3 class="text-lg font-semibold">Технические работы</h3>
								<p class="text-sm text-muted-foreground">
									{maintenanceMessage || 'Сервис временно недоступен из-за проведения технических работ. Пожалуйста, попробуйте позже.'}
								</p>
							</div>
						</div>
					{:else}
						{#if errorMessage}
							<Alert variant="destructive" class="mb-4">
								<AlertCircle class="h-4 w-4" />
								<AlertDescription>{errorMessage}</AlertDescription>
							</Alert>
						{/if}

						{#if successMessage}
							<Alert class="mb-4">
								<CheckCircle class="h-4 w-4" />
								<AlertDescription>{successMessage}</AlertDescription>
							</Alert>
						{/if}

						<form onsubmit={handleSubmit} class="space-y-4">
						<!-- Full Name -->
						<div class="space-y-2">
							<Label for="fullname">{$t('search.manualSsn.fullName')}</Label>
							<Input
								id="fullname"
								type="text"
								bind:value={form.fullname}
								placeholder={$t('search.manualSsn.fullNamePlaceholder')}
								disabled={isSubmitting}
							/>
							{#if errors.fullname}
								<p class="text-sm text-destructive">{errors.fullname[0]}</p>
							{/if}
						</div>

						<!-- Address -->
						<div class="space-y-2">
							<Label for="address">{$t('search.manualSsn.address')}</Label>
							<Input
								id="address"
								type="text"
								bind:value={form.address}
								placeholder={$t('search.manualSsn.addressPlaceholder')}
								disabled={isSubmitting}
							/>
							{#if errors.address}
								<p class="text-sm text-destructive">{errors.address[0]}</p>
							{/if}
						</div>

						<div class="flex flex-col gap-2">
							<Button type="submit" disabled={isSubmitting} class="w-full">
								{#if isSubmitting}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									{$t('search.manualSsn.submitting')}
								{:else}
									<Send class="mr-2 h-4 w-4" />
									{$t('search.manualSsn.submitButton')}
								{/if}
							</Button>
							<p class="text-sm text-muted-foreground">
								{$t('search.manualSsn.teamNote')}
							</p>
						</div>
					</form>
					{/if}
				</CardContent>
			</Card>
		</div>

		<!-- Right Column: My Tickets -->
		<div class="space-y-4">
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-2">
					<h2 class="text-2xl font-bold">{$t('search.manualSsn.myRequests')}</h2>
					{#if $unviewedTicketsCount > 0}
						<Badge variant="destructive" class="text-sm">
							{$unviewedTicketsCount} new
						</Badge>
					{/if}
				</div>
				<div class="flex items-center gap-2">
					{#if myTickets.filter(t => t.status === 'completed').length > 0}
						<Button
							variant="default"
							size="sm"
							class="bg-green-600 hover:bg-green-700"
							onclick={handleMoveAllCompletedToOrders}
							disabled={isMovingAll || isLoadingTickets}
						>
							{#if isMovingAll}
								<Loader2 class="mr-1 h-4 w-4 animate-spin" />
								Переносим...
							{:else}
								<ShoppingCart class="mr-1 h-4 w-4" />
								Все в корзину ({myTickets.filter(t => t.status === 'completed').length})
							{/if}
						</Button>
					{/if}
					<Button variant="outline" size="sm" onclick={loadMyTickets} disabled={isLoadingTickets}>
						<RefreshCw class={`h-4 w-4 ${isLoadingTickets ? 'animate-spin' : ''}`} />
					</Button>
				</div>
			</div>

			{#if isLoadingTickets}
				<div class="flex items-center justify-center py-12">
					<Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
				</div>
			{:else if myTickets.length === 0}
				<Card>
					<CardContent class="py-12 text-center text-muted-foreground">
						<FileText class="mx-auto mb-4 h-12 w-12 opacity-50" />
						<p>{$t('search.manualSsn.noRequests')}</p>
					</CardContent>
				</Card>
			{:else}
				<!-- Tickets Table -->
				<Card>
					<CardContent class="p-0">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead class="w-[90px]"></TableHead>
									<TableHead class="w-[100px]">Статус</TableHead>
									<TableHead class="w-[180px]">Информация</TableHead>
									<TableHead class="hidden md:table-cell">Результат</TableHead>
									<TableHead class="w-[60px] hidden md:table-cell">Время</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each myTickets as ticket (ticket.id)}
									<TableRow class={ticket.status === 'completed' && !ticket.is_viewed ? 'bg-green-50 dark:bg-green-950/20' : ''}>
										<!-- Column 1: Actions -->
										<TableCell class="py-2 px-2">
											{#if ticket.status === 'completed'}
												<div class="flex items-center gap-1">
													<Button
														variant="outline"
														size="sm"
														class="h-8 w-8 p-0 border-green-500 bg-green-50 text-green-600 hover:bg-green-100 hover:text-green-700"
														onclick={() => handleMoveToOrder(ticket.id)}
														disabled={movingTickets.has(ticket.id)}
														title="Отправить в корзину"
													>
														{#if movingTickets.has(ticket.id)}
															<Loader2 class="h-4 w-4 animate-spin" />
														{:else}
															<Check class="h-4 w-4" />
														{/if}
													</Button>
													<Button
														variant="ghost"
														size="sm"
														class="h-8 w-8 p-0"
														onclick={() => copyAllTicketData(ticket)}
														title="Скопировать все данные"
													>
														<Copy class="h-4 w-4" />
													</Button>
												</div>
											{:else}
												<span class="text-xs text-muted-foreground">—</span>
											{/if}
										</TableCell>

										<!-- Column 2: Status -->
										<TableCell class="py-3 px-4">
											<Badge variant={getStatusBadgeVariant(ticket.status)} class="flex items-center gap-1 w-fit">
												<svelte:component
													this={getStatusIcon(ticket.status)}
													class={ticket.status === 'processing' ? 'h-3 w-3 animate-spin' : 'h-3 w-3'}
												/>
												<span class="text-xs">{$t(`search.manualSsn.status.${ticket.status}`)}</span>
											</Badge>
										</TableCell>

										<!-- Column 3: User Info -->
										<TableCell class="py-3 px-4">
											<!-- svelte-ignore a11y_click_events_have_key_events -->
											<!-- svelte-ignore a11y_no_static_element_interactions -->
											<div
												class="space-y-1 cursor-pointer hover:bg-muted/50 rounded p-1 transition-colors -m-1"
												onclick={() => copyToClipboard(`${ticket.firstname} ${ticket.lastname}, ${ticket.address}`, 'Информация')}
												title="Нажмите для копирования"
											>
												<p class="font-medium text-sm">{ticket.firstname} {ticket.lastname}</p>
												<p class="text-xs text-muted-foreground truncate max-w-[180px]" title={ticket.address}>
													{ticket.address}
												</p>
											</div>
										</TableCell>

										<!-- Column 4: Result (hidden on mobile) -->
										<TableCell class="py-2 px-3 hidden md:table-cell">
											{#if ticket.status === 'completed' && ticket.response_data}
												<!-- svelte-ignore a11y_click_events_have_key_events -->
												<!-- svelte-ignore a11y_no_static_element_interactions -->
												<div
													class="text-xs font-medium truncate cursor-pointer hover:bg-muted/50 rounded px-1 transition-colors"
													title="Нажмите для копирования"
													onclick={() => {
														const values = Object.entries(ticket.response_data || {})
															.filter(([k]) => k !== 'reason')
															.map(([, v]) => String(v))
															.join(' | ');
														copyToClipboard(values, 'Результат');
													}}
												>
													{Object.entries(ticket.response_data)
														.filter(([k]) => k !== 'reason')
														.slice(0, 3)
														.map(([, v]) => String(v))
														.join(' | ')}
												</div>
											{:else if ticket.status === 'pending'}
												<span class="text-xs text-muted-foreground">Ожидает</span>
											{:else if ticket.status === 'processing'}
												<span class="text-xs text-muted-foreground">
													{#if ticket.worker_username}
														{ticket.worker_username}
													{:else}
														В обработке
													{/if}
												</span>
											{:else if ticket.status === 'rejected'}
												<span class="text-xs text-destructive truncate">
													{ticket.response_data?.reason || 'Отклонено'}
												</span>
											{:else}
												<span class="text-xs text-muted-foreground">—</span>
											{/if}
										</TableCell>

										<!-- Column 5: Time (hidden on mobile) -->
										<TableCell class="py-2 px-2 hidden md:table-cell">
											{#if ticket.status === 'completed'}
												{@const minutes = calculateProcessingMinutes(ticket.created_at, ticket.updated_at)}
												{#if minutes > 0}
													<div class="flex items-center gap-1 text-xs text-muted-foreground">
														<Clock class="h-3 w-3" />
														<span>{minutes}m</span>
													</div>
												{:else}
													<span class="text-xs text-muted-foreground">—</span>
												{/if}
											{:else}
												<span class="text-xs text-muted-foreground">—</span>
											{/if}
										</TableCell>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					</CardContent>
				</Card>
			{/if}
		</div>
	</div>
</div>
