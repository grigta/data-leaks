<script lang="ts">
	import { goto } from '$app/navigation';
	import { registerWorker, type WorkerRegisterRequest } from '$lib/api/client';
	import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Loader2, UserPlus, CheckCircle, Copy, ArrowRight } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';

	// State
	let username = $state('');
	let email = $state('');
	let password = $state('');
	let confirmPassword = $state('');
	let error = $state('');
	let isLoading = $state(false);
	let accessCode = $state<string | null>(null);
	let registrationComplete = $state(false);

	// Validation
	function validate(): string | null {
		if (!username || !email || !password || !confirmPassword) {
			return 'Все поля обязательны';
		}

		if (username.length < 3 || username.length > 50) {
			return 'Имя пользователя должно быть от 3 до 50 символов';
		}

		if (!email.includes('@')) {
			return 'Введите действительный адрес email';
		}

		if (password.length < 8) {
			return 'Пароль должен быть не менее 8 символов';
		}

		if (password !== confirmPassword) {
			return 'Пароли не совпадают';
		}

		return null;
	}

	// Handle registration
	async function handleRegister() {
		const validationError = validate();
		if (validationError) {
			error = validationError;
			return;
		}

		isLoading = true;
		error = '';

		try {
			const data: WorkerRegisterRequest = {
				username,
				email,
				password
			};

			const response = await registerWorker(data);

			// Registration successful
			accessCode = response.access_code;
			registrationComplete = true;
			toast.success('Регистрация успешна!');
		} catch (err: any) {
			if (err.response?.data?.detail) {
				error = err.response.data.detail;
			} else {
				error = err.message || 'Регистрация не удалась. Попробуйте снова.';
			}
		} finally {
			isLoading = false;
		}
	}

	// Copy access code to clipboard
	async function copyAccessCode() {
		if (!accessCode) return;

		try {
			await navigator.clipboard.writeText(accessCode);
			toast.success('Код доступа скопирован в буфер обмена!');
		} catch (err) {
			toast.error('Не удалось скопировать код доступа');
		}
	}

	// Handle Enter key
	function handleKeyPress(event: KeyboardEvent, action: () => void) {
		if (event.key === 'Enter') {
			action();
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-background px-4 py-8">
	<Card class="w-full max-w-md">
		<CardHeader>
			<div class="flex items-center justify-center gap-2">
				<UserPlus class="h-6 w-6 text-primary" />
				<CardTitle class="text-center text-2xl">Регистрация работника</CardTitle>
			</div>
			{#if !registrationComplete}
				<CardDescription class="text-center">
					Зарегистрируйтесь, чтобы стать работником. После регистрации ваша заявка будет рассмотрена администратором.
				</CardDescription>
			{/if}
		</CardHeader>

		<CardContent>
			{#if !registrationComplete}
				<!-- Registration Form -->
				<form
					onsubmit={(e) => {
						e.preventDefault();
						handleRegister();
					}}
					class="space-y-4"
				>
					<div class="space-y-2">
						<Label for="username">Имя пользователя *</Label>
						<Input
							id="username"
							type="text"
							placeholder="Выберите имя пользователя"
							bind:value={username}
							disabled={isLoading}
							autocomplete="username"
							onkeypress={(e) => handleKeyPress(e, handleRegister)}
						/>
						<p class="text-xs text-muted-foreground">3-50 символов</p>
					</div>

					<div class="space-y-2">
						<Label for="email">Email *</Label>
						<Input
							id="email"
							type="email"
							placeholder="ваш@email.com"
							bind:value={email}
							disabled={isLoading}
							autocomplete="email"
							onkeypress={(e) => handleKeyPress(e, handleRegister)}
						/>
					</div>

					<div class="space-y-2">
						<Label for="password">Пароль *</Label>
						<Input
							id="password"
							type="password"
							placeholder="Введите пароль"
							bind:value={password}
							disabled={isLoading}
							autocomplete="new-password"
							onkeypress={(e) => handleKeyPress(e, handleRegister)}
						/>
						<p class="text-xs text-muted-foreground">Минимум 8 символов</p>
					</div>

					<div class="space-y-2">
						<Label for="confirm-password">Подтвердите пароль *</Label>
						<Input
							id="confirm-password"
							type="password"
							placeholder="Подтвердите пароль"
							bind:value={confirmPassword}
							disabled={isLoading}
							autocomplete="new-password"
							onkeypress={(e) => handleKeyPress(e, handleRegister)}
						/>
					</div>

					{#if error}
						<Alert variant="destructive">
							<AlertDescription>{error}</AlertDescription>
						</Alert>
					{/if}

					<Button type="submit" class="w-full" disabled={isLoading}>
						{#if isLoading}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							Регистрация...
						{:else}
							<UserPlus class="mr-2 h-4 w-4" />
							Зарегистрироваться как работник
						{/if}
					</Button>

					<div class="text-center text-sm">
						<span class="text-muted-foreground">Уже зарегистрированы?</span>
						<Button variant="link" class="p-0 pl-1" onclick={() => goto('/login')}>
							Войти здесь
						</Button>
					</div>
				</form>
			{:else}
				<!-- Success Screen -->
				<div class="space-y-6">
					<div class="flex flex-col items-center gap-4 text-center">
						<CheckCircle class="h-16 w-16 text-green-600" />
						<div>
							<h3 class="text-lg font-semibold">Регистрация успешна!</h3>
							<p class="text-sm text-muted-foreground">
								Ваша заявка на регистрацию работника отправлена.
							</p>
						</div>
					</div>

					<div class="space-y-3 rounded-lg border p-4">
						<div class="flex items-center justify-between">
							<Label class="text-sm font-medium">Ваш код доступа</Label>
							<Button variant="ghost" size="sm" onclick={copyAccessCode}>
								<Copy class="h-4 w-4" />
							</Button>
						</div>
						<div class="rounded bg-muted p-3 font-mono text-lg font-bold text-center tracking-wider">
							{accessCode}
						</div>
						<Alert>
							<AlertDescription class="text-xs">
								<strong>Важно:</strong> Сохраните этот код доступа! Он понадобится вам для доступа к функциям работника после одобрения вашей заявки администратором.
							</AlertDescription>
						</Alert>
					</div>

					<div class="space-y-2 text-sm text-muted-foreground">
						<p><strong>Следующие шаги:</strong></p>
						<ol class="list-decimal list-inside space-y-1 ml-2">
							<li>Сохраните код доступа в безопасном месте</li>
							<li>Дождитесь рассмотрения заявки администратором</li>
							<li>Сможете войти после одобрения</li>
						</ol>
					</div>

					<Button class="w-full" onclick={() => goto('/login')}>
						Перейти ко входу
						<ArrowRight class="ml-2 h-4 w-4" />
					</Button>
				</div>
			{/if}
		</CardContent>
	</Card>
</div>
