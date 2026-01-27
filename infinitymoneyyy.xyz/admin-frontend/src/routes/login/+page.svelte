<script lang="ts">
	import { goto } from '$app/navigation';
	import { authStore, requires2FA } from '$lib/stores/auth';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Loader2, Lock, Shield, ArrowLeft } from '@lucide/svelte';

	// State
	let username = $state('');
	let password = $state('');
	let totpCode = $state('');
	let error = $state('');
	let isLoading = $state(false);

	// Derived state - show TOTP input if 2FA is required
	let showTOTPInput = $derived($requires2FA);

	// Handle username/password login
	async function handleLogin() {
		if (!username || !password) {
			error = 'Имя пользователя и пароль обязательны';
			return;
		}

		isLoading = true;
		error = '';

		const result = await authStore.login(username, password);

		if (result.success) {
			if (result.requires2FA) {
				// TOTP input will be shown automatically via showTOTPInput
				isLoading = false;
			} else {
				// No 2FA required, redirect based on role
				if (result.user?.worker_role === true && result.user?.is_admin === false) {
					goto('/manual-ssn');
				} else {
					goto('/');
				}
			}
		} else {
			error = result.error || 'Ошибка входа';
			isLoading = false;
		}
	}

	// Handle TOTP verification
	async function handleTOTPVerify() {
		if (!totpCode || totpCode.length !== 6) {
			error = 'Введите действительный 6-значный код';
			return;
		}

		isLoading = true;
		error = '';

		const result = await authStore.verifyTOTP(totpCode);

		if (result.success) {
			// Redirect based on role
			if (result.user?.worker_role === true && result.user?.is_admin === false) {
				goto('/manual-ssn');
			} else {
				goto('/');
			}
		} else {
			error = result.error || 'Ошибка подтверждения';
			totpCode = '';
			isLoading = false;
		}
	}

	// Go back to username/password
	function handleBack() {
		error = '';
		totpCode = '';
		password = '';
		authStore.logout();
	}

	// Handle Enter key
	function handleKeyPress(event: KeyboardEvent, action: () => void) {
		if (event.key === 'Enter') {
			action();
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-background px-4">
	<Card class="w-full max-w-md">
		<CardHeader>
			<div class="flex items-center justify-center gap-2">
				<Lock class="h-6 w-6 text-primary" />
				<CardTitle class="text-center text-2xl">Вход администратора</CardTitle>
			</div>
		</CardHeader>

		<CardContent>
			{#if !showTOTPInput}
				<!-- Username/Password Form -->
				<form
					onsubmit={(e) => {
						e.preventDefault();
						handleLogin();
					}}
					class="space-y-4"
				>
					<div class="space-y-2">
						<Label for="username">Имя пользователя</Label>
						<Input
							id="username"
							type="text"
							placeholder="Введите имя пользователя"
							bind:value={username}
							disabled={isLoading}
							autocomplete="username"
							onkeypress={(e) => handleKeyPress(e, handleLogin)}
						/>
					</div>

					<div class="space-y-2">
						<Label for="password">Пароль</Label>
						<Input
							id="password"
							type="password"
							placeholder="Введите пароль"
							bind:value={password}
							disabled={isLoading}
							autocomplete="current-password"
							onkeypress={(e) => handleKeyPress(e, handleLogin)}
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
							Вход...
						{:else}
							Войти
						{/if}
					</Button>

					<div class="text-center text-sm">
						<span class="text-muted-foreground">Хотите стать работником?</span>
						<Button variant="link" class="p-0 pl-1" onclick={() => goto('/register-worker')}>
							Зарегистрироваться здесь
						</Button>
					</div>
				</form>
			{:else}
				<!-- TOTP Verification Form -->
				<div class="space-y-4">
					<div class="flex flex-col items-center gap-2 text-center">
						<Shield class="h-12 w-12 text-primary" />
						<h3 class="text-lg font-semibold">Двухфакторная аутентификация</h3>
						<p class="text-sm text-muted-foreground">
							Введите 6-значный код из приложения-аутентификатора
						</p>
					</div>

					<div class="space-y-2">
						<Label for="totp">Код аутентификации</Label>
						<Input
							id="totp"
							type="text"
							placeholder="000000"
							bind:value={totpCode}
							disabled={isLoading}
							maxlength={6}
							pattern="[0-9]{6}"
							inputmode="numeric"
							autocomplete="one-time-code"
							onkeypress={(e) => handleKeyPress(e, handleTOTPVerify)}
							class="text-center text-2xl tracking-widest"
						/>
					</div>

					{#if error}
						<Alert variant="destructive">
							<AlertDescription>{error}</AlertDescription>
						</Alert>
					{/if}

					<div class="flex gap-2">
						<Button variant="outline" class="flex-1" onclick={handleBack} disabled={isLoading}>
							<ArrowLeft class="mr-2 h-4 w-4" />
							Назад
						</Button>

						<Button class="flex-1" onclick={handleTOTPVerify} disabled={isLoading}>
							{#if isLoading}
								<Loader2 class="mr-2 h-4 w-4 animate-spin" />
								Подтверждение...
							{:else}
								Подтвердить
							{/if}
						</Button>
					</div>
				</div>
			{/if}
		</CardContent>
	</Card>
</div>
