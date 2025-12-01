<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { authStore, username } from '$lib/stores/auth';
	import { derived } from 'svelte/store';
	import { Button } from '$lib/components/ui/button';
	import { Avatar, AvatarFallback } from '$lib/components/ui/avatar';
	import {
		DropdownMenu,
		DropdownMenuContent,
		DropdownMenuGroup,
		DropdownMenuItem,
		DropdownMenuLabel,
		DropdownMenuSeparator,
		DropdownMenuTrigger
	} from '$lib/components/ui/dropdown-menu';
	import { Badge } from '$lib/components/ui/badge';
	import {
		LayoutDashboard,
		Ticket,
		Users,
		LogOut,
		Menu,
		X,
		Lock,
		Settings,
		Newspaper,
		UserCog,
		FileText,
		ClipboardList,
		UserCheck,
		BarChart3,
		MessageCircle,
		Mail,
		DollarSign,
		Sun,
		Moon,
		Monitor,
		UserX
	} from '@lucide/svelte';
	import { wsManager, connectionStatus, THREAD_CREATED, THREAD_MESSAGE_ADDED, CONTACT_THREAD_CREATED, CONTACT_THREAD_MESSAGE_ADDED, CONTACT_THREAD_MESSAGES_READ, TICKET_CREATED, TICKET_UPDATED } from '$lib/websocket/manager';
	import { browser } from '$app/environment';
	import type { Snippet } from 'svelte';
	import { setMode, userPrefersMode } from 'mode-watcher';
	import { getUnreadThreadsCount, getContactThreadUnreadCount, getPendingTicketsCount } from '$lib/api/client';

	interface Props {
		children?: Snippet;
	}

	let { children }: Props = $props();

	// State
	let isLoggingOut = $state(false);
	let sidebarOpen = $state(true);
	let wsConnected = $state(false);
	let unreadSupportCount = $state(0);
	let unreadContactCount = $state(0);
	let pendingTicketsCount = $state(0);

	// Get user info from auth store
	let authState = $derived($authStore);
	let userInfo = $derived(authState.user);
	let isAdmin = $derived(userInfo?.is_admin ?? false);
	let isWorker = $derived(userInfo?.worker_role ?? false);

	// Theme state
	let currentTheme = $derived($userPrefersMode);

	// Load unread support threads count
	async function loadUnreadSupportCount() {
		if (!isAdmin) return;
		try {
			unreadSupportCount = await getUnreadThreadsCount();
		} catch (error) {
			console.error('Failed to load unread support count:', error);
		}
	}

	// Decrement unread support count (called from support page)
	export function decrementUnreadSupportCount(amount: number = 1) {
		unreadSupportCount = Math.max(0, unreadSupportCount - amount);
	}

	// Load unread contact threads count
	async function loadUnreadContactCount() {
		if (!isAdmin) return;
		try {
			const response = await getContactThreadUnreadCount();
			unreadContactCount = response.count;
		} catch (error) {
			console.error('Failed to load unread contact count:', error);
		}
	}

	// Load pending tickets count
	async function loadPendingTicketsCount() {
		// Load for both workers and admins
		if (!isWorker && !isAdmin) return;
		try {
			pendingTicketsCount = await getPendingTicketsCount();
		} catch (error) {
			console.error('Failed to load pending tickets count:', error);
		}
	}

	// All navigation items with role requirements
	const allNavItems = [
		{
			href: '/dashboard',
			label: 'Панель управления',
			icon: LayoutDashboard,
			requiresAdmin: false,
			requiresWorker: false
		},
		{
			href: '/instant-ssn-stats',
			label: 'Статистика Instant SSN',
			icon: BarChart3,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/manual-ssn-stats',
			label: 'Статистика Manual SSN',
			icon: BarChart3,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/telegram-stats',
			label: 'Статистика Telegram',
			icon: MessageCircle,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/maintenance-mode',
			label: 'Технические работы',
			icon: Settings,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/workers',
			label: 'Работники',
			icon: UserCog,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/worker-requests',
			label: 'Запросы работников',
			icon: UserCheck,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/tickets',
			label: 'История тикетов',
			icon: ClipboardList,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/manual-ssn',
			label: 'Ручная обработка SSN',
			icon: FileText,
			requiresAdmin: false,
			requiresWorker: true
		},
		{
			href: '/coupons',
			label: 'Купоны',
			icon: Ticket,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/custom-pricing',
			label: 'Уникальные цены',
			icon: DollarSign,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/news',
			label: 'Новости',
			icon: Newspaper,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/users',
			label: 'Пользователи',
			icon: Users,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/bans',
			label: 'Список банов',
			icon: UserX,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/support-messages',
			label: 'Сообщения поддержки',
			icon: MessageCircle,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/contact-messages',
			label: 'Контактные сообщения',
			icon: Mail,
			requiresAdmin: true,
			requiresWorker: false
		},
		{
			href: '/settings',
			label: 'Настройки',
			icon: Settings,
			requiresAdmin: false,
			requiresWorker: false
		}
	];

	// Filter navigation items based on user role
	let navItems = $derived(
		allNavItems.filter((item) => {
			// Pure worker (worker_role=true, is_admin=false) - show ONLY worker items
			if (isWorker && !isAdmin) {
				return item.requiresWorker;
			}

			// Admin (is_admin=true, worker_role=false) - show admin items and common items, but NOT worker items
			if (isAdmin && !isWorker) {
				return !item.requiresWorker;
			}

			// Admin with worker role (is_admin=true, worker_role=true) - show everything
			if (isAdmin && isWorker) {
				return true;
			}

			// Regular user (neither admin nor worker) - show only common items
			return !item.requiresAdmin && !item.requiresWorker;
		})
	);

	// Check if route is active
	function isActive(href: string): boolean {
		return $page.url.pathname === href || $page.url.pathname.startsWith(href + '/');
	}

	// Handle logout
	async function handleLogout() {
		isLoggingOut = true;
		authStore.logout();
	}

	// Get user initials
	function getUserInitials(name: string | null): string {
		if (!name) return 'A';
		return name
			.split(' ')
			.map((n) => n[0])
			.join('')
			.toUpperCase()
			.slice(0, 2);
	}

	// Setup WebSocket
	function setupWebSocket() {
		if (!browser) return;

		const token = localStorage.getItem('admin_access_token');
		if (token) {
			wsManager.connect(token);

			// Subscribe to connection status changes
			connectionStatus.subscribe((status) => {
				wsConnected = status;
			});
		}
	}

	// Cleanup WebSocket
	function cleanupWebSocket() {
		wsManager.disconnect();
	}

	onMount(() => {
		setupWebSocket();
		loadUnreadSupportCount();
		loadUnreadContactCount();
		loadPendingTicketsCount();

		// Subscribe to WebSocket events for unread support count
		const unsubscribeThreadCreated = wsManager.on(THREAD_CREATED, () => {
			loadUnreadSupportCount();
		});

		const unsubscribeMessageAdded = wsManager.on(THREAD_MESSAGE_ADDED, (data: any) => {
			// Increment count only for new user messages
			if (data.message_type === 'user') {
				unreadSupportCount = unreadSupportCount + 1;
			}
		});

		// Subscribe to WebSocket events for unread contact count
		const unsubscribeContactThreadCreated = wsManager.on(CONTACT_THREAD_CREATED, () => {
			loadUnreadContactCount();
		});

		const unsubscribeContactMessageAdded = wsManager.on(CONTACT_THREAD_MESSAGE_ADDED, (data: any) => {
			// Increment count only for new user messages
			if (data.message_type === 'user') {
				unreadContactCount = unreadContactCount + 1;
			}
		});

		const unsubscribeContactMessagesRead = wsManager.on(CONTACT_THREAD_MESSAGES_READ, () => {
			loadUnreadContactCount();
		});

		// Subscribe to WebSocket events for pending tickets count
		const unsubscribeTicketCreated = wsManager.on(TICKET_CREATED, () => {
			loadPendingTicketsCount();
		});

		const unsubscribeTicketUpdated = wsManager.on(TICKET_UPDATED, (data: any) => {
			// Reload count when ticket status changes
			loadPendingTicketsCount();
		});

		return () => {
			unsubscribeThreadCreated();
			unsubscribeMessageAdded();
			unsubscribeContactThreadCreated();
			unsubscribeContactMessageAdded();
			unsubscribeContactMessagesRead();
			unsubscribeTicketCreated();
			unsubscribeTicketUpdated();
		};
	});

	onDestroy(() => {
		cleanupWebSocket();
	});
