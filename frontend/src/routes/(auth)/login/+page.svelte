<script lang="ts">
	import { goto } from '$app/navigation';
	import { login, isAuthenticated, isLoggingIn } from '$lib/stores/auth';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
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
	import { superForm } from 'sveltekit-superforms';
	import { ANIMATION_DURATIONS } from '$lib/constants/animations';
	import type { PageData } from './$types';
	import { t } from '$lib/i18n';

	let { data }: { data: PageData } = $props();

	// Removed onMount redirect to prevent race conditions
	// Authentication redirects are handled explicitly after successful login

	let errorMessage = $state('');

	const { form, errors, enhance, delayed } = superForm(data.form, {
		id: 'login',
		onSubmit: async ({ cancel }) => {
			// Форматирование происходит автоматически через handleInput
			errorMessage = ''; // Очищаем ошибки при новой попытке

			// Проверяем, не выполняется ли уже вход
			if ($isLoggingIn) {
				cancel();
				return;
			}

			// Если форма валидна, выполняем вход
			if ($form.access_code && $form.access_code.replace(/\D/g, '').length === 12) {
				cancel(); // Отменяем стандартную отправку формы
				const response = await login($form.access_code);
				if (!response.success) {
					errorMessage = response.error || $t('auth.login.invalidCode');
				} else {
					// Wait for auth store to actually update before navigating
					// This prevents race conditions with layout loaders
					await new Promise<void>((resolve) => {
						const unsubscribe = isAuthenticated.subscribe(val => {
							if (val) {
								unsubscribe();
								resolve();
							}
						});
						// Fallback timeout in case something goes wrong
						setTimeout(() => {
							unsubscribe();
							resolve();
						}, 2000);
					});
					goto('/dashboard');
				}
			}
		}
	});

	function formatAccessCode(value: string) {
		// Remove all non-digit characters
		const digits = value.replace(/\D/g, '');

		// Format as XXX-XXX-XXX-XXX
		const parts = [];
		for (let i = 0; i < digits.length && i < 12; i += 3) {
			parts.push(digits.slice(i, i + 3));
		}

		return parts.join('-');
	}

	function handleInput(event: Event) {
		const target = event.target as HTMLInputElement;
		const formatted = formatAccessCode(target.value);
		$form.access_code = formatted;
		target.value = formatted;
	}
</script>

<Card class="w-full max-w-md">
	<CardHeader>
		<CardTitle>{$t('auth.login.title')}</CardTitle>
		<CardDescription>{$t('auth.login.subtitle')}</CardDescription>
	</CardHeader>
	<form method="POST" use:enhance>
		<CardContent class="space-y-4">
			{#if $isLoggingIn}
				<!-- Skeleton loader во время входа -->
				<div class="space-y-3">
					<Skeleton class="h-4 w-20" />
					<Skeleton class="h-12 w-full" />
					<Skeleton class="h-4 w-3/4" />
				</div>
			{:else}
				<div
					class="space-y-2 animate-in fade-in slide-in-from-bottom-2 duration-slow"
				>
					<Label for="access-code">{$t('auth.login.accessCode')}</Label>
					<Input
						id="access-code"
						name="access_code"
						type="text"
						placeholder={$t('auth.login.accessCodePlaceholder')}
						bind:value={$form.access_code}
						oninput={handleInput}
						maxlength="15"
						class="font-mono text-lg transition-all duration-normal hover:border-primary/50 focus:scale-[1.01]"
						aria-invalid={$errors.access_code || errorMessage ? 'true' : undefined}
						autocomplete="off"
					/>
					{#if $errors.access_code}
						<p
							class="text-sm text-destructive animate-in fade-in slide-in-from-top-1 duration-normal"
						>
							{$errors.access_code}
						</p>
					{/if}
					{#if errorMessage}
						<Alert
							variant="destructive"
							class="animate-in fade-in slide-in-from-top-1 duration-slow"
						>
							<AlertDescription>{errorMessage}</AlertDescription>
						</Alert>
					{/if}
					<p class="text-sm text-muted-foreground">
						{$t('auth.login.accessCodeHelp')}
					</p>
				</div>
			{/if}
		</CardContent>
		<CardFooter class="flex flex-col space-y-4">
			<Button
				type="submit"
				class="w-full transition-all duration-normal hover:scale-[1.02]"
				disabled={$isLoggingIn || $delayed}
			>
				{#if $isLoggingIn}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{$t('auth.login.signingIn')}
				{:else}
					{$t('auth.login.signIn')}
				{/if}
			</Button>
			<p class="text-sm text-muted-foreground text-center">
				{$t('auth.login.noAccount')}
				<a
					href="/register"
					class="text-primary hover:underline transition-colors duration-normal"
				>
					{$t('auth.login.signUp')}
				</a>
			</p>
		</CardFooter>
	</form>
</Card>
