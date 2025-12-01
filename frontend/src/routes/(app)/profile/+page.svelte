<script lang="ts">
	import { onMount } from 'svelte';
	import { user, logout, setUser } from '$lib/stores/auth';
	import { updateProfile, changePassword, setPassword, handleApiError, getInvitationCode, getInvitationStats } from '$lib/api/client';
	import { formatCurrency } from '$lib/utils';
	import { t } from '$lib/i18n';
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import {
		Dialog,
		DialogContent,
		DialogDescription,
		DialogFooter,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import Pencil from '@lucide/svelte/icons/pencil';
	import Info from '@lucide/svelte/icons/info';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import Users from '@lucide/svelte/icons/users';
	import { ANIMATION_DURATIONS } from '$lib/constants/animations';
	import type { AxiosError } from 'axios';

	// Edit field dialog state
	let editDialogOpen = false;
	let editFieldName = '';
	let editFieldLabel = '';
	let editFieldValue = '';
	let editFieldPlaceholder = '';

	// Change password dialog state
	let passwordDialogOpen = false;
	let currentPassword = '';
	let newPassword = '';
	let confirmPassword = '';
	let hasPassword = false;

	// Messages
	let successMessage = '';
	let errorMessage = '';
	let loading = false;
	let isLoggingOut = false;

	// Invitation/Referral state
	let invitationCode = $state('');
	let invitationStats = $state<{ total_invited: number; total_bonus_earned: number } | null>(null);
	let loadingInvitation = $state(false);
	let invitationCopied = $state(false);

	$effect(() => {
		if ($user) {
			hasPassword = !$user.access_code?.includes('-'); // Простая проверка
		}
	});

	async function handleLogout() {
		isLoggingOut = true;
		await logout();
		// logout() теперь сам делает редирект
	}

	function openEditDialog(field: 'telegram' | 'jabber' | 'email') {
		editFieldName = field;
		editFieldLabel = field === 'telegram' ? $t('profile.telegram') : field === 'jabber' ? $t('profile.jabber') : $t('profile.email');
		editFieldValue = ($user?.[field] as string) || '';
		editFieldPlaceholder =
			field === 'telegram'
				? '@username'
				: field === 'jabber'
					? 'user@server.com'
					: 'email@example.com';
		editDialogOpen = true;
		successMessage = '';
		errorMessage = '';
	}

	async function handleEditField() {
		if (!editFieldValue.trim()) {
			errorMessage = $t('profile.errors.fieldEmpty');
			return;
		}

		loading = true;
		errorMessage = '';
		successMessage = '';

		try {
			const data: any = {};
			data[editFieldName] = editFieldValue;
			const updated = await updateProfile(data);

			// Обновить store через setUser вместо записи в derived store
			setUser(updated);

			successMessage = $t('profile.success.fieldUpdated').replace('{{field}}', editFieldLabel);
			setTimeout(() => {
				editDialogOpen = false;
				successMessage = '';
			}, 1500);
		} catch (err) {
			errorMessage = handleApiError(err as AxiosError);
		} finally {
			loading = false;
		}
	}

	function openPasswordDialog() {
		passwordDialogOpen = true;
		currentPassword = '';
		newPassword = '';
		confirmPassword = '';
		successMessage = '';
		errorMessage = '';
	}

	async function handleChangePassword() {
		if (hasPassword && !currentPassword) {
			errorMessage = $t('profile.errors.currentPasswordRequired');
			return;
		}

		if (!newPassword || newPassword.length < 8) {
			errorMessage = $t('profile.errors.passwordTooShort');
			return;
		}

		if (newPassword !== confirmPassword) {
			errorMessage = $t('profile.errors.passwordsNoMatch');
			return;
		}

		loading = true;
		errorMessage = '';
		successMessage = '';

		try {
			if (hasPassword) {
				await changePassword(currentPassword, newPassword);
			} else {
				await setPassword(newPassword);
			}

			successMessage = $t('profile.success.passwordSet');
			setTimeout(() => {
				passwordDialogOpen = false;
				successMessage = '';
				hasPassword = true;
			}, 1500);
		} catch (err) {
			errorMessage = handleApiError(err as AxiosError);
		} finally {
			loading = false;
		}
	}

	async function loadInvitationData() {
		loadingInvitation = true;
		try {
			const [codeResponse, statsResponse] = await Promise.all([
				getInvitationCode(),
				getInvitationStats()
			]);
			invitationCode = codeResponse.invitation_code;
			invitationStats = {
				total_invited: statsResponse.total_invited,
				total_bonus_earned: statsResponse.total_bonus_earned
			};
		} catch (error) {
			console.error('Failed to load invitation data:', error);
		} finally {
			loadingInvitation = false;
		}
	}

	async function copyInvitationCode() {
		try {
			await navigator.clipboard.writeText(invitationCode);
			invitationCopied = true;
			toast.success('Код приглашения скопирован');
			setTimeout(() => {
				invitationCopied = false;
			}, 2000);
		} catch (error) {
			console.error('Failed to copy invitation code:', error);
			toast.error('Не удалось скопировать код');
		}
	}

	onMount(() => {
		loadInvitationData();
	});
</script>

<div class="container mx-auto max-w-4xl space-y-6">
	<!-- Top buttons -->
	<div class="flex items-center justify-between">
		<h1 class="text-3xl font-bold">{$t('profile.title')}</h1>
		<div class="flex gap-3">
			<Button href="/balance" class="transition-all duration-normal"
				>{$t('profile.deposit')}</Button
			>
			<Button
				variant="outline"
				on:click={handleLogout}
				disabled={isLoggingOut}
				class="transition-all duration-normal"
			>
				{#if isLoggingOut}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{$t('profile.loggingOut')}
				{:else}
					{$t('profile.logout')}
				{/if}
			</Button>
		</div>
	</div>

	<!-- Profile card -->
	<Card class="border">
		<CardHeader>
			<CardTitle class="text-2xl">{$user?.username}</CardTitle>
			<p class="text-sm text-muted-foreground">{$t('profile.balance')} {formatCurrency($user?.balance || 0)}</p>
		</CardHeader>
		<CardContent class="space-y-4">
			<!-- Telegram field -->
			<div class="flex items-center justify-between">
				<div class="flex-1">
					<Label class="text-sm text-muted-foreground">{$t('profile.telegram')}</Label>
					<p class="text-base">{$user?.telegram || $t('profile.notSet')}</p>
				</div>
				<Button
					variant="ghost"
					size="icon"
					on:click={() => openEditDialog('telegram')}
					aria-label="Edit Telegram"
				>
					<Pencil class="h-4 w-4" />
				</Button>
			</div>

			<!-- Jabber field -->
			<div class="flex items-center justify-between">
				<div class="flex-1">
					<Label class="text-sm text-muted-foreground">{$t('profile.jabber')}</Label>
					<p class="text-base">{$user?.jabber || $t('profile.notSet')}</p>
				</div>
				<Button
					variant="ghost"
					size="icon"
					on:click={() => openEditDialog('jabber')}
					aria-label="Edit Jabber"
				>
					<Pencil class="h-4 w-4" />
				</Button>
			</div>

			<!-- Email field -->
			<div class="flex items-center justify-between">
				<div class="flex-1">
					<Label class="text-sm text-muted-foreground flex items-center gap-1">
						{$t('profile.email')}
						<Info class="h-3 w-3" />
					</Label>
					<p class="text-base">{$user?.email || $t('profile.notSet')}</p>
				</div>
				<Button
					variant="ghost"
					size="icon"
					on:click={() => openEditDialog('email')}
					aria-label="Edit Email"
				>
					<Pencil class="h-4 w-4" />
				</Button>
			</div>

			<!-- Change password button -->
			<div class="pt-4">
				<Button variant="outline" class="w-full" on:click={openPasswordDialog}>
					{hasPassword ? $t('profile.changePassword') : $t('profile.setPassword')}
				</Button>
			</div>
		</CardContent>
	</Card>

	<!-- Invitation/Referral Card -->
	<Card class="border">
		<CardHeader>
			<CardTitle class="text-2xl flex items-center gap-2">
				<Users class="h-6 w-6" />
				Реферальная программа
			</CardTitle>
		</CardHeader>
		<CardContent class="space-y-4">
			{#if loadingInvitation}
				<div class="space-y-2">
					<Skeleton class="h-4 w-full" />
					<Skeleton class="h-10 w-full" />
				</div>
			{:else}
				<div class="space-y-2">
					<Label class="text-sm text-muted-foreground">Ваш код приглашения</Label>
					<div class="flex gap-2">
						<Input
							type="text"
							readonly
							value={invitationCode}
							class="font-mono text-lg"
						/>
						<Button
							variant="outline"
							size="icon"
							on:click={copyInvitationCode}
						>
							{#if invitationCopied}
								<Check class="h-4 w-4" />
							{:else}
								<Copy class="h-4 w-4" />
							{/if}
						</Button>
					</div>
					<p class="text-xs text-muted-foreground">
						Поделитесь этим кодом с друзьями. Они получат бонус при регистрации, а вы получите вознаграждение!
					</p>
				</div>

				{#if invitationStats}
					<div class="grid grid-cols-2 gap-4 pt-4">
						<div class="space-y-1">
							<Label class="text-sm text-muted-foreground">Приглашено пользователей</Label>
							<p class="text-2xl font-bold">{invitationStats.total_invited}</p>
						</div>
						<div class="space-y-1">
							<Label class="text-sm text-muted-foreground">Заработано бонусов</Label>
							<p class="text-2xl font-bold">{formatCurrency(invitationStats.total_bonus_earned)}</p>
						</div>
					</div>
				{/if}
			{/if}
		</CardContent>
	</Card>
</div>

<!-- Edit Field Dialog -->
<Dialog bind:open={editDialogOpen}>
	<DialogContent>
		<DialogHeader>
			<DialogTitle>{$t('profile.editField').replace('{{field}}', editFieldLabel)}</DialogTitle>
			<DialogDescription>{$t('profile.updateField').replace('{{field}}', editFieldLabel.toLowerCase())}</DialogDescription>
		</DialogHeader>

		{#if successMessage}
			<Alert>
				<AlertDescription>{successMessage}</AlertDescription>
			</Alert>
		{/if}

		{#if errorMessage}
			<Alert variant="destructive">
				<AlertDescription>{errorMessage}</AlertDescription>
			</Alert>
		{/if}

		<div class="space-y-4">
			<div>
				<Label for="edit-field">{editFieldLabel}</Label>
				<Input
					id="edit-field"
					type="text"
					placeholder={editFieldPlaceholder}
					bind:value={editFieldValue}
					disabled={loading}
				/>
			</div>
		</div>

		<DialogFooter>
			<Button variant="outline" on:click={() => (editDialogOpen = false)} disabled={loading}>
				{$t('profile.cancel')}
			</Button>
			<Button on:click={handleEditField} disabled={loading}>
				{loading ? $t('profile.saving') : $t('profile.save')}
			</Button>
		</DialogFooter>
	</DialogContent>
</Dialog>

<!-- Change Password Dialog -->
<Dialog bind:open={passwordDialogOpen}>
	<DialogContent>
		<DialogHeader>
			<DialogTitle>{hasPassword ? $t('profile.changePassword') : $t('profile.setPassword')}</DialogTitle>
			<DialogDescription>
				{hasPassword
					? $t('profile.enterCurrent')
					: $t('profile.setPasswordDesc')}
			</DialogDescription>
		</DialogHeader>

		{#if successMessage}
			<Alert>
				<AlertDescription>{successMessage}</AlertDescription>
			</Alert>
		{/if}

		{#if errorMessage}
			<Alert variant="destructive">
				<AlertDescription>{errorMessage}</AlertDescription>
			</Alert>
		{/if}

		<div class="space-y-4">
			{#if hasPassword}
				<div>
					<Label for="current-password">{$t('profile.currentPassword')}</Label>
					<Input
						id="current-password"
						type="password"
						bind:value={currentPassword}
						disabled={loading}
					/>
				</div>
			{/if}

			<div>
				<Label for="new-password">{$t('profile.newPassword')}</Label>
				<Input
					id="new-password"
					type="password"
					placeholder={$t('profile.newPasswordPlaceholder')}
					bind:value={newPassword}
					disabled={loading}
				/>
			</div>

			<div>
				<Label for="confirm-password">{$t('profile.confirmPassword')}</Label>
				<Input
					id="confirm-password"
					type="password"
					placeholder={$t('profile.confirmPasswordPlaceholder')}
					bind:value={confirmPassword}
					disabled={loading}
				/>
			</div>
		</div>

		<DialogFooter>
			<Button variant="outline" on:click={() => (passwordDialogOpen = false)} disabled={loading}>
				{$t('profile.cancel')}
			</Button>
			<Button on:click={handleChangePassword} disabled={loading}>
				{loading ? $t('profile.saving') : hasPassword ? $t('profile.changePassword') : $t('profile.setPassword')}
			</Button>
		</DialogFooter>
	</DialogContent>
</Dialog>
