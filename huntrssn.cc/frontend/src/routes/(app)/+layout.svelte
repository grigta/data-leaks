<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { browser, dev } from '$app/environment';
	import { get } from 'svelte/store';
	import { user, logout, initComplete } from '$lib/stores/auth';
	import { loadUnviewedOrdersCount } from '$lib/stores/orders';
	import { loadUnviewedTicketsCount, unviewedTicketsCount, incrementUnviewedTicketsCount } from '$lib/stores/tickets';
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
	import { Button } from '$lib/components/ui/button';
	import Wallet from '@lucide/svelte/icons/wallet';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Globe from '@lucide/svelte/icons/globe';
	import FileText from '@lucide/svelte/icons/file-text';

	import Ticket from '@lucide/svelte/icons/ticket';
	import Eye from '@lucide/svelte/icons/eye';
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import LogOut from '@lucide/svelte/icons/log-out';
	import Sun from '@lucide/svelte/icons/sun';
	import Moon from '@lucide/svelte/icons/moon';
	import UserIcon from '@lucide/svelte/icons/user';
	import { ANIMATION_DURATIONS } from '$lib/constants/animations';
	import { currentLanguage } from '$lib/stores/language';
	import { currentTheme } from '$lib/stores/theme';
	import { dateFormat } from '$lib/stores/dateFormat';
	import CalendarDays from '@lucide/svelte/icons/calendar-days';
	import { t } from '$lib/i18n';
	import { toast } from 'svelte-sonner';
	import { isAuthenticated } from '$lib/stores/auth';
	import { wsManager, TICKET_COMPLETED, TICKET_UPDATED, BALANCE_UPDATED } from '$lib/websocket/client';
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
	let dropdownOpen = $state(false);

	const isDark = $derived($currentTheme === 'dark');

	function navigateAndClose(path: string) {
		dropdownOpen = false;
		goto(path);
	}

	function toggleTheme() {
		currentTheme.set(isDark ? 'light' : 'dark');
	}


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

	// Load unviewed orders and tickets count on mount after auth is initialized
	let wsInitialized = false;

	function connectWebSocket() {
		if (wsInitialized || !browser) return;
		const currentUser = get(user);
		if (!currentUser) return;

		const token = localStorage.getItem('access_token');
		if (!token) return;

		wsInitialized = true;
		try {
			// Main site always uses public WebSocket (admin WS is only for admin panel)
			const endpoint = '/api/public/ws';

			wsManager.connect(token, endpoint);

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

			// Подписка на обновления баланса в реальном времени
			wsManager.on(BALANCE_UPDATED, (data: any) => {
				if ($user && data.new_balance != null) {
					$user.balance = data.new_balance;
				}
			});
		} catch (error) {
			console.error('[App Layout] Failed to initialize WebSocket:', error);
		}
	}

	onMount(() => {
		loadUnviewedOrdersCount();
		loadUnviewedTicketsCount();

		// Connect WebSocket when auth is ready
		if (browser) {
			// Try immediately (user might already be loaded)
			connectWebSocket();

			// If not ready yet, poll until initComplete
			if (!wsInitialized) {
				const interval = setInterval(() => {
					if (get(initComplete)) {
						connectWebSocket();
						clearInterval(interval);
					}
				}, 200);
				// Safety cleanup after 15s
				setTimeout(() => clearInterval(interval), 15000);
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
		<header class="sticky top-0 z-10 bg-background px-6 py-3 border-b border-border">
			<div class="flex items-center justify-between">
				<!-- Left side -->
				<div></div>

				<!-- Right side -->
				<div class="flex items-center gap-4">
					<!-- Language Toggle -->
					<button
						onclick={toggleLanguage}
						class="h-8 w-8 rounded-md flex items-center justify-center hover:bg-accent transition-colors duration-normal"
						aria-label={$currentLanguage === 'en' ? 'Switch to Russian' : 'Switch to English'}
						title={$currentLanguage === 'en' ? 'Русский' : 'English'}
					>
						<Globe class="h-4 w-4 text-muted-foreground" />
					</button>

					<!-- Date Format Toggle -->
					<button
						onclick={() => dateFormat.toggle()}
						class="h-8 rounded-md px-1.5 flex items-center justify-center gap-1 hover:bg-accent transition-colors duration-normal"
						aria-label="Toggle date format"
						title={$dateFormat === 'ddmm' ? 'DD/MM → MM/DD' : 'MM/DD → DD/MM'}
					>
						<CalendarDays class="h-3.5 w-3.5 text-muted-foreground" />
						<span class="text-xs text-muted-foreground font-medium">{$dateFormat === 'ddmm' ? 'DD/MM' : 'MM/DD'}</span>
					</button>

					<!-- Theme Toggle -->
					<button
						onclick={toggleTheme}
						class="h-8 w-8 rounded-md flex items-center justify-center hover:bg-accent transition-colors duration-normal"
						aria-label="Toggle theme"
					>
						{#if isDark}
							<Moon class="h-4 w-4 text-muted-foreground" />
						{:else}
							<Sun class="h-4 w-4 text-muted-foreground" />
						{/if}
					</button>

					<!-- Balance Badge -->
					<a href="/balance" class="transition-opacity duration-normal hover:opacity-80">
						<Badge variant="outline" class="flex items-center gap-1 cursor-pointer">
							<Wallet class="h-3 w-3" />
							{formatCurrency($user?.balance || 0)}
						</Badge>
					</a>

					<!-- User Avatar with Mega Dropdown -->
					<DropdownMenu bind:open={dropdownOpen}>
						<DropdownMenuTrigger class="transition-opacity hover:opacity-80 cursor-pointer">
							<Avatar>
								<AvatarFallback>
									<UserIcon class="h-4 w-4" />
								</AvatarFallback>
							</Avatar>
						</DropdownMenuTrigger>
						<DropdownMenuContent align="end" class="w-[380px] p-0 overflow-hidden">
							<!-- Section 1: User Info -->
							<div class="bg-gradient-to-r from-accent/60 to-transparent p-4">
								<div class="flex items-center gap-3">
									<Avatar class="h-11 w-11">
										<AvatarFallback class="bg-primary text-primary-foreground font-bold text-sm">
											<UserIcon class="h-5 w-5" />
										</AvatarFallback>
									</Avatar>
									<div class="flex-1 min-w-0">
										<div class="flex items-center gap-2">
											<span class="text-sm font-semibold truncate">{$user?.username || 'N/A'}</span>
											<Badge variant="secondary" class="text-[10px] px-1.5 py-0">User</Badge>
										</div>
										<p class="text-xl font-bold tabular-nums mt-0.5">
											{formatCurrency($user?.balance || 0)}
										</p>
									</div>
								</div>
							</div>

							<DropdownMenuSeparator class="m-0" />

							<!-- Section 2: Quick Actions -->
							<div class="px-4 py-3">
								<p class="text-xs text-muted-foreground font-medium pb-2">{$t('navigation.quickActions')}</p>
								<div class="flex gap-2">
									<Button
										size="sm"
										class="flex-1"
										onclick={() => navigateAndClose('/balance')}
										disabled={isLoggingOut}
									>
										<Wallet class="mr-1.5 h-3.5 w-3.5" />
										{$t('navigation.deposit')}
									</Button>
									<Button
										variant="outline"
										size="sm"
										class="flex-1"
										onclick={openCouponModal}
										disabled={isLoggingOut}
									>
										<Ticket class="mr-1.5 h-3.5 w-3.5" />
										{$t('navigation.coupon')}
									</Button>
								</div>
							</div>

							<DropdownMenuSeparator class="m-0" />

							<!-- Section 3: Access Code -->
							<div class="px-4 py-3">
								<p class="text-xs text-muted-foreground font-medium pb-2">{$t('navigation.accessCode')}</p>
								<div class="flex items-center gap-2">
									<div class="flex-1 flex items-center bg-muted/50 border border-border rounded-md px-3 py-1.5">
										<span
											class="font-mono text-sm font-semibold text-foreground select-none transition-all duration-300 flex-1"
											class:blur-sm={!codeVisible}
										>
											{$user?.access_code || 'N/A'}
										</span>
									</div>
									<button
										onclick={toggleCodeVisibility}
										class="flex-shrink-0 rounded-md p-2 hover:bg-accent transition-colors duration-normal"
										type="button"
										aria-label={codeVisible ? 'Hide code' : 'Show code'}
									>
										{#if codeVisible}
											<EyeOff class="h-4 w-4 text-muted-foreground" />
										{:else}
											<Eye class="h-4 w-4 text-muted-foreground" />
										{/if}
									</button>
									<button
										onclick={copyAccessCode}
										class="flex-shrink-0 rounded-md p-2 hover:bg-accent transition-colors duration-normal"
										type="button"
										disabled={isLoggingOut}
										aria-label="Copy access code"
									>
										{#if copied}
											<Check class="h-4 w-4 text-[hsl(var(--success))] animate-in fade-in zoom-in duration-normal" />
										{:else}
											<Copy class="h-4 w-4 text-muted-foreground" />
										{/if}
									</button>
								</div>
							</div>

							<DropdownMenuSeparator class="m-0" />

							<!-- Section 4: Footer Actions -->
							<div class="bg-muted/30 px-4 py-2.5 flex items-center justify-end">
								<button
									onclick={handleLogout}
									class="h-9 w-9 rounded-md flex items-center justify-center hover:bg-destructive/10 transition-colors duration-normal"
									disabled={isLoggingOut}
									aria-label={$t('navigation.logout')}
									title={$t('navigation.logout')}
								>
									{#if isLoggingOut}
										<Loader2 class="h-4 w-4 text-destructive animate-spin" />
									{:else}
										<LogOut class="h-4 w-4 text-destructive" />
									{/if}
								</button>
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
				<div class="border border-border bg-muted/50 rounded-lg p-4">
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
