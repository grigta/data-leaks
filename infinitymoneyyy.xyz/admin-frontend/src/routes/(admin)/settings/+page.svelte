<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import {
		Dialog,
		DialogContent,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import { Badge } from '$lib/components/ui/badge';
	import {
		Shield,
		ShieldCheck,
		ShieldOff,
		Loader2,
		Copy,
		CheckCircle2
	} from '@lucide/svelte';
	import QrCode from 'svelte-qrcode';
	import {
		setupTwoFactor,
		confirmTwoFactor,
		disableTwoFactor,
		getCurrentAdminUser,
		handleApiError
	} from '$lib/api/client';
	import { toast } from 'svelte-sonner';

	// State переменные
	let currentUser = $state<{ username: string; email: string; has_totp: boolean } | null>(null);
	let has2FA = $state(false);
	let isLoading = $state(true);
	let error = $state('');
	let setupStep = $state<'idle' | 'qr' | 'confirm'>('idle');
	let qrData = $state<{ secret: string; provisioning_uri: string } | null>(null);
	let totpCode = $state('');
	let isSettingUp = $state(false);
	let isConfirming = $state(false);
	let showDisableDialog = $state(false);
	let disablePassword = $state('');
	let isDisabling = $state(false);

	// Загрузка данных пользователя
	async function loadUserData() {
		isLoading = true;
		error = '';

		try {
			const user = await getCurrentAdminUser();
			currentUser = user;
			// Проверяем наличие 2FA из типизированного ответа
			has2FA = user.has_totp;
		} catch (err: any) {
			console.error('Failed to load user data:', err);
			error = handleApiError(err);
		} finally {
			isLoading = false;
		}
	}

	// Начало настройки 2FA
	async function handleSetup2FA() {
		// Защита от повторного вызова setup для пользователей с активным 2FA
		if (has2FA) {
			toast.error('2FA уже включена. Сначала отключите её для повторной настройки.');
			return;
		}

		isSettingUp = true;
		error = '';

		try {
			const response = await setupTwoFactor();
			qrData = {
				secret: response.secret,
				provisioning_uri: response.provisioning_uri
			};
			setupStep = 'qr';
		} catch (err: any) {
			console.error('Failed to setup 2FA:', err);
			toast.error(handleApiError(err));
		} finally {
			isSettingUp = false;
		}
	}

	// Подтверждение 2FA
	async function handleConfirm2FA() {
		// Валидация кода
		if (!totpCode || totpCode.length !== 6 || !/^\d{6}$/.test(totpCode)) {
			toast.error('Введите действительный 6-значный код');
			return;
		}

		isConfirming = true;

		try {
			await confirmTwoFactor(totpCode);
			toast.success('2FA успешно включена');
			has2FA = true;
			setupStep = 'idle';
			qrData = null;
			totpCode = '';
			// Перезагрузить данные пользователя
			await loadUserData();
		} catch (err: any) {
			console.error('Failed to confirm 2FA:', err);
			toast.error(handleApiError(err));
		} finally {
			isConfirming = false;
		}
	}

	// Отключение 2FA
	async function handleDisable2FA() {
		// Валидация пароля
		if (!disablePassword) {
			toast.error('Введите ваш пароль');
			return;
		}

		// Валидация длины пароля
		if (disablePassword.length < 8) {
			toast.error('Пароль должен быть не менее 8 символов');
			return;
		}

		isDisabling = true;

		try {
			await disableTwoFactor(disablePassword);
			toast.success('2FA отключена');
			has2FA = false;
			showDisableDialog = false;
			disablePassword = '';
			// Перезагрузить данные пользователя
			await loadUserData();
		} catch (err: any) {
			console.error('Failed to disable 2FA:', err);
			toast.error(handleApiError(err));
		} finally {
			isDisabling = false;
		}
	}

	// Копирование секрета
	function copySecret() {
		if (qrData?.secret) {
			navigator.clipboard.writeText(qrData.secret);
			toast.success('Секрет скопирован в буфер обмена');
		}
	}

	// Отмена настройки
	function resetSetup() {
		setupStep = 'idle';
		qrData = null;
		totpCode = '';
	}

	// Инициализация при монтировании
	onMount(() => {
		loadUserData();
	});
</script>

<div class="space-y-6">
	<!-- Заголовок страницы -->
	<div>
		<h2 class="text-3xl font-bold tracking-tight">Двухфакторная аутентификация</h2>
		<p class="text-muted-foreground mt-2">Защитите свой аккаунт администратора с помощью 2FA</p>
	</div>

	<!-- Ошибка -->
	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Секция статуса 2FA -->
	<Card>
		<CardHeader>
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-3">
					{#if has2FA}
						<ShieldCheck class="h-6 w-6 text-green-500" />
						<div>
							<CardTitle>Статус двухфакторной аутентификации</CardTitle>
							<p class="text-sm text-muted-foreground mt-1">
								Ваш аккаунт защищён с помощью 2FA
							</p>
						</div>
					{:else}
						<Shield class="h-6 w-6 text-muted-foreground" />
						<div>
							<CardTitle>Статус двухфакторной аутентификации</CardTitle>
							<p class="text-sm text-muted-foreground mt-1">
								Двухфакторная аутентификация добавляет дополнительный уровень безопасности
							</p>
						</div>
					{/if}
				</div>
				{#if has2FA}
					<Badge variant="default" class="bg-green-500">Включена</Badge>
				{:else}
					<Badge variant="secondary">Отключена</Badge>
				{/if}
			</div>
		</CardHeader>
	</Card>

	<!-- Секция включения 2FA -->
	{#if !has2FA}
		{#if setupStep === 'idle'}
			<!-- Кнопка Enable 2FA -->
			<Card>
				<CardHeader>
					<CardTitle>Включить двухфакторную аутентификацию</CardTitle>
				</CardHeader>
				<CardContent>
					<p class="text-sm text-muted-foreground mb-4">
						Защитите свой аккаунт администратора, требуя код подтверждения из приложения-аутентификатора в дополнение к паролю.
					</p>
					<Button onclick={handleSetup2FA} disabled={isSettingUp || isLoading}>
						{#if isSettingUp}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							Настройка...
						{:else}
							<Shield class="mr-2 h-4 w-4" />
							Включить двухфакторную аутентификацию
						{/if}
					</Button>
				</CardContent>
			</Card>
		{:else if setupStep === 'qr'}
			<!-- Показ QR-кода -->
			<Card>
				<CardHeader>
					<CardTitle>Сканировать QR-код</CardTitle>
				</CardHeader>
				<CardContent class="space-y-6">
					<!-- Инструкция -->
					<Alert>
						<AlertDescription>
							Отсканируйте этот QR-код с помощью приложения-аутентификатора (Google Authenticator, Authy и т.д.), чтобы связать свой аккаунт.
						</AlertDescription>
					</Alert>

					<!-- QR-код -->
					{#if qrData}
						<div class="flex flex-col items-center justify-center space-y-4">
							<div class="p-4 bg-white rounded-lg">
								<QrCode value={qrData.provisioning_uri} size={256} />
							</div>

							<!-- Секрет -->
							<div class="w-full max-w-md space-y-2">
								<p class="text-sm text-muted-foreground text-center">
									Или введите этот секрет вручную:
								</p>
								<div class="flex items-center gap-2">
									<code class="flex-1 px-3 py-2 bg-muted rounded text-sm font-mono text-center">
										{qrData.secret}
									</code>
									<Button size="icon" variant="outline" onclick={copySecret}>
										<Copy class="h-4 w-4" />
									</Button>
								</div>
							</div>
						</div>

						<!-- Поле ввода кода -->
						<div class="space-y-2 max-w-md mx-auto">
							<Label for="totp-code">Введите код подтверждения</Label>
							<Input
								id="totp-code"
								bind:value={totpCode}
								maxlength={6}
								placeholder="000000"
								class="text-center text-2xl tracking-widest font-mono"
							/>
							<p class="text-xs text-muted-foreground">
								Введите 6-значный код из приложения-аутентификатора
							</p>
						</div>

						<!-- Кнопки -->
						<div class="flex gap-3 justify-center">
							<Button variant="outline" onclick={resetSetup} disabled={isConfirming}>
								Отмена
							</Button>
							<Button onclick={handleConfirm2FA} disabled={isConfirming || !totpCode}>
								{#if isConfirming}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									Подтверждение...
								{:else}
									<CheckCircle2 class="mr-2 h-4 w-4" />
									Подтвердить
								{/if}
							</Button>
						</div>
					{/if}
				</CardContent>
			</Card>
		{/if}
	{/if}

	<!-- Секция отключения 2FA -->
	{#if has2FA}
		<Card>
			<CardHeader>
				<CardTitle>Отключить двухфакторную аутентификацию</CardTitle>
			</CardHeader>
			<CardContent class="space-y-4">
				<Alert variant="destructive">
					<AlertDescription>
						Отключение 2FA сделает ваш аккаунт менее безопасным. Вам понадобится только пароль для входа.
					</AlertDescription>
				</Alert>

				<Button variant="destructive" onclick={() => (showDisableDialog = true)}>
					<ShieldOff class="mr-2 h-4 w-4" />
					Отключить двухфакторную аутентификацию
				</Button>
			</CardContent>
		</Card>
	{/if}

	<!-- Модальное окно отключения -->
	<Dialog bind:open={showDisableDialog}>
		<DialogContent>
			<DialogHeader>
				<DialogTitle>Отключить двухфакторную аутентификацию</DialogTitle>
			</DialogHeader>

			<div class="space-y-4">
				<Alert variant="destructive">
					<AlertDescription>
						Вы уверены, что хотите отключить 2FA? Это снизит безопасность вашего аккаунта.
					</AlertDescription>
				</Alert>

				<div class="space-y-2">
					<Label for="disable-password">Введите пароль для подтверждения</Label>
					<Input
						id="disable-password"
						type="password"
						bind:value={disablePassword}
						placeholder="Введите ваш пароль"
					/>
					<p class="text-xs text-muted-foreground">
						Пароль должен быть не менее 8 символов
					</p>
				</div>

				<div class="flex gap-3 justify-end">
					<Button
						variant="outline"
						onclick={() => {
							showDisableDialog = false;
							disablePassword = '';
						}}
						disabled={isDisabling}
					>
						Отмена
					</Button>
					<Button
						variant="destructive"
						onclick={handleDisable2FA}
						disabled={isDisabling || !disablePassword || disablePassword.length < 8}
					>
						{#if isDisabling}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							Отключение...
						{:else}
							Отключить 2FA
						{/if}
					</Button>
				</div>
			</div>
		</DialogContent>
	</Dialog>
</div>