</script>

<div class="flex h-screen overflow-hidden bg-background">
	<!-- Sidebar -->
	<aside
		class="flex w-64 flex-col border-r bg-card transition-all duration-300"
		class:hidden={!sidebarOpen}
	>
		<!-- Logo/Brand -->
		<div class="flex h-16 items-center gap-2 border-b px-6">
			<Lock class="h-6 w-6 text-primary" />
			<span class="text-lg font-semibold">Админ панель</span>
		</div>

		<!-- Navigation -->
		<nav class="flex-1 space-y-1 p-4">
			{#each navItems as item}
				{@const Icon = item.icon}
				<Button
					variant={isActive(item.href) ? 'default' : 'ghost'}
					class="w-full justify-start relative"
					onclick={() => goto(item.href)}
				>
					<Icon class="mr-2 h-4 w-4" />
					{item.label}
					{#if item.href === '/support-messages' && unreadSupportCount > 0}
						<Badge variant="destructive" class="ml-auto text-xs">
							{unreadSupportCount}
						</Badge>
					{/if}
					{#if item.href === '/contact-messages' && unreadContactCount > 0}
						<Badge variant="destructive" class="ml-auto text-xs">
							{unreadContactCount}
						</Badge>
					{/if}
					{#if item.href === '/manual-ssn' && pendingTicketsCount > 0}
						<Badge variant="destructive" class="ml-auto text-xs">
							{pendingTicketsCount}
						</Badge>
					{/if}
				</Button>
			{/each}
		</nav>

		<!-- Bottom section -->
		<div class="border-t p-4">
			<!-- User menu -->
			<DropdownMenu>
				<DropdownMenuTrigger>
					{#snippet child({ props })}
						<Button {...props} variant="outline" class="w-full justify-start">
							<Avatar class="mr-2 h-6 w-6">
								<AvatarFallback>{getUserInitials($username)}</AvatarFallback>
							</Avatar>
							<span class="flex-1 truncate text-left">{$username || 'Admin'}</span>
						</Button>
					{/snippet}
				</DropdownMenuTrigger>
				<DropdownMenuContent class="w-56" align="end">
					<DropdownMenuLabel>Мой аккаунт</DropdownMenuLabel>
					<DropdownMenuSeparator />
					<DropdownMenuGroup>
						<DropdownMenuLabel>Тема оформления</DropdownMenuLabel>
						<DropdownMenuItem
							onclick={() => setMode('light')}
							class={currentTheme === 'light' ? 'bg-accent' : ''}
						>
							<Sun class="mr-2 h-4 w-4" />
							Светлая
						</DropdownMenuItem>
						<DropdownMenuItem
							onclick={() => setMode('dark')}
							class={currentTheme === 'dark' ? 'bg-accent' : ''}
						>
							<Moon class="mr-2 h-4 w-4" />
							Тёмная
						</DropdownMenuItem>
						<DropdownMenuItem
							onclick={() => setMode('system')}
							class={currentTheme === 'system' ? 'bg-accent' : ''}
						>
							<Monitor class="mr-2 h-4 w-4" />
							Системная
						</DropdownMenuItem>
					</DropdownMenuGroup>
					<DropdownMenuSeparator />
					<DropdownMenuGroup>
						<DropdownMenuItem onclick={handleLogout} disabled={isLoggingOut}>
							<LogOut class="mr-2 h-4 w-4" />
							{isLoggingOut ? 'Выход из системы...' : 'Выход'}
						</DropdownMenuItem>
					</DropdownMenuGroup>
				</DropdownMenuContent>
			</DropdownMenu>
		</div>
	</aside>

	<!-- Main content -->
	<div class="flex flex-1 flex-col overflow-hidden">
		<!-- Header -->
		<header class="flex h-16 items-center justify-between border-b bg-card px-6">
			<div class="flex items-center gap-4">
				<Button variant="ghost" size="icon" onclick={() => (sidebarOpen = !sidebarOpen)}>
					{#if sidebarOpen}
						<X class="h-5 w-5" />
					{:else}
						<Menu class="h-5 w-5" />
					{/if}
				</Button>

				<h1 class="text-xl font-semibold">
					{#if $page.url.pathname.includes('dashboard')}
						Панель управления
					{:else if $page.url.pathname.includes('instant-ssn-stats')}
						Статистика Instant SSN
					{:else if $page.url.pathname.includes('manual-ssn-stats')}
						Статистика Manual SSN
					{:else if $page.url.pathname.includes('telegram-stats')}
						Статистика Telegram
					{:else if $page.url.pathname.includes('workers') && !$page.url.pathname.includes('worker-requests')}
						Управление работниками
					{:else if $page.url.pathname.includes('worker-requests')}
						Запросы работников
					{:else if $page.url.pathname.includes('tickets')}
						История тикетов
					{:else if $page.url.pathname.includes('manual-ssn')}
						Ручная обработка SSN
					{:else if $page.url.pathname.includes('coupons')}
						Управление купонами
					{:else if $page.url.pathname.includes('maintenance-mode')}
						Технические работы
					{:else if $page.url.pathname.includes('custom-pricing')}
						Уникальные цены
					{:else if $page.url.pathname.includes('news')}
						Управление новостями
					{:else if $page.url.pathname.includes('users')}
						Управление пользователями
					{:else if $page.url.pathname.includes('bans')}
						Список банов
					{:else if $page.url.pathname.includes('settings')}
						Настройки
					{:else}
						Админ панель
					{/if}
				</h1>
			</div>

			<div class="flex items-center gap-2">
				{#if wsConnected}
					<Badge variant="outline" class="text-green-600 border-green-600">
						<span class="mr-1 h-2 w-2 rounded-full bg-green-600"></span>
						Подключено
					</Badge>
				{:else}
					<Badge variant="outline" class="text-red-600 border-red-600">
						<span class="mr-1 h-2 w-2 rounded-full bg-red-600"></span>
						Отключено
					</Badge>
				{/if}
				<Badge variant="secondary">Администратор</Badge>
			</div>
		</header>

		<!-- Page content -->
		<main class="flex-1 overflow-y-auto bg-background p-6">
			<div class="mx-auto max-w-7xl">
				{@render children?.()}
			</div>
		</main>
	</div>
</div>
