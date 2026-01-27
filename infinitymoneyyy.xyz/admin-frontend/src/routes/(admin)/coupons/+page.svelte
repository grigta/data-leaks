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
		getCoupons,
		createCoupon,
		updateCoupon,
		deactivateCoupon,
		deleteCoupon,
		type CouponResponse,
		type CreateCouponRequest,
		type UpdateCouponRequest,
		type CouponType,
		handleApiError
	} from '$lib/api/client';
	import { formatDate } from '$lib/utils';
	import { Plus, Edit, Trash2, ToggleLeft, ToggleRight, Copy, Loader2 } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';

	// State
	let coupons = $state<CouponResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let showCreateDialog = $state(false);
	let showEditDialog = $state(false);
	let selectedCoupon = $state<CouponResponse | null>(null);

	// AbortController for canceling requests
	let abortController: AbortController | null = null;

	// Form data
	let formData = $state<CreateCouponRequest>({
		code: '',
		bonus_percent: 10,
		coupon_type: 'percentage',
		bonus_amount: 0,
		requires_registration: false,
		max_uses: 100,
		is_active: true
	});

	// Load coupons
	async function loadCoupons() {
		// Cancel previous request if exists
		if (abortController) {
			abortController.abort();
		}

		abortController = new AbortController();
		const currentController = abortController;

		isLoading = true;
		error = '';

		try {
			const response = await getCoupons();

			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				coupons = response?.coupons ?? [];
			}
		} catch (err: any) {
			if (!currentController.signal.aborted) {
				console.error('Failed to load coupons:', err);
				error = handleApiError(err);
				coupons = [];
			}
		} finally {
			if (!currentController.signal.aborted) {
				isLoading = false;
			}
		}
	}

	// Handle create coupon
	async function handleCreateCoupon() {
		// Validation based on coupon type
		if (formData.coupon_type === 'percentage') {
			if (!formData.bonus_percent || formData.bonus_percent < 1 || formData.bonus_percent > 100) {
				toast.error('Процент бонуса должен быть от 1 до 100');
				return;
			}
		} else if (formData.coupon_type === 'fixed_amount' || formData.coupon_type === 'registration_bonus') {
			if (!formData.bonus_amount || formData.bonus_amount <= 0) {
				toast.error('Сумма бонуса должна быть больше 0');
				return;
			}
		}

		if (formData.max_uses < 1) {
			toast.error('Макс. использований должно быть не менее 1');
			return;
		}

		try {
			await createCoupon({
				code: formData.code || undefined,
				bonus_percent: formData.bonus_percent,
				coupon_type: formData.coupon_type,
				bonus_amount: formData.bonus_amount,
				requires_registration: formData.requires_registration,
				max_uses: formData.max_uses,
				is_active: formData.is_active
			});

			toast.success('Купон успешно создан');
			showCreateDialog = false;
			resetForm();
			loadCoupons();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Handle update coupon
	async function handleUpdateCoupon() {
		if (!selectedCoupon) return;

		// Type-specific validation
		if (formData.coupon_type === 'percentage') {
			if (formData.bonus_percent < 1 || formData.bonus_percent > 100) {
				toast.error('Процент бонуса должен быть от 1 до 100');
				return;
			}
		} else if (formData.coupon_type === 'fixed_amount' || formData.coupon_type === 'registration_bonus') {
			if (formData.bonus_amount <= 0) {
				toast.error('Сумма бонуса должна быть больше 0');
				return;
			}
		}

		if (formData.max_uses < 1) {
			toast.error('Макс. использований должно быть не менее 1');
			return;
		}

		try {
			await updateCoupon(selectedCoupon.id, {
				bonus_percent: formData.coupon_type === 'percentage' ? formData.bonus_percent : undefined,
				coupon_type: formData.coupon_type,
				bonus_amount: (formData.coupon_type === 'fixed_amount' || formData.coupon_type === 'registration_bonus') ? formData.bonus_amount : undefined,
				requires_registration: formData.requires_registration,
				max_uses: formData.max_uses,
				is_active: formData.is_active
			});

			toast.success('Купон успешно обновлён');
			showEditDialog = false;
			selectedCoupon = null;
			resetForm();
			loadCoupons();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Handle deactivate/activate coupon
	async function handleToggleCoupon(coupon: CouponResponse) {
		try {
			if (coupon.is_active) {
				await deactivateCoupon(coupon.id);
				toast.success('Купон деактивирован');
			} else {
				await updateCoupon(coupon.id, { is_active: true });
				toast.success('Купон активирован');
			}
			loadCoupons();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Handle delete coupon
	async function handleDeleteCoupon(coupon: CouponResponse) {
		if (coupon.current_uses > 0) {
			const confirmed = confirm(
				`Этот купон использован ${coupon.current_uses} раз. Уверены, что хотите удалить?`
			);
			if (!confirmed) return;
		} else {
			const confirmed = confirm('Уверены, что хотите удалить этот купон?');
			if (!confirmed) return;
		}

		try {
			await deleteCoupon(coupon.id);
			toast.success('Купон удалён');
			loadCoupons();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Open edit dialog
	function openEditDialog(coupon: CouponResponse) {
		selectedCoupon = coupon;
		formData = {
			code: coupon.code,
			bonus_percent: coupon.bonus_percent,
			coupon_type: coupon.coupon_type,
			bonus_amount: coupon.bonus_amount || 0,
			requires_registration: coupon.requires_registration,
			max_uses: coupon.max_uses,
			is_active: coupon.is_active
		};
		showEditDialog = true;
	}

	// Reset form
	function resetForm() {
		formData = {
			code: '',
			bonus_percent: 10,
			coupon_type: 'percentage',
			bonus_amount: 0,
			requires_registration: false,
			max_uses: 100,
			is_active: true
		};
	}

	// Copy coupon code
	async function copyCouponCode(code: string) {
		try {
			await navigator.clipboard.writeText(code);
			toast.success('Код купона скопирован');
		} catch {
			toast.error('Не удалось скопировать код купона');
		}
	}

	onMount(() => {
		loadCoupons();

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
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">Управление купонами</h2>
			<p class="text-muted-foreground">Создание и управление купонами платформы</p>
		</div>

		<Dialog bind:open={showCreateDialog}>
			<DialogTrigger>
				{#snippet child({ props })}
					<Button {...props}>
						<Plus class="mr-2 h-4 w-4" />
						Создать купон
					</Button>
				{/snippet}
			</DialogTrigger>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>Создать новый купон</DialogTitle>
				</DialogHeader>
				<div class="space-y-4 py-4">
					<div class="space-y-2">
						<Label for="code">Код (опционально)</Label>
						<Input
							id="code"
							placeholder="Оставьте пустым для автогенерации"
							bind:value={formData.code}
						/>
						<p class="text-xs text-muted-foreground">
							Если пусто, уникальный код будет сгенерирован автоматически
						</p>
					</div>

					<div class="space-y-2">
						<Label for="coupon_type">Тип купона</Label>
						<select
							id="coupon_type"
							bind:value={formData.coupon_type}
							class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
						>
							<option value="percentage">Процентный бонус</option>
							<option value="fixed_amount">Фиксированная сумма</option>
							<option value="registration">Только регистрация</option>
							<option value="registration_bonus">Регистрация с бонусом</option>
						</select>
					</div>

					{#if formData.coupon_type === 'percentage'}
						<div class="space-y-2">
							<Label for="bonus_percent">Процент бонуса</Label>
							<Input
								id="bonus_percent"
								type="number"
								min="1"
								max="100"
								bind:value={formData.bonus_percent}
							/>
						</div>
					{:else if formData.coupon_type === 'fixed_amount' || formData.coupon_type === 'registration_bonus'}
						<div class="space-y-2">
							<Label for="bonus_amount">Сумма бонуса ($)</Label>
							<Input
								id="bonus_amount"
								type="number"
								min="0.01"
								step="0.01"
								bind:value={formData.bonus_amount}
							/>
						</div>
					{:else if formData.coupon_type === 'registration'}
						<Alert>
							<AlertDescription>
								Купон только для регистрации (без бонуса)
							</AlertDescription>
						</Alert>
					{/if}

					<div class="space-y-2">
						<Label for="max_uses">Макс. использований</Label>
						<Input id="max_uses" type="number" min="1" bind:value={formData.max_uses} />
					</div>

					<div class="flex items-center space-x-2">
						<Checkbox
							id="requires_registration"
							bind:checked={formData.requires_registration}
							disabled={formData.coupon_type === 'registration' || formData.coupon_type === 'registration_bonus'}
						/>
						<Label for="requires_registration" class="cursor-pointer">Требуется для регистрации</Label>
					</div>

					<div class="flex items-center space-x-2">
						<Checkbox id="is_active" bind:checked={formData.is_active} />
						<Label for="is_active" class="cursor-pointer">Активный</Label>
					</div>

					<div class="flex gap-2">
						<Button class="flex-1" onclick={handleCreateCoupon}>Создать</Button>
						<Button
							variant="outline"
							class="flex-1"
							onclick={() => {
								showCreateDialog = false;
								resetForm();
							}}>Отмена</Button
						>
					</div>
				</div>
			</DialogContent>
		</Dialog>
	</div>

	<!-- Error alert -->
	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Coupons table -->
	<Card>
		<CardHeader>
			<CardTitle>Купоны</CardTitle>
		</CardHeader>
		<CardContent>
			{#if isLoading}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-8 w-8 animate-spin text-primary" />
				</div>
			{:else if coupons.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-muted-foreground">Купоны не найдены</p>
					<p class="text-sm text-muted-foreground">Создайте первый купон для начала</p>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>Код</TableHead>
								<TableHead>Тип</TableHead>
								<TableHead>Бонус</TableHead>
								<TableHead>Макс. использований</TableHead>
								<TableHead>Текущее использование</TableHead>
								<TableHead>Использование</TableHead>
								<TableHead>Статус</TableHead>
								<TableHead>Создан</TableHead>
								<TableHead class="text-right">Действия</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each coupons as coupon}
								<TableRow>
									<TableCell class="font-mono">
										<div class="flex items-center gap-2">
											{coupon.code}
											<Button
												variant="ghost"
												size="icon"
												class="h-6 w-6"
												onclick={() => copyCouponCode(coupon.code)}
											>
												<Copy class="h-3 w-3" />
											</Button>
										</div>
									</TableCell>
									<TableCell>
										<Badge variant="outline">
											{#if coupon.coupon_type === 'percentage'}
												Процент
											{:else if coupon.coupon_type === 'fixed_amount'}
												Фиксир.
											{:else if coupon.coupon_type === 'registration'}
												Регистр.
											{:else if coupon.coupon_type === 'registration_bonus'}
												Рег.+Бонус
											{:else}
												{coupon.coupon_type}
											{/if}
										</Badge>
									</TableCell>
									<TableCell>
										{#if coupon.coupon_type === 'percentage'}
											{coupon.bonus_percent}%
										{:else if coupon.coupon_type === 'fixed_amount' || coupon.coupon_type === 'registration_bonus'}
											${coupon.bonus_amount}
										{:else}
											N/A
										{/if}
									</TableCell>
									<TableCell>{coupon.max_uses}</TableCell>
									<TableCell>{coupon.current_uses}</TableCell>
									<TableCell>
										<div class="space-y-1">
											<div class="flex items-center gap-2">
												<div class="h-2 w-24 rounded-full bg-muted">
													<div
														class="h-full rounded-full bg-primary transition-all"
														style="width: {coupon.usage_percentage}%"
													></div>
												</div>
												<span class="text-xs text-muted-foreground"
													>{coupon.usage_percentage.toFixed(0)}%</span
												>
											</div>
										</div>
									</TableCell>
									<TableCell>
										<Badge variant={coupon.is_active ? 'default' : 'secondary'}>
											{coupon.is_active ? 'Активный' : 'Неактивный'}
										</Badge>
									</TableCell>
									<TableCell>{formatDate(coupon.created_at)}</TableCell>
									<TableCell class="text-right">
										<div class="flex justify-end gap-2">
											<Button
												variant="ghost"
												size="icon"
												onclick={() => openEditDialog(coupon)}
											>
												<Edit class="h-4 w-4" />
											</Button>
											<Button
												variant="ghost"
												size="icon"
												onclick={() => handleToggleCoupon(coupon)}
											>
												{#if coupon.is_active}
													<ToggleRight class="h-4 w-4" />
												{:else}
													<ToggleLeft class="h-4 w-4" />
												{/if}
											</Button>
											<Button
												variant="ghost"
												size="icon"
												onclick={() => handleDeleteCoupon(coupon)}
											>
												<Trash2 class="h-4 w-4 text-destructive" />
											</Button>
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

<!-- Edit Dialog -->
<Dialog bind:open={showEditDialog}>
	<DialogContent>
		<DialogHeader>
			<DialogTitle>Редактировать купон</DialogTitle>
		</DialogHeader>
		<div class="space-y-4 py-4">
			<div class="space-y-2">
				<Label>Код</Label>
				<Input value={formData.code} disabled />
			</div>

			<div class="space-y-2">
				<Label>Тип купона</Label>
				<Input value={formData.coupon_type} disabled />
				<p class="text-xs text-muted-foreground">Тип купона нельзя изменить после создания</p>
			</div>

			{#if formData.coupon_type === 'percentage'}
				<div class="space-y-2">
					<Label for="edit_bonus_percent">Процент бонуса</Label>
					<Input
						id="edit_bonus_percent"
						type="number"
						min="1"
						max="100"
						bind:value={formData.bonus_percent}
					/>
				</div>
			{:else if formData.coupon_type === 'fixed_amount' || formData.coupon_type === 'registration_bonus'}
				<div class="space-y-2">
					<Label for="edit_bonus_amount">Сумма бонуса ($)</Label>
					<Input
						id="edit_bonus_amount"
						type="number"
						min="0.01"
						step="0.01"
						bind:value={formData.bonus_amount}
					/>
				</div>
			{:else if formData.coupon_type === 'registration'}
				<Alert>
					<AlertDescription>
						Купон только для регистрации (без бонуса)
					</AlertDescription>
				</Alert>
			{/if}

			<div class="space-y-2">
				<Label for="edit_max_uses">Макс. использований</Label>
				<Input id="edit_max_uses" type="number" min="1" bind:value={formData.max_uses} />
			</div>

			<div class="flex items-center space-x-2">
				<Checkbox
					id="edit_requires_registration"
					bind:checked={formData.requires_registration}
					disabled={formData.coupon_type === 'registration' || formData.coupon_type === 'registration_bonus'}
				/>
				<Label for="edit_requires_registration" class="cursor-pointer">Требуется для регистрации</Label>
			</div>

			<div class="flex items-center space-x-2">
				<Checkbox id="edit_is_active" bind:checked={formData.is_active} />
				<Label for="edit_is_active" class="cursor-pointer">Активный</Label>
			</div>

			<div class="flex gap-2">
				<Button class="flex-1" onclick={handleUpdateCoupon}>Обновить</Button>
				<Button
					variant="outline"
					class="flex-1"
					onclick={() => {
						showEditDialog = false;
						selectedCoupon = null;
						resetForm();
					}}>Отмена</Button
				>
			</div>
		</div>
	</DialogContent>
</Dialog>
