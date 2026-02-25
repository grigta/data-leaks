<script lang="ts">
	import { goto } from '$app/navigation';
	import { register as registerUser, login, isAuthenticated, isRegistering } from '$lib/stores/auth';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import {
		Card,
		CardHeader,
		CardTitle,
		CardDescription,
		CardContent,
		CardFooter
	} from '$lib/components/ui/card';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import KeyRound from '@lucide/svelte/icons/key-round';
	import { t } from '$lib/i18n';
	import { toast } from 'svelte-sonner';

	// Registration state
	let errorMessage = $state('');
	let accessCode = $state('');
	let registered = $state(false);
	let copied = $state(false);
	let isLoggingIn = $state(false);
	let isProcessing = $state(false);

	async function handleGenerate() {
		isProcessing = true;
		errorMessage = '';

		try {
			const registerResponse = await registerUser();

			if (registerResponse.success && registerResponse.user) {
				accessCode = registerResponse.user.access_code || '';
				registered = true;
			} else {
				errorMessage = registerResponse.error || 'Registration failed';
			}
		} catch (error: any) {
			errorMessage = error.response?.data?.detail || 'Registration error';
		} finally {
			isProcessing = false;
		}
	}

	async function handleContinue() {
		if (!accessCode) return;

		isLoggingIn = true;
		errorMessage = '';

		const loginResponse = await login(accessCode);
		if (loginResponse.success) {
			await new Promise<void>((resolve) => {
				let unsubscribe: (() => void) | undefined;
				unsubscribe = isAuthenticated.subscribe(val => {
					if (val && unsubscribe) {
						unsubscribe();
						resolve();
					}
				});
				setTimeout(() => {
					if (unsubscribe) unsubscribe();
					resolve();
				}, 2000);
			});
			goto('/search');
		} else {
			isLoggingIn = false;
			errorMessage = loginResponse.error || 'Login failed';
		}
	}

	async function copyAccessCode() {
		try {
			await navigator.clipboard.writeText(accessCode);
			copied = true;
			toast.success('Access code copied');
			setTimeout(() => { copied = false; }, 2000);
		} catch (error) {
			console.error('Failed to copy access code:', error);
		}
	}
</script>

<Card class="w-full max-w-md">
	<CardHeader>
		<CardTitle class="font-semibold">{$t('auth.register.title')}</CardTitle>
		<CardDescription>{$t('auth.register.subtitle')}</CardDescription>
	</CardHeader>
	<CardContent class="space-y-4">
		{#if !registered}
			<p class="text-sm text-muted-foreground">
				Click the button below to generate your unique access code. You will use it to log in.
			</p>
		{:else}
			<!-- Access code display after successful registration -->
			<div class="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-slow">
				<Alert class="animate-in fade-in slide-in-from-top-2 duration-slower">
					<AlertDescription class="font-medium">
						{$t('auth.register.success')}
					</AlertDescription>
				</Alert>

				<div class="space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-slower">
					<div class="flex gap-2">
						<Input
							id="access-code"
							type="text"
							readonly
							value={accessCode}
							class="font-mono text-lg"
							autocomplete="off"
						/>
						<Button
							variant="outline"
							size="icon"
							onclick={copyAccessCode}
						>
							{#if copied}
								<Check class="h-4 w-4 animate-in fade-in zoom-in duration-normal" />
							{:else}
								<Copy class="h-4 w-4" />
							{/if}
						</Button>
					</div>

					<div
						class="border border-warning/50 bg-warning/10 rounded-lg p-3 animate-in fade-in slide-in-from-bottom-1 duration-slower"
					>
						<p class="text-xs text-warning font-medium">
							{$t('auth.register.warning')}
						</p>
					</div>
				</div>
			</div>
		{/if}

		{#if errorMessage}
			<Alert variant="destructive" class="animate-in fade-in slide-in-from-top-1 duration-slow">
				<AlertDescription>{errorMessage}</AlertDescription>
			</Alert>
		{/if}
	</CardContent>
	<CardFooter class="flex flex-col space-y-4">
		{#if !registered}
			<Button
				type="button"
				class="w-full font-heading"
				disabled={isProcessing || $isRegistering}
				onclick={handleGenerate}
			>
				{#if isProcessing || $isRegistering}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					Generating...
				{:else}
					<KeyRound class="mr-2 h-4 w-4" />
					Generate Access Code
				{/if}
			</Button>
		{:else}
			<Button
				type="button"
				class="w-full font-heading"
				disabled={isLoggingIn || !accessCode}
				onclick={handleContinue}
			>
				{#if isLoggingIn}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{$t('auth.register.continuing')}
				{:else}
					{$t('auth.register.continue')}
				{/if}
			</Button>
		{/if}
		<p class="text-sm text-muted-foreground text-center">
			{$t('auth.register.haveAccount')}
			<a href="/login" class="text-primary hover:underline">{$t('auth.register.signIn')}</a>
		</p>
	</CardFooter>
</Card>
