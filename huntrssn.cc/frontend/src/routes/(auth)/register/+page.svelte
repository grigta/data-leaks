<script lang="ts">
	import { goto } from '$app/navigation';
	import { register as registerUser, login, isAuthenticated, isRegistering } from '$lib/stores/auth';
	import { validateCoupon as validateCouponAPI } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button';
	import { Label } from '$lib/components/ui/label';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
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
	import { superForm } from 'sveltekit-superforms';
	import { ANIMATION_DURATIONS } from '$lib/constants/animations';
	import type { PageData } from './$types';
	import { t } from '$lib/i18n';
	import { toast } from 'svelte-sonner';

	let { data }: { data: PageData } = $props();

	const { form, enhance, delayed } = superForm(data.form, { id: 'register' });

	// Registration state
	let errorMessage = $state('');
	let accessCode = $state('');
	let registered = $state(false);
	let copied = $state(false);
	let isLoggingIn = $state(false);
	let couponCode = $state('');
	let isProcessing = $state(false);

	async function handleSubmit() {
		if (!couponCode.trim()) {
			errorMessage = $t('auth.errors.couponCodeRequired');
			return;
		}

		isProcessing = true;
		errorMessage = '';

		try {
			// Step 1: Validate coupon
			const validationResponse = await validateCouponAPI(couponCode.trim());

			if (!validationResponse.valid) {
				errorMessage = validationResponse.message || $t('auth.errors.couponInvalid');
				isProcessing = false;
				return;
			}

			// Check if coupon is valid for registration
			if (!validationResponse.coupon_type ||
			    (validationResponse.coupon_type !== 'registration' &&
			     validationResponse.coupon_type !== 'registration_bonus' &&
			     validationResponse.coupon_type !== 'fixed_amount')) {
				errorMessage = $t('auth.errors.couponNotForRegistration');
				isProcessing = false;
				return;
			}

			// Step 2: Register with validated coupon (no invitation code)
			const registerResponse = await registerUser(
				couponCode.trim(),
				undefined
			);

			if (registerResponse.success && registerResponse.user) {
				accessCode = registerResponse.user.access_code || '';
				registered = true;
				toast.success($t('auth.register.registrationSuccess'));
			} else {
				errorMessage = registerResponse.error || $t('auth.errors.registrationFailed');
			}
		} catch (error: any) {
			errorMessage = error.response?.data?.detail || $t('auth.errors.registrationError');
		} finally {
			isProcessing = false;
		}
	}

	async function handleContinue() {
		if (!accessCode) {
			errorMessage = $t('auth.errors.accessCodeRequired');
			return;
		}

		isLoggingIn = true;
		errorMessage = '';

		const loginResponse = await login(accessCode);
		if (loginResponse.success) {
			// Wait for auth store to actually update before navigating
			await new Promise<void>((resolve) => {
				let unsubscribe: (() => void) | undefined;
				unsubscribe = isAuthenticated.subscribe(val => {
					if (val && unsubscribe) {
						unsubscribe();
						resolve();
					}
				});
				// Fallback timeout in case something goes wrong
				setTimeout(() => {
					if (unsubscribe) {
						unsubscribe();
					}
					resolve();
				}, 2000);
			});
			goto('/dashboard');
		} else {
			isLoggingIn = false;
			errorMessage = loginResponse.error || $t('auth.errors.loginFailed');
		}
	}

	async function copyAccessCode() {
		try {
			await navigator.clipboard.writeText(accessCode);
			copied = true;
			toast.success($t('auth.register.codeCopied') || 'Код доступа скопирован');
			setTimeout(() => {
				copied = false;
			}, 2000);
		} catch (error) {
			console.error('Failed to copy access code:', error);
			toast.error($t('auth.errors.copyFailed') || 'Не удалось скопировать код');
			errorMessage = $t('auth.errors.copyFailed');
		}
	}
</script>

<Card class="w-full max-w-md">
	<CardHeader>
		<CardTitle>{$t('auth.register.title')}</CardTitle>
		<CardDescription>{$t('auth.register.subtitle')}</CardDescription>
	</CardHeader>
	<CardContent class="space-y-4">
		{#if !registered}
			<!-- Registration Form: Coupon + Invitation Code -->
			<div class="space-y-4">
				<p class="text-sm text-muted-foreground">
					{$t('auth.register.description')}
				</p>

				<div class="space-y-2">
					<Label for="coupon-code">{$t('auth.register.couponCode')}</Label>
					<Input
						id="coupon-code"
						type="text"
						placeholder={$t('auth.register.couponCodePlaceholder')}
						bind:value={couponCode}
						class="transition-all duration-normal"
						autocomplete="off"
						disabled={isProcessing || $isRegistering}
					/>
					<p class="text-xs text-muted-foreground">
						{$t('auth.register.couponCodeHelp')}
					</p>
				</div>
			</div>
		{:else}
			<!-- Access code display after successful registration -->
			<div class="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-slow">
				<Alert class="animate-in fade-in slide-in-from-top-2 duration-slower">
					<AlertDescription class="font-medium">
						{$t('auth.register.success')}
					</AlertDescription>
				</Alert>

				<div class="space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-slower">
					<Label for="access-code">{$t('auth.register.accessCode')}</Label>
					<div class="flex gap-2">
						<Input
							id="access-code"
							type="text"
							readonly
							value={accessCode}
							class="font-mono text-lg transition-all duration-slow"
							autocomplete="off"
						/>
						<Button
							variant="outline"
							size="icon"
							onclick={copyAccessCode}
							class="transition-all duration-normal hover:scale-105"
						>
							{#if copied}
								<Check class="h-4 w-4 animate-in fade-in zoom-in duration-normal" />
							{:else}
								<Copy class="h-4 w-4" />
							{/if}
						</Button>
					</div>
					<p class="text-sm text-muted-foreground">
						{$t('auth.register.accessCodeHelp')}
					</p>

					<div
						class="rounded-lg border border-warning/50 bg-warning/10 p-3 animate-in fade-in slide-in-from-bottom-1 duration-slower"
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
			<!-- Registration button -->
			<Button
				type="button"
				class="w-full transition-all duration-normal hover:scale-[1.02]"
				disabled={isProcessing || $isRegistering || !couponCode.trim()}
				onclick={handleSubmit}
			>
				{#if isProcessing || $isRegistering}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{isProcessing ? $t('auth.register.processing') : $t('auth.register.creatingAccount')}
				{:else}
					{$t('auth.register.registerButton')}
				{/if}
			</Button>
		{:else}
			<!-- Continue button after registration -->
			<Button
				type="button"
				class="w-full transition-all duration-normal hover:scale-[1.02]"
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
			<a
				href="/login"
				class="text-primary hover:underline transition-colors duration-normal"
				>{$t('auth.register.signIn')}</a
			>
		</p>
	</CardFooter>
</Card>
