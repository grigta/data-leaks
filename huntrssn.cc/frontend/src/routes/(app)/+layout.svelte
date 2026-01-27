<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { browser, dev } from '$app/environment';
	import { user, logout } from '$lib/stores/auth';
	import { loadUnviewedOrdersCount } from '$lib/stores/orders';
	import { loadUnviewedTicketsCount, unviewedTicketsCount, incrementUnviewedTicketsCount } from '$lib/stores/tickets';
	import { checkSubscriptionAccess, type CheckAccessResponse } from '$lib/api/client';
	import { formatCurrency } from '$lib/utils';
	import { Avatar, AvatarFallback } from '$lib/components/ui/avatar';
	import { Badge } from '$lib/components/ui/badge';
	import {
		DropdownMenu,
		DropdownMenuTrigger,
		DropdownMenuContent,
		DropdownMenuItem,
		DropdownMenuLabel,
		DropdownMenuSeparator
	} from '$lib/components/ui/dropdown-menu';
	import CompactSidebar from '$lib/components/CompactSidebar.svelte';
	import Wallet from '@lucide/svelte/icons/wallet';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Globe from '@lucide/svelte/icons/globe';
	import FileText from '@lucide/svelte/icons/file-text';
	import CreditCard from '@lucide/svelte/icons/credit-card';
	import { ANIMATION_DURATIONS } from '$lib/constants/animations';
	import { currentLanguage } from '$lib/stores/language';
	import { t } from '$lib/i18n';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import { toast } from 'svelte-sonner';
	import { isAuthenticated } from '$lib/stores/auth';
	import { wsManager, TICKET_COMPLETED, TICKET_UPDATED } from '$lib/websocket/client';
	import ApplyCouponModal from '$lib/components/ApplyCouponModal.svelte';
	import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '$lib/components/ui/dialog';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';

	let { children, data } = $props();
	let showBanDialog = $state(false);

	function getUserInitials(username?: string): string {
		if (!username) return 'U';
		return username.slice(0, 2).toUpperCase();
	}

	let copied = $state(false);
	let isLoggingOut = $state(false);
	let codeVisible = $state(false);
	let showCouponModal = $state(false);
	let subscriptionStatus = $state<CheckAccessResponse | null>(null);

	function toggleCodeVisibility() {
		codeVisible = !codeVisible;
	}

	async function copyAccessCode() {
		if (!$user?.access_code) return;
		try {
			await navigator.clipboard.writeText($user.access_code);
			copied = true;
			toast.success('Код доступа скопирован');
			setTimeout(() => {
				copied = false;
			}, ANIMATION_DURATIONS.slower);
		} catch (error) {
			console.error('Failed to copy access code:', error);
			toast.error('Не удалось скопировать код');
		}
	}

	async function handleLogout() {
		isLoggingOut = true;
		await logout();
		// logout() теперь сам делает редирект
	}

	function toggleLanguage() {
		currentLanguage.toggle();
	}

	function openCouponModal() {
		showCouponModal = true;
	}

	function handleCouponSuccess(newBalance: number) {
		// Update user balance in store
		if ($user) {
			$user.balance = newBalance;
		}
		toast.success('Купон успешно применён!');
		showCouponModal = false;
	}

	async function loadSubscriptionStatus() {
		try {
			subscriptionStatus = await checkSubscriptionAccess();
		} catch (error) {
			console.error('Failed to load subscription status:', error);
		}
	}

	// Load unviewed orders and tickets count on mount after auth is initialized
	onMount(() => {
		loadUnviewedOrdersCount();
		loadUnviewedTicketsCount();
		loadSubscriptionStatus();

		// Initialize WebSocket connection based on user role
		if (browser) {
			const token = localStorage.getItem('access_token');
			if (token && $user) {
				try {
					// Admins and workers connect to admin WebSocket
					// Regular users connect to public WebSocket
					const endpoint = ($user.is_admin || $user.worker_role)
						? '/api/admin/ws'
						: '/api/public/ws';

					wsManager.connect(token, endpoint);
					dev && console.log(`[App Layout] WebSocket connection initialized to ${endpoint}`);

					// Глобальная подписка на события завершения тикетов
					wsManager.on(TICKET_COMPLETED, (data: any) => {
						if ($user && data.user_id === $user.id) {
							incrementUnviewedTicketsCount();
							toast.info('Ваш запрос на ручной пробив выполнен!');
						}
					});

					// Подписка на обновления тикетов (если статус стал completed)
					wsManager.on(TICKET_UPDATED, (data: any) => {
						if ($user && data.user_id === $user.id && data.status === 'completed') {
							incrementUnviewedTicketsCount();
							toast.info('Ваш запрос на ручной пробив выполнен!');
						}
					});
				} catch (error) {
					console.error('[App Layout] Failed to initialize WebSocket:', error);
				}
			}
		}
	});

	// Reactive redirect based on auth state
	// This handles the case where auth state changes after initial load
	$effect(() => {
		if (data?.needsAuth && !$isAuthenticated) {
			console.debug('[App Layout] Auth required, redirecting to login');
			// Disconnect WebSocket when logging out
			wsManager.disconnect();
			goto('/login');
		}
	});

	// Check for ban status
	$effect(() => {
		if ($user?.is_banned) {
			console.debug('[App Layout] User is banned, showing ban dialog');
			showBanDialog = true;
		} else {
			showBanDialog = false;
		}
	});
