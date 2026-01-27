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
	import {
		getCustomPricing,
		createCustomPricing,
		updateCustomPricing,
		deleteCustomPricing,
		toggleCustomPricing,
		type CustomPricingResponse,
		type CreateCustomPricingRequest,
		type UpdateCustomPricingRequest,
		type UserTableItem,
		handleApiError
	} from '$lib/api/client';
	import UserSearchInput from '$lib/components/UserSearchInput.svelte';
	import { formatDate } from '$lib/utils';
	import { DollarSign, Edit, Trash2, ToggleLeft, ToggleRight, Plus, Loader2, Search } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';

	// Service names mapping
	const SERVICE_NAMES: Record<string, string> = {
		instant_ssn: 'Быстрый SSN',
		manual_ssn: 'Ручной SSN'
	};

	// State
	let customPricing = $state<CustomPricingResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let showCreateDialog = $state(false);
	let showEditDialog = $state(false);
	let selectedPricing = $state<CustomPricingResponse | null>(null);

	// Filters
	let filterAccessCode = $state('');
	let filterServiceName = $state('');
	let filterIsActive = $state<string>('');
	let filterUser = $state<UserTableItem | null>(null);

	// AbortController for canceling requests
	let abortController: AbortController | null = null;

	// Form data
	let formData = $state<CreateCustomPricingRequest>({
		access_code: '',
		service_name: 'instant_ssn',
		price: '2.00',
		is_active: true
	});

	// Input mode toggle for create dialog
	let inputMode = $state<'access_code' | 'user'>('access_code');
	let selectedUser = $state<UserTableItem | null>(null);

	// Load custom pricing
	async function loadCustomPricing() {
		// Cancel previous request if exists
		if (abortController) {
			abortController.abort();
		}

		abortController = new AbortController();
		const currentController = abortController;

		isLoading = true;
		error = '';

		try {
			const params: any = {};
			if (filterAccessCode) params.access_code = filterAccessCode;
			if (filterUser) params.user_id = filterUser.id;
			if (filterServiceName) params.service_name = filterServiceName;
			// Convert string value to boolean or undefined
			if (filterIsActive === 'true') {
				params.is_active = true;
			} else if (filterIsActive === 'false') {
				params.is_active = false;
			}
			// If filterIsActive is empty string, don't add it to params

			const response = await getCustomPricing(params);

			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				customPricing = response?.custom_pricing ?? [];
			}
		} catch (err: any) {
			if (!currentController.signal.aborted) {
				console.error('Failed to load custom pricing:', err);
				error = handleApiError(err);
				customPricing = [];
			}
		} finally {
			if (!currentController.signal.aborted) {
				isLoading = false;
			}
		}
	}

	// Handle create custom pricing
	async function handleCreate() {
		// Validate price
		const priceNum = parseFloat(formData.price);
		if (isNaN(priceNum) || priceNum < 0) {
			toast.error('Цена должна быть числом >= 0');
			return;
		}

		// Validate that either access code or user is provided
		if (inputMode === 'access_code' && (!formData.access_code || formData.access_code.trim().length === 0)) {
			toast.error('Access code обязателен');
			return;
		}
		if (inputMode === 'user' && !selectedUser) {
			toast.error('Пользователь обязателен');
			return;
		}

		try {
			const requestData: CreateCustomPricingRequest = {
				service_name: formData.service_name,
				price: priceNum.toFixed(2),
				is_active: formData.is_active
			};

			if (inputMode === 'user' && selectedUser) {
				requestData.user_id = selectedUser.id;
				// Include access_code if provided, even in user mode
				if (formData.access_code && formData.access_code.trim()) {
					requestData.access_code = formData.access_code.trim();
				}
			} else if (inputMode === 'access_code') {
				requestData.access_code = formData.access_code.trim();
			}

			await createCustomPricing(requestData);

			toast.success('Индивидуальная цена создана');
			showCreateDialog = false;
			resetForm();
			loadCustomPricing();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Handle update custom pricing
	async function handleUpdate() {
		if (!selectedPricing) return;

		// Validate price
		const priceNum = parseFloat(formData.price);
		if (isNaN(priceNum) || priceNum < 0) {
			toast.error('Цена должна быть числом >= 0');
			return;
		}

		try {
			await updateCustomPricing(selectedPricing.id, {
				price: priceNum.toFixed(2),
				is_active: formData.is_active
			});

			toast.success('Индивидуальная цена обновлена');
			showEditDialog = false;
			selectedPricing = null;
			resetForm();
			loadCustomPricing();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Handle toggle custom pricing
	async function handleToggle(pricing: CustomPricingResponse) {
		try {
			await toggleCustomPricing(pricing.id);
			toast.success(`Индивидуальная цена ${pricing.is_active ? 'выключена' : 'включена'}`);
			loadCustomPricing();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Handle delete custom pricing
	async function handleDelete(pricing: CustomPricingResponse) {
		if (!confirm(`Удалить индивидуальную цену для "${pricing.access_code}" (${SERVICE_NAMES[pricing.service_name]})?`)) {
			return;
		}

		try {
			await deleteCustomPricing(pricing.id);
			toast.success('Индивидуальная цена удалена');
			loadCustomPricing();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Open edit dialog
	function openEditDialog(pricing: CustomPricingResponse) {
		selectedPricing = pricing;
		formData = {
			access_code: pricing.access_code,
			service_name: pricing.service_name,
			price: pricing.price,
			is_active: pricing.is_active
		};
		showEditDialog = true;
	}

	// Reset form
	function resetForm() {
		formData = {
			access_code: '',
			service_name: 'instant_ssn',
			price: '2.00',
			is_active: true
		};
		selectedUser = null;
		inputMode = 'access_code';
	}

	// Apply filters
	function applyFilters() {
		loadCustomPricing();
	}

	// Clear filters
	function clearFilters() {
		filterAccessCode = '';
		filterUser = null;
		filterServiceName = '';
		filterIsActive = '';
		loadCustomPricing();
	}

	// Load on mount
	onMount(() => {
		loadCustomPricing();
	});
</script>

<div class="container py-8">
	<Card>
		<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-4">
			<div>
				<CardTitle class="text-2xl font-bold">Управление уникальными ценами</CardTitle>
				<p class="text-sm text-muted-foreground mt-1">
					Установка индивидуальных цен для пользователей
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
						<DialogTitle>Создать индивидуальную цену</DialogTitle>
					</DialogHeader>
					<div class="space-y-4 py-4">
						<!-- Mode toggle -->
						<div class="flex gap-2 p-1 bg-muted rounded-md">
							<Button
								variant={inputMode === 'access_code' ? 'default' : 'ghost'}
								class="flex-1"
								size="sm"
								onclick={() => inputMode = 'access_code'}
							>
								By Access Code
							</Button>
							<Button
								variant={inputMode === 'user' ? 'default' : 'ghost'}
								class="flex-1"
								size="sm"
								onclick={() => inputMode = 'user'}
							>
								By User
							</Button>
						</div>

						{#if inputMode === 'access_code'}
							<div class="space-y-2">
								<Label for="create-access-code">Access Code</Label>
								<Input
									id="create-access-code"
									bind:value={formData.access_code}
									placeholder="Введите access code пользователя"
									maxlength={15}
								/>
							</div>
						{:else}
							<div class="space-y-2">
								<Label for="create-user">Пользователь</Label>
								<UserSearchInput bind:value={selectedUser} placeholder="Поиск по username или ID" />
							</div>
						{/if}

						<div class="space-y-2">
							<Label for="create-service">Сервис</Label>
							<select
								id="create-service"
								bind:value={formData.service_name}
								class="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
							>
								<option value="instant_ssn">Быстрый SSN</option>
								<option value="manual_ssn">Ручной SSN</option>
							</select>
						</div>
						<div class="space-y-2">
							<Label for="create-price">Цена ($)</Label>
							<Input
								id="create-price"
								type="number"
								bind:value={formData.price}
								step="0.01"
								min="0"
								placeholder="0.00"
							/>
						</div>
						<div class="flex items-center space-x-2">
							<Checkbox id="create-active" bind:checked={formData.is_active} />
							<Label for="create-active">Активна</Label>
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
			<!-- Filters -->
			<Card class="mb-4">
				<CardContent class="pt-6">
					<div class="grid grid-cols-1 md:grid-cols-5 gap-4">
						<div class="space-y-2">
							<Label for="filter-access-code">Access Code</Label>
							<Input
								id="filter-access-code"
								bind:value={filterAccessCode}
								placeholder="Фильтр по access code"
							/>
						</div>
						<div class="space-y-2">
							<Label for="filter-user">Пользователь</Label>
							<UserSearchInput bind:value={filterUser} placeholder="Поиск пользователя" />
						</div>
						<div class="space-y-2">
							<Label for="filter-service">Сервис</Label>
							<select
								id="filter-service"
								bind:value={filterServiceName}
								class="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
							>
								<option value="">Все сервисы</option>
								<option value="instant_ssn">Быстрый SSN</option>
								<option value="manual_ssn">Ручной SSN</option>
							</select>
						</div>
						<div class="space-y-2">
							<Label for="filter-active">Статус</Label>
							<select
								id="filter-active"
								bind:value={filterIsActive}
								class="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
							>
								<option value="">Все</option>
								<option value="true">Активные</option>
								<option value="false">Неактивные</option>
							</select>
						</div>
						<div class="flex items-end gap-2">
							<Button onclick={applyFilters} class="flex-1">
								<Search class="mr-2 h-4 w-4" />
								Применить
							</Button>
							<Button variant="outline" onclick={clearFilters}>
								Сбросить
							</Button>
						</div>
					</div>
				</CardContent>
			</Card>

			{#if error}
				<Alert variant="destructive" class="mb-4">
					<AlertDescription>{error}</AlertDescription>
				</Alert>
			{/if}

			{#if isLoading}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
				</div>
			{:else if customPricing.length === 0}
				<div class="text-center py-8 text-muted-foreground">
					<DollarSign class="mx-auto h-12 w-12 mb-2 opacity-50" />
					<p>Нет настроенных индивидуальных цен</p>
				</div>
			{:else}
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>User</TableHead>
							<TableHead>Access Code</TableHead>
							<TableHead>Сервис</TableHead>
							<TableHead>Цена</TableHead>
							<TableHead>Статус</TableHead>
							<TableHead>Создан</TableHead>
							<TableHead>Обновлён</TableHead>
							<TableHead class="text-right">Действия</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each customPricing as pricing (pricing.id)}
							<TableRow>
								<TableCell class="font-medium">
									{#if pricing.username}
										{pricing.username}
									{:else if pricing.user_id}
										<span class="text-muted-foreground text-sm">User ID: {pricing.user_id.substring(0, 8)}...</span>
									{:else}
										<span class="text-muted-foreground">—</span>
									{/if}
								</TableCell>
								<TableCell class="font-mono text-sm">
									{#if pricing.access_code}
										{pricing.access_code}
									{:else if pricing.user_id}
										<span class="text-muted-foreground">(via user)</span>
									{:else}
										<span class="text-muted-foreground">—</span>
									{/if}
								</TableCell>
								<TableCell>
									{SERVICE_NAMES[pricing.service_name] || pricing.service_name}
								</TableCell>
								<TableCell class="font-semibold">
									${parseFloat(pricing.price).toFixed(2)}
								</TableCell>
								<TableCell>
									{#if pricing.is_active}
										<Badge variant="default">Активна</Badge>
									{:else}
										<Badge variant="outline">Неактивна</Badge>
									{/if}
								</TableCell>
								<TableCell class="text-muted-foreground text-sm">
									{formatDate(pricing.created_at)}
								</TableCell>
								<TableCell class="text-muted-foreground text-sm">
									{formatDate(pricing.updated_at)}
								</TableCell>
								<TableCell class="text-right">
									<div class="flex justify-end gap-2">
										<Button
											variant="ghost"
											size="sm"
											onclick={() => openEditDialog(pricing)}
										>
											<Edit class="h-4 w-4" />
										</Button>
										<Button
											variant="ghost"
											size="sm"
											onclick={() => handleToggle(pricing)}
										>
											{#if pricing.is_active}
												<ToggleRight class="h-4 w-4 text-green-500" />
											{:else}
												<ToggleLeft class="h-4 w-4 text-muted-foreground" />
											{/if}
										</Button>
										<Button
											variant="ghost"
											size="sm"
											onclick={() => handleDelete(pricing)}
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
			<DialogTitle>Редактировать индивидуальную цену</DialogTitle>
		</DialogHeader>
		<div class="space-y-4 py-4">
			{#if selectedPricing?.username}
				<div class="space-y-2">
					<Label for="edit-username">Пользователь</Label>
					<Input
						id="edit-username"
						value={selectedPricing.username}
						disabled
					/>
				</div>
			{/if}
			<div class="space-y-2">
				<Label for="edit-access-code">Access Code</Label>
				<Input
					id="edit-access-code"
					value={selectedPricing?.access_code || (selectedPricing?.user_id ? '(via user)' : '')}
					disabled
				/>
			</div>
			<div class="space-y-2">
				<Label for="edit-service">Сервис</Label>
				<Input
					id="edit-service"
					value={selectedPricing ? SERVICE_NAMES[selectedPricing.service_name] : ''}
					disabled
				/>
			</div>
			<div class="space-y-2">
				<Label for="edit-price">Цена ($)</Label>
				<Input
					id="edit-price"
					type="number"
					bind:value={formData.price}
					step="0.01"
					min="0"
					placeholder="0.00"
				/>
			</div>
			<div class="flex items-center space-x-2">
				<Checkbox id="edit-active" bind:checked={formData.is_active} />
				<Label for="edit-active">Активна</Label>
			</div>
		</div>
		<div class="flex justify-end gap-2">
			<Button variant="outline" onclick={() => showEditDialog = false}>Отмена</Button>
			<Button onclick={handleUpdate}>Обновить</Button>
		</div>
	</DialogContent>
</Dialog>
