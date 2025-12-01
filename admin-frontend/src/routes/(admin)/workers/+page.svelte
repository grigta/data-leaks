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
	import { Users, UserMinus, Loader2, AlertCircle } from '@lucide/svelte';
	import {
		getWorkers,
		removeWorkerRole,
		handleApiError,
		type WorkerResponse
	} from '$lib/api/client';
	import { formatDate } from '$lib/utils';
	import { toast } from 'svelte-sonner';
	import { wsManager, WORKER_REQUEST_APPROVED } from '$lib/websocket/manager';

	// Feature flags
	const ENABLE_REMOVE_ROLE = false; // Backend endpoint not yet available

	// State
	let workers = $state<WorkerResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let selectedWorker = $state<WorkerResponse | null>(null);
	let showRemoveDialog = $state(false);
	let isRemoving = $state(false);

	// AbortController for canceling requests
	let abortController: AbortController | null = null;

	// Load workers
	async function loadWorkers() {
		// Cancel previous request if exists
		if (abortController) {
			abortController.abort();
		}

		abortController = new AbortController();
		const currentController = abortController;

		isLoading = true;
		error = '';

		try {
			const response = await getWorkers();

			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				workers = response.workers;
			}
		} catch (err: any) {
			if (!currentController.signal.aborted) {
				error = handleApiError(err);
				toast.error('Не удалось загрузить работников');
			}
		} finally {
			if (!currentController.signal.aborted) {
				isLoading = false;
			}
		}
	}

	// Handle remove worker role
	function handleRemoveWorkerRole(worker: WorkerResponse) {
		selectedWorker = worker;
		showRemoveDialog = true;
	}

	// Confirm remove worker role
	async function confirmRemoveWorkerRole() {
		if (!selectedWorker) return;

		isRemoving = true;

		try {
			// Note: This endpoint doesn't exist yet - show error message
			await removeWorkerRole(selectedWorker.id);
			toast.success(`Роль работника удалена у ${selectedWorker.username}`);
			showRemoveDialog = false;
			selectedWorker = null;
			loadWorkers();
		} catch (err: any) {
			// Show specific error message about missing backend implementation
			toast.error(
				'Эта функция требует реализации на бэкенде. Добавьте endpoint: PATCH /workers/{user_id}/remove-role'
			);
			console.error('Remove worker role error:', err);
		} finally {
			isRemoving = false;
		}
	}

	// WebSocket unsubscribe functions
	let unsubscribeWorkerRequestApproved: (() => void) | null = null;

	// Setup WebSocket
	function setupWebSocket() {
		// Register handler for worker_request_approved event to reload workers list
		unsubscribeWorkerRequestApproved = wsManager.on(WORKER_REQUEST_APPROVED, () => {
			console.log('Worker request approved, reloading workers list');
			loadWorkers();
		});
	}

	// Cleanup WebSocket
	function cleanupWebSocket() {
		// Unsubscribe from all WebSocket events
		if (unsubscribeWorkerRequestApproved) {
			unsubscribeWorkerRequestApproved();
			unsubscribeWorkerRequestApproved = null;
		}
	}

	onMount(() => {
		loadWorkers();
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
		<h2 class="text-2xl font-bold tracking-tight">Управление работниками</h2>
		<p class="text-muted-foreground">Управление аккаунтами и правами работников</p>
	</div>

	<!-- Error alert -->
	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Workers table -->
	<Card>
		<CardHeader>
			<div class="flex items-center justify-between">
				<CardTitle>
					<div class="flex items-center gap-2">
						<Users class="h-5 w-5" />
						Работники
					</div>
				</CardTitle>
			</div>
		</CardHeader>
		<CardContent>
			{#if isLoading}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-8 w-8 animate-spin text-primary" />
				</div>
			{:else if workers.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-muted-foreground">Работники не найдены</p>
					<p class="text-sm text-muted-foreground mt-2">
						Одобрите заявки на регистрацию работников, чтобы добавить их
					</p>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>Имя пользователя</TableHead>
								<TableHead>Email</TableHead>
								<TableHead>Дата создания</TableHead>
								<TableHead>Роль</TableHead>
								<TableHead class="text-right">Действия</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each workers as worker}
								<TableRow>
									<TableCell class="font-medium">{worker.username}</TableCell>
									<TableCell>{worker.email}</TableCell>
									<TableCell>{formatDate(worker.created_at)}</TableCell>
									<TableCell>
										<Badge variant="default">Работник</Badge>
										{#if worker.is_admin}
											<Badge variant="secondary" class="ml-1">Админ</Badge>
										{/if}
									</TableCell>
									<TableCell class="text-right">
										<Button
											variant="ghost"
											size="sm"
											onclick={() => handleRemoveWorkerRole(worker)}
											disabled={!ENABLE_REMOVE_ROLE}
											title={ENABLE_REMOVE_ROLE
												? "Удалить роль работника"
												: "Функция недоступна - требуется бэкенд endpoint"}
										>
											<UserMinus class="h-4 w-4 mr-1" />
											Удалить роль
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
</div>

<!-- Confirmation Dialog -->
<Dialog bind:open={showRemoveDialog}>
	<DialogContent>
		<DialogHeader>
			<DialogTitle>Удалить роль работника</DialogTitle>
		</DialogHeader>
		<div class="space-y-4 py-4">
			{#if selectedWorker}
				<Alert>
					<AlertCircle class="h-4 w-4" />
					<AlertDescription>
						Это удалит права работника у <strong>{selectedWorker.username}</strong>. Они больше не смогут получать доступ к функциям работника.
					</AlertDescription>
				</Alert>

				<p class="text-sm text-muted-foreground">
					<strong>Примечание:</strong> Эта функция требует реализации на бэкенде. Endpoint
					<code class="text-xs bg-muted px-1 py-0.5 rounded">
						PATCH /workers/{'{user_id}'}/remove-role
					</code>
					необходимо добавить в API бэкенда.
				</p>
			{/if}

			<div class="flex gap-2">
				<Button
					variant="destructive"
					class="flex-1"
					onclick={confirmRemoveWorkerRole}
					disabled={isRemoving}
				>
					{#if isRemoving}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{/if}
					Удалить роль
				</Button>
				<Button
					variant="outline"
					class="flex-1"
					onclick={() => {
						showRemoveDialog = false;
						selectedWorker = null;
					}}
					disabled={isRemoving}
				>
					Отмена
				</Button>
			</div>
		</div>
	</DialogContent>
</Dialog>
