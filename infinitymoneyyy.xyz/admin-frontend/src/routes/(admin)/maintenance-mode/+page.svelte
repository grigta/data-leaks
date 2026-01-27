<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
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
		DialogTitle,
		DialogTrigger
	} from '$lib/components/ui/dialog';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import {
		Select,
		SelectContent,
		SelectItem,
		SelectTrigger,
		SelectValue
	} from '$lib/components/ui/select';
	import { Textarea } from '$lib/components/ui/textarea';
	import {
		getMaintenanceModes,
		createMaintenanceMode,
		updateMaintenanceMode,
		deleteMaintenanceMode,
		toggleMaintenanceMode,
		type MaintenanceModeResponse,
		type CreateMaintenanceModeRequest,
		type UpdateMaintenanceModeRequest,
		handleApiError
	} from '$lib/api/client';
	import { formatDate } from '$lib/utils';
	import { Settings, Edit, Trash2, ToggleLeft, ToggleRight, Plus, Loader2 } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';

	// Service names mapping
	const SERVICE_NAMES: Record<string, string> = {
		instant_ssn: 'Быстрый SSN',
		manual_ssn: 'Ручной SSN'
	};

	// State
	let maintenanceModes = $state<MaintenanceModeResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let showCreateDialog = $state(false);
	let showEditDialog = $state(false);
	let selectedMode = $state<MaintenanceModeResponse | null>(null);

	// AbortController for canceling requests
	let abortController: AbortController | null = null;

	// Form data
	let formData = $state<CreateMaintenanceModeRequest>({
		service_name: 'instant_ssn',
		is_active: false,
		message: ''
	});

	// Load maintenance modes
	async function loadMaintenanceModes() {
		// Cancel previous request if exists
		if (abortController) {
			abortController.abort();
		}

		abortController = new AbortController();
		const currentController = abortController;

		isLoading = true;
		error = '';

		try {
			const response = await getMaintenanceModes();

			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				maintenanceModes = response?.maintenance_modes ?? [];
			}
		} catch (err: any) {
			if (!currentController.signal.aborted) {
				console.error('Failed to load maintenance modes:', err);
				error = handleApiError(err);
				maintenanceModes = [];
			}
		} finally {
			if (!currentController.signal.aborted) {
				isLoading = false;
			}
		}
	}

	// Handle create maintenance mode
	async function handleCreate() {
		try {
			await createMaintenanceMode({
				service_name: formData.service_name,
				is_active: formData.is_active,
				message: formData.message || undefined
			});

			toast.success('Режим технических работ создан');
			showCreateDialog = false;
			resetForm();
			loadMaintenanceModes();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Handle update maintenance mode
	async function handleUpdate() {
		if (!selectedMode) return;

		try {
			await updateMaintenanceMode(selectedMode.service_name, {
				is_active: formData.is_active,
				message: formData.message || undefined
			});

			toast.success('Режим технических работ обновлён');
			showEditDialog = false;
			selectedMode = null;
			resetForm();
			loadMaintenanceModes();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Handle toggle maintenance mode
	async function handleToggle(mode: MaintenanceModeResponse) {
		try {
			await toggleMaintenanceMode(mode.service_name);
			toast.success(`Режим технических работ ${mode.is_active ? 'выключен' : 'включён'}`);
			loadMaintenanceModes();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Handle delete maintenance mode
	async function handleDelete(mode: MaintenanceModeResponse) {
		if (!confirm(`Удалить режим технических работ для сервиса "${SERVICE_NAMES[mode.service_name]}"?`)) {
			return;
		}

		try {
			await deleteMaintenanceMode(mode.service_name);
			toast.success('Режим технических работ удалён');
			loadMaintenanceModes();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Open edit dialog
	function openEditDialog(mode: MaintenanceModeResponse) {
		selectedMode = mode;
		formData = {
			service_name: mode.service_name,
			is_active: mode.is_active,
			message: mode.message || ''
		};
		showEditDialog = true;
	}

	// Reset form
	function resetForm() {
		formData = {
			service_name: 'instant_ssn',
			is_active: false,
			message: ''
		};
	}

	// Load on mount
	onMount(() => {
		loadMaintenanceModes();
	});
</script>

<div class="container py-8">
	<Card>
		<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-4">
			<div>
				<CardTitle class="text-2xl font-bold">Управление техническими работами</CardTitle>
				<p class="text-sm text-muted-foreground mt-1">
					Управление режимом технических работ для сервисов
				</p>
			</div>
			<Dialog bind:open={showCreateDialog}>
				<DialogTrigger>
					<Button onclick={() => { showCreateDialog = true; resetForm(); }}>
						<Plus class="mr-2 h-4 w-4" />
						Создать
					</Button>
				</DialogTrigger>
				<DialogContent>
					<DialogHeader>
						<DialogTitle>Создать режим технических работ</DialogTitle>
					</DialogHeader>
					<div class="space-y-4 py-4">
						<div class="space-y-2">
							<Label for="create-service">Сервис</Label>
							<Select bind:value={formData.service_name}>
								<SelectTrigger id="create-service">
									<SelectValue placeholder="Выберите сервис" />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="instant_ssn">Быстрый SSN</SelectItem>
									<SelectItem value="manual_ssn">Ручной SSN</SelectItem>
								</SelectContent>
							</Select>
						</div>
						<div class="flex items-center space-x-2">
							<Checkbox id="create-active" bind:checked={formData.is_active} />
							<Label for="create-active">Активен</Label>
						</div>
						<div class="space-y-2">
							<Label for="create-message">Сообщение (необязательно)</Label>
							<Textarea
								id="create-message"
								bind:value={formData.message}
								placeholder="Сообщение для пользователей"
								rows={3}
							/>
						</div>
					</div>
					<div class="flex justify-end gap-2">
						<Button variant="outline" onclick={() => showCreateDialog = false}>Отмена</Button>
						<Button onclick={handleCreate}>Создать</Button>
					</div>
				</DialogContent>
			</Dialog>
		</CardHeader>

		<CardContent>
			{#if error}
				<Alert variant="destructive" class="mb-4">
					<AlertDescription>{error}</AlertDescription>
				</Alert>
			{/if}

			{#if isLoading}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
				</div>
			{:else if maintenanceModes.length === 0}
				<div class="text-center py-8 text-muted-foreground">
					<Settings class="mx-auto h-12 w-12 mb-2 opacity-50" />
					<p>Нет настроенных режимов технических работ</p>
				</div>
			{:else}
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>Сервис</TableHead>
							<TableHead>Статус</TableHead>
							<TableHead>Сообщение</TableHead>
							<TableHead>Создан</TableHead>
							<TableHead>Обновлён</TableHead>
							<TableHead class="text-right">Действия</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each maintenanceModes as mode (mode.id)}
							<TableRow>
								<TableCell class="font-medium">
									{SERVICE_NAMES[mode.service_name] || mode.service_name}
								</TableCell>
								<TableCell>
									{#if mode.is_active}
										<Badge variant="destructive">Активен</Badge>
									{:else}
										<Badge variant="outline">Неактивен</Badge>
									{/if}
								</TableCell>
								<TableCell class="max-w-md">
									{#if mode.message}
										<span class="truncate block">{mode.message}</span>
									{:else}
										<span class="text-muted-foreground italic">Нет сообщения</span>
									{/if}
								</TableCell>
								<TableCell class="text-muted-foreground text-sm">
									{formatDate(mode.created_at)}
								</TableCell>
								<TableCell class="text-muted-foreground text-sm">
									{formatDate(mode.updated_at)}
								</TableCell>
								<TableCell class="text-right">
									<div class="flex justify-end gap-2">
										<Button
											variant="ghost"
											size="sm"
											onclick={() => openEditDialog(mode)}
										>
											<Edit class="h-4 w-4" />
										</Button>
										<Button
											variant="ghost"
											size="sm"
											onclick={() => handleToggle(mode)}
										>
											{#if mode.is_active}
												<ToggleRight class="h-4 w-4 text-green-500" />
											{:else}
												<ToggleLeft class="h-4 w-4 text-muted-foreground" />
											{/if}
										</Button>
										<Button
											variant="ghost"
											size="sm"
											onclick={() => handleDelete(mode)}
										>
											<Trash2 class="h-4 w-4 text-destructive" />
										</Button>
									</div>
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
			{/if}
		</CardContent>
	</Card>
</div>

<!-- Edit Dialog -->
<Dialog bind:open={showEditDialog}>
	<DialogContent>
		<DialogHeader>
			<DialogTitle>Редактировать режим технических работ</DialogTitle>
		</DialogHeader>
		<div class="space-y-4 py-4">
			<div class="space-y-2">
				<Label for="edit-service">Сервис</Label>
				<Input
					id="edit-service"
					value={selectedMode ? SERVICE_NAMES[selectedMode.service_name] : ''}
					disabled
				/>
			</div>
			<div class="flex items-center space-x-2">
				<Checkbox id="edit-active" bind:checked={formData.is_active} />
				<Label for="edit-active">Активен</Label>
			</div>
			<div class="space-y-2">
				<Label for="edit-message">Сообщение (необязательно)</Label>
				<Textarea
					id="edit-message"
					bind:value={formData.message}
					placeholder="Сообщение для пользователей"
					rows={3}
				/>
			</div>
		</div>
		<div class="flex justify-end gap-2">
			<Button variant="outline" onclick={() => showEditDialog = false}>Отмена</Button>
			<Button onclick={handleUpdate}>Обновить</Button>
		</div>
	</DialogContent>
</Dialog>
