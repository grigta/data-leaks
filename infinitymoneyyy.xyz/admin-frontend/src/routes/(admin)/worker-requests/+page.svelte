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
	import { UserCheck, UserX, Clock, CheckCircle, XCircle, Loader2, Copy } from '@lucide/svelte';
	import {
		getWorkerRequests,
		approveWorkerRequest,
		rejectWorkerRequest,
		handleApiError,
		type WorkerRequestResponse
	} from '$lib/api/client';
	import { formatDate, formatDateTime } from '$lib/utils';
	import { toast } from 'svelte-sonner';
	import { wsManager, WORKER_REQUEST_CREATED, WORKER_REQUEST_APPROVED, WORKER_REQUEST_REJECTED } from '$lib/websocket/manager';

	// State
	let requests = $state<WorkerRequestResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let statusFilter = $state<string | null>(null);
	let selectedRequest = $state<WorkerRequestResponse | null>(null);
	let showApproveDialog = $state(false);
	let showRejectDialog = $state(false);
	let isProcessing = $state(false);

	// AbortController for canceling requests
	let abortController: AbortController | null = null;

	// Load requests
	async function loadRequests() {
		// Cancel previous request if exists
		if (abortController) {
			abortController.abort();
		}

		abortController = new AbortController();
		const currentController = abortController;

		isLoading = true;
		error = '';

		try {
			const response = await getWorkerRequests({
				status_filter: statusFilter || undefined
			});

			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				requests = response.requests;
				// Sort by created_at desc (most recent first)
				requests.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
			}
		} catch (err: any) {
			if (!currentController.signal.aborted) {
				error = handleApiError(err);
				toast.error('Не удалось загрузить заявки работников');
			}
		} finally {
			if (!currentController.signal.aborted) {
				isLoading = false;
			}
		}
	}

	// Handle approve
	function handleApprove(request: WorkerRequestResponse) {
		selectedRequest = request;
		showApproveDialog = true;
	}

	// Confirm approve
	async function confirmApprove() {
		if (!selectedRequest) return;

		isProcessing = true;

		try {
			const response = await approveWorkerRequest(selectedRequest.id);
			toast.success(`Заявка работника одобрена для ${response.username}`, {
				description: `Код доступа: ${response.access_code}`
			});
			showApproveDialog = false;
			selectedRequest = null;
			loadRequests();
		} catch (err: any) {
			const errorMsg = handleApiError(err);
			toast.error('Не удалось одобрить заявку', {
				description: errorMsg
			});
		} finally {
			isProcessing = false;
		}
	}

	// Handle reject
	function handleReject(request: WorkerRequestResponse) {
		selectedRequest = request;
		showRejectDialog = true;
	}

	// Confirm reject
	async function confirmReject() {
		if (!selectedRequest) return;

		isProcessing = true;

		try {
			const response = await rejectWorkerRequest(selectedRequest.id);
			toast.success(`Заявка работника отклонена для ${response.username}`);
			showRejectDialog = false;
			selectedRequest = null;
			loadRequests();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isProcessing = false;
		}
	}

	// Copy access code
	async function copyAccessCode(code: string) {
		try {
			await navigator.clipboard.writeText(code);
			toast.success('Код доступа скопирован в буфер обмена');
		} catch {
			toast.error('Не удалось скопировать код доступа');
		}
	}

	// Get status badge variant
	function getStatusBadgeVariant(status: string): 'default' | 'secondary' | 'destructive' {
		if (status === 'pending') return 'secondary';
		if (status === 'approved') return 'default';
		if (status === 'rejected') return 'destructive';
		return 'secondary';
	}

	// WebSocket unsubscribe functions
	let unsubscribeWorkerRequestCreated: (() => void) | null = null;
	let unsubscribeWorkerRequestApproved: (() => void) | null = null;
	let unsubscribeWorkerRequestRejected: (() => void) | null = null;

	// Setup WebSocket
	function setupWebSocket() {
		// Register handlers for real-time updates
		unsubscribeWorkerRequestCreated = wsManager.on(WORKER_REQUEST_CREATED, () => {
			console.log('New worker request created, reloading list');
			loadRequests();
		});

		unsubscribeWorkerRequestApproved = wsManager.on(WORKER_REQUEST_APPROVED, () => {
			console.log('Worker request approved, reloading list');
			loadRequests();
		});

		unsubscribeWorkerRequestRejected = wsManager.on(WORKER_REQUEST_REJECTED, () => {
			console.log('Worker request rejected, reloading list');
			loadRequests();
		});
	}

	// Cleanup WebSocket
	function cleanupWebSocket() {
		// Unsubscribe from all WebSocket events
		if (unsubscribeWorkerRequestCreated) {
			unsubscribeWorkerRequestCreated();
			unsubscribeWorkerRequestCreated = null;
		}
		if (unsubscribeWorkerRequestApproved) {
			unsubscribeWorkerRequestApproved();
			unsubscribeWorkerRequestApproved = null;
		}
		if (unsubscribeWorkerRequestRejected) {
			unsubscribeWorkerRequestRejected();
			unsubscribeWorkerRequestRejected = null;
		}
	}

	onMount(() => {
		loadRequests();
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
		<h2 class="text-2xl font-bold tracking-tight">Заявки на регистрацию работников</h2>
		<p class="text-muted-foreground">Просмотр и одобрение заявок на регистрацию работников</p>
	</div>

	<!-- Filter buttons -->
	<div class="flex gap-2">
		<Button
			variant={statusFilter === null ? 'default' : 'outline'}
			size="sm"
			onclick={() => {
				statusFilter = null;
				loadRequests();
			}}
		>
			Все
		</Button>
		<Button
			variant={statusFilter === 'pending' ? 'default' : 'outline'}
			size="sm"
			onclick={() => {
				statusFilter = 'pending';
				loadRequests();
			}}
		>
			<Clock class="mr-1 h-3 w-3" />
			Ожидающие
		</Button>
		<Button
			variant={statusFilter === 'approved' ? 'default' : 'outline'}
			size="sm"
			onclick={() => {
				statusFilter = 'approved';
				loadRequests();
			}}
		>
			<CheckCircle class="mr-1 h-3 w-3" />
			Одобренные
		</Button>
		<Button
			variant={statusFilter === 'rejected' ? 'default' : 'outline'}
			size="sm"
			onclick={() => {
				statusFilter = 'rejected';
				loadRequests();
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

	<!-- Requests table -->
	<Card>
		<CardHeader>
			<CardTitle>Заявки на регистрацию</CardTitle>
		</CardHeader>
		<CardContent>
			{#if isLoading}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-8 w-8 animate-spin text-primary" />
				</div>
			{:else if requests.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-muted-foreground">
						{#if statusFilter}
							{statusFilter === 'pending' ? 'Ожидающих' : statusFilter === 'approved' ? 'Одобренных' : 'Отклонённых'} заявок не найдено
						{:else}
							Заявки на регистрацию не найдены
						{/if}
					</p>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>Имя пользователя</TableHead>
								<TableHead>Email</TableHead>
								<TableHead>Код доступа</TableHead>
								<TableHead>Статус</TableHead>
								<TableHead>Дата создания</TableHead>
								<TableHead class="text-right">Действия</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each requests as request}
								<TableRow>
									<TableCell class="font-medium">{request.username}</TableCell>
									<TableCell>{request.email}</TableCell>
									<TableCell class="font-mono text-xs">
										<div class="flex items-center gap-2">
											{request.access_code}
											<Button
												variant="ghost"
												size="icon"
												class="h-6 w-6"
												onclick={() => copyAccessCode(request.access_code)}
											>
												<Copy class="h-3 w-3" />
											</Button>
										</div>
									</TableCell>
									<TableCell>
										<Badge variant={getStatusBadgeVariant(request.status)}>
											{request.status.charAt(0).toUpperCase() + request.status.slice(1)}
										</Badge>
									</TableCell>
									<TableCell>{formatDateTime(request.created_at)}</TableCell>
									<TableCell class="text-right">
										<div class="flex justify-end gap-2">
											{#if request.status === 'pending'}
												<Button
													variant="ghost"
													size="sm"
													onclick={() => handleApprove(request)}
												>
													<UserCheck class="h-4 w-4 mr-1" />
													Одобрить
												</Button>
												<Button
													variant="ghost"
													size="sm"
													onclick={() => handleReject(request)}
												>
													<UserX class="h-4 w-4 mr-1 text-destructive" />
													Отклонить
												</Button>
											{:else}
												<span class="text-sm text-muted-foreground">
													{request.status.charAt(0).toUpperCase() + request.status.slice(1)}
												</span>
											{/if}
										</div>
									</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				</div>
			{/if}
		</CardContent>
	</Card>
</div>

<!-- Approve Dialog -->
<Dialog bind:open={showApproveDialog}>
	<DialogContent>
		<DialogHeader>
			<DialogTitle>Одобрить заявку работника</DialogTitle>
		</DialogHeader>
		<div class="space-y-4 py-4">
			{#if selectedRequest}
				<div class="space-y-2">
					<div>
						<span class="text-sm font-medium">Имя пользователя:</span>
						<span class="ml-2 text-sm">{selectedRequest.username}</span>
					</div>
					<div>
						<span class="text-sm font-medium">Email:</span>
						<span class="ml-2 text-sm">{selectedRequest.email}</span>
					</div>
				</div>

				<Alert>
					<AlertDescription>
						Это создаст аккаунт работника с аутентификацией администратора, но с ограничением доступа только к endpoints работников.
					</AlertDescription>
				</Alert>
			{/if}

			<div class="flex gap-2">
				<Button class="flex-1" onclick={confirmApprove} disabled={isProcessing}>
					{#if isProcessing}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{/if}
					Одобрить
				</Button>
				<Button
					variant="outline"
					class="flex-1"
					onclick={() => {
						showApproveDialog = false;
						selectedRequest = null;
					}}
					disabled={isProcessing}
				>
					Отмена
				</Button>
			</div>
		</div>
	</DialogContent>
</Dialog>

<!-- Reject Dialog -->
<Dialog bind:open={showRejectDialog}>
	<DialogContent>
		<DialogHeader>
			<DialogTitle>Отклонить заявку работника</DialogTitle>
		</DialogHeader>
		<div class="space-y-4 py-4">
			{#if selectedRequest}
				<div class="space-y-2">
					<div>
						<span class="text-sm font-medium">Имя пользователя:</span>
						<span class="ml-2 text-sm">{selectedRequest.username}</span>
					</div>
					<div>
						<span class="text-sm font-medium">Email:</span>
						<span class="ml-2 text-sm">{selectedRequest.email}</span>
					</div>
				</div>

				<Alert variant="destructive">
					<AlertDescription>
						Это отклонит заявку на регистрацию. Пользователю нужно будет зарегистрироваться заново.
					</AlertDescription>
				</Alert>
			{/if}

			<div class="flex gap-2">
				<Button variant="destructive" class="flex-1" onclick={confirmReject} disabled={isProcessing}>
					{#if isProcessing}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{/if}
					Отклонить
				</Button>
				<Button
					variant="outline"
					class="flex-1"
					onclick={() => {
						showRejectDialog = false;
						selectedRequest = null;
					}}
					disabled={isProcessing}
				>
					Отмена
				</Button>
			</div>
		</div>
	</DialogContent>
</Dialog>