</script>

<div class="flex min-h-screen w-full">
	<CompactSidebar />

	<!-- Main content -->
	<div class="flex flex-1 flex-col">
		<!-- Header -->
		<header class="sticky top-0 z-10 bg-background px-6 py-3">
			<div class="flex items-center justify-between">
				<!-- Left side - Empty for now -->
				<div></div>

				<!-- Right side - Theme Toggle, Unviewed Tickets Badge, Balance Badge and Avatar with Dropdown -->
				<div class="flex items-center gap-4">
					<!-- Theme Toggle -->
					<ThemeToggle />

					<!-- Unviewed Tickets Badge -->
					{#if $unviewedTicketsCount > 0}
						<a href="/manual-ssn" class="transition-opacity duration-normal hover:opacity-80">
							<Badge variant="secondary" class="flex items-center gap-1 cursor-pointer transition-transform duration-normal hover:scale-105">
								<FileText class="h-3 w-3" />
								{$unviewedTicketsCount} new
							</Badge>
						</a>
					{/if}

					<!-- Subscription Status Badge -->
					{#if subscriptionStatus?.has_access}
						<a href="/subscription" class="transition-opacity duration-normal hover:opacity-80">
							<Badge variant="outline" class="flex items-center gap-1 cursor-pointer transition-transform duration-normal hover:scale-105 bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-300 dark:border-green-800">
								<CreditCard class="h-3 w-3" />
								Active
							</Badge>
						</a>
					{:else if subscriptionStatus !== null}
						<a href="/subscription" class="transition-opacity duration-normal hover:opacity-80">
							<Badge variant="outline" class="flex items-center gap-1 cursor-pointer transition-transform duration-normal hover:scale-105 bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950 dark:text-orange-300 dark:border-orange-800">
								<CreditCard class="h-3 w-3" />
								No Sub
							</Badge>
						</a>
					{/if}

					<!-- Balance Badge -->
					<a href="/balance" class="transition-opacity duration-normal hover:opacity-80">
						<Badge variant="outline" class="flex items-center gap-1 cursor-pointer transition-transform duration-normal hover:scale-105">
							<Wallet class="h-3 w-3" />
							{formatCurrency($user?.balance || 0)}
						</Badge>
					</a>

					<!-- User Avatar with Dropdown -->
					<DropdownMenu>
						<DropdownMenuTrigger class="rounded-full transition-opacity hover:opacity-80 cursor-pointer">
							<Avatar>
								<AvatarFallback>{getUserInitials($user?.username)}</AvatarFallback>
							</Avatar>
						</DropdownMenuTrigger>
						<DropdownMenuContent align="end" class="min-w-[250px]">
							<div class="flex items-center justify-between gap-2 px-2 py-2">
								<span
									class="font-mono text-lg font-bold text-foreground cursor-pointer select-none transition-all duration-300"
									class:blur-sm={!codeVisible}
									onclick={toggleCodeVisibility}
									role="button"
									tabindex="0"
								>
									{$user?.access_code || 'N/A'}
								</span>
								<button
									onclick={copyAccessCode}
									class="flex-shrink-0 rounded-md p-1.5 hover:bg-accent transition-colors duration-normal"
									type="button"
									disabled={isLoggingOut}
								>
									{#if copied}
										<Check class="h-4 w-4 animate-in fade-in zoom-in duration-normal" />
									{:else}
										<Copy class="h-4 w-4" />
									{/if}
								</button>
							</div>

							<DropdownMenuSeparator />

							<DropdownMenuItem onclick={() => goto('/crypto-deposit')} disabled={isLoggingOut}>
								{$t('navigation.addBalance')}
							</DropdownMenuItem>

							<DropdownMenuItem onclick={openCouponModal} disabled={isLoggingOut}>
								Применить купон
							</DropdownMenuItem>

							<DropdownMenuSeparator />

							<DropdownMenuItem onclick={toggleLanguage} disabled={isLoggingOut}>
								<Globe class="mr-2 h-4 w-4" />
								{$currentLanguage === 'en' ? 'Русский' : 'English'}
							</DropdownMenuItem>

							<DropdownMenuSeparator />

							<DropdownMenuItem onclick={handleLogout} disabled={isLoggingOut}>
								{#if isLoggingOut}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									{$t('navigation.loggingOut')}
								{:else}
									{$t('navigation.logout')}
								{/if}
							</DropdownMenuItem>

							<DropdownMenuSeparator />

							<div class="px-2 py-2">
								<div class="text-xs text-muted-foreground text-center">
									{$user?.username || 'N/A'}
								</div>
							</div>
						</DropdownMenuContent>
					</DropdownMenu>
				</div>
			</div>
		</header>

		<!-- Main content area -->
		<main class="flex-1 overflow-y-auto p-6">
			{@render children?.()}
		</main>
	</div>
</div>

<!-- Ban Dialog -->
<Dialog bind:open={showBanDialog}>
	<DialogContent class="max-w-md">
		<DialogHeader>
			<div class="flex items-center gap-3 mb-2">
				<div class="rounded-full bg-destructive/10 p-3">
					<AlertCircle class="h-6 w-6 text-destructive" />
				</div>
				<DialogTitle class="text-xl">Доступ заблокирован</DialogTitle>
			</div>
			<DialogDescription class="text-base mt-4">
				Ваш аккаунт был заблокирован администрацией.
			</DialogDescription>
		</DialogHeader>

		<div class="space-y-4 py-4">
			{#if $user?.ban_reason}
				<div class="rounded-lg bg-muted p-4">
					<h4 class="text-sm font-medium mb-2">Причина блокировки:</h4>
					<p class="text-sm text-muted-foreground">{$user.ban_reason}</p>
				</div>
			{/if}

			{#if $user?.banned_at}
				<div class="text-xs text-muted-foreground">
					Заблокирован: {new Date($user.banned_at).toLocaleString('ru-RU')}
				</div>
			{/if}

			<div class="pt-2 border-t">
				<p class="text-sm text-muted-foreground mb-2">
					Для получения дополнительной информации или оспаривания блокировки, пожалуйста, свяжитесь с администрацией.
				</p>
				{#if $user?.id}
					<div class="text-xs text-muted-foreground/60 mt-4">
						User ID: {$user.id}
					</div>
				{/if}
			</div>
		</div>
	</DialogContent>
</Dialog>

<ApplyCouponModal
	open={showCouponModal}
	onClose={() => showCouponModal = false}
	onSuccess={handleCouponSuccess}
/>
