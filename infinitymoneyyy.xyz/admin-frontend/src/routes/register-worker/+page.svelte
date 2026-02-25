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
	import { t } from '$lib/i18n';

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
			return $t('auth.register.allFieldsRequired');
		}

		if (username.length < 3 || username.length > 50) {
			return $t('auth.register.usernameLength');
		}

		if (!email.includes('@')) {
			return $t('auth.register.invalidEmail');
		}

		if (password.length < 8) {
			return $t('auth.register.passwordLength');
		}

		if (password !== confirmPassword) {
			return $t('auth.register.passwordMismatch');
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
			toast.success($t('auth.register.registrationSuccess'));
		} catch (err: any) {
			if (err.response?.data?.detail) {
				error = err.response.data.detail;
			} else {
				error = err.message || $t('auth.register.registrationFailed');
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
			toast.success($t('auth.register.accessCodeCopied'));
		} catch (err) {
			toast.error($t('auth.register.accessCodeCopyFailed'));
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
				<CardTitle class="text-center text-2xl">{$t('auth.register.title')}</CardTitle>
			</div>
			{#if !registrationComplete}
				<CardDescription class="text-center">
					{$t('auth.register.description')}
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
						<Label for="username">{$t('auth.register.username')}</Label>
						<Input
							id="username"
							type="text"
							placeholder={$t('auth.register.usernamePlaceholder')}
							bind:value={username}
							disabled={isLoading}
							autocomplete="username"
							onkeypress={(e) => handleKeyPress(e, handleRegister)}
						/>
						<p class="text-xs text-muted-foreground">{$t('auth.register.usernameHint')}</p>
					</div>

					<div class="space-y-2">
						<Label for="email">{$t('auth.register.email')}</Label>
						<Input
							id="email"
							type="email"
							placeholder={$t('auth.register.emailPlaceholder')}
							bind:value={email}
							disabled={isLoading}
							autocomplete="email"
							onkeypress={(e) => handleKeyPress(e, handleRegister)}
						/>
					</div>

					<div class="space-y-2">
						<Label for="password">{$t('auth.register.password')}</Label>
						<Input
							id="password"
							type="password"
							placeholder={$t('auth.register.passwordPlaceholder')}
							bind:value={password}
							disabled={isLoading}
							autocomplete="new-password"
							onkeypress={(e) => handleKeyPress(e, handleRegister)}
						/>
						<p class="text-xs text-muted-foreground">{$t('auth.register.passwordHint')}</p>
					</div>

					<div class="space-y-2">
						<Label for="confirm-password">{$t('auth.register.confirmPassword')}</Label>
						<Input
							id="confirm-password"
							type="password"
							placeholder={$t('auth.register.confirmPasswordPlaceholder')}
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
							{$t('auth.register.registering')}
						{:else}
							<UserPlus class="mr-2 h-4 w-4" />
							{$t('auth.register.registerButton')}
						{/if}
					</Button>

					<div class="text-center text-sm">
						<span class="text-muted-foreground">{$t('auth.register.alreadyRegistered')}</span>
						<Button variant="link" class="p-0 pl-1" onclick={() => goto('/login')}>
							{$t('auth.register.loginHere')}
						</Button>
					</div>
				</form>
			{:else}
				<!-- Success Screen -->
				<div class="space-y-6">
					<div class="flex flex-col items-center gap-4 text-center">
						<CheckCircle class="h-16 w-16 text-green-600" />
						<div>
							<h3 class="text-lg font-semibold">{$t('auth.register.successTitle')}</h3>
							<p class="text-sm text-muted-foreground">
								{$t('auth.register.successMessage')}
							</p>
						</div>
					</div>

					<div class="space-y-3 rounded-lg border p-4">
						<div class="flex items-center justify-between">
							<Label class="text-sm font-medium">{$t('auth.register.accessCodeLabel')}</Label>
							<Button variant="ghost" size="sm" onclick={copyAccessCode}>
								<Copy class="h-4 w-4" />
							</Button>
						</div>
						<div class="rounded bg-muted p-3 font-mono text-lg font-bold text-center tracking-wider">
							{accessCode}
						</div>
						<Alert>
							<AlertDescription class="text-xs">
								<strong>{$t('auth.register.important')}</strong> {$t('auth.register.accessCodeWarning')}
							</AlertDescription>
						</Alert>
					</div>

					<div class="space-y-2 text-sm text-muted-foreground">
						<p><strong>{$t('auth.register.nextSteps')}</strong></p>
						<ol class="list-decimal list-inside space-y-1 ml-2">
							<li>{$t('auth.register.step1')}</li>
							<li>{$t('auth.register.step2')}</li>
							<li>{$t('auth.register.step3')}</li>
						</ol>
					</div>

					<Button class="w-full" onclick={() => goto('/login')}>
						{$t('auth.register.goToLogin')}
						<ArrowRight class="ml-2 h-4 w-4" />
					</Button>
				</div>
			{/if}
		</CardContent>
	</Card>
</div>
