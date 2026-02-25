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
		Users,
		LogOut,
		Menu,
		X,
		Lock,
		Sun,
		Moon,
		Monitor,
		TrendingUp,
		MessageSquare,
		Wrench,
		AlertTriangle,
		ShoppingCart,
		Settings,
		Globe,
		FlaskConical
	} from '@lucide/svelte';
	import { wsManager, connectionStatus } from '$lib/websocket/manager';
	import { browser } from '$app/environment';
	import type { Snippet } from 'svelte';
	import { setMode, userPrefersMode } from 'mode-watcher';
	import { t } from '$lib/i18n';
	import { currentLanguage } from '$lib/stores/language';

	interface Props {
		children?: Snippet;
	}

	let { children }: Props = $props();

	// State
	let isLoggingOut = $state(false);
	let sidebarOpen = $state(true);
	let wsConnected = $state(false);

	// Get user info from auth store
	let authState = $derived($authStore);
	let userInfo = $derived(authState.user);
	let isAdmin = $derived(userInfo?.is_admin ?? false);

	// Theme state
	let currentTheme = $derived($userPrefersMode);

	// Navigation items
	const navKeys = [
		{ href: '/profit-dashboard', labelKey: 'navigation.profitDashboard', icon: TrendingUp, requiresAdmin: true },
		{ href: '/profit-users', labelKey: 'navigation.profitUsers', icon: Users, requiresAdmin: true },
		{ href: '/report', labelKey: 'navigation.report', icon: MessageSquare, requiresAdmin: true },
		{ href: '/workers', labelKey: 'navigation.workers', icon: Wrench, requiresAdmin: true },
		{ href: '/error-logs', labelKey: 'navigation.apiErrors', icon: AlertTriangle, requiresAdmin: true },
		{ href: '/orders', labelKey: 'navigation.allOrders', icon: ShoppingCart, requiresAdmin: true },
		{ href: '/test-polygon', labelKey: 'navigation.testPolygon', icon: FlaskConical, requiresAdmin: true },
		{ href: '/settings', labelKey: 'navigation.settings', icon: Settings, requiresAdmin: true }
	];

	let navItems = $derived(
		navKeys.filter((item) => {
			if (isAdmin) return true;
			return !item.requiresAdmin;
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

	// Get page title key from path
	function getPageTitleKey(pathname: string): string {
		if (pathname.includes('profit-dashboard')) return 'navigation.profitDashboard';
		if (pathname.includes('profit-users')) return 'navigation.profitUsers';
		if (pathname.includes('report')) return 'navigation.report';
		if (pathname.includes('workers')) return 'navigation.workers';
		if (pathname.includes('error-logs')) return 'navigation.apiErrors';
		if (pathname.includes('orders')) return 'navigation.allOrders';
		if (pathname.includes('test-polygon')) return 'navigation.testPolygon';
		if (pathname.includes('settings')) return 'navigation.settings';
		return 'navigation.adminPanel';
	}

	// Toggle language
	function toggleLanguage() {
		currentLanguage.toggle();
	}

	// Setup WebSocket
	function setupWebSocket() {
		if (!browser) return;

		const token = localStorage.getItem('admin_access_token');
		if (token) {
			wsManager.connect(token);

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
			<span class="text-lg font-semibold">{$t('navigation.adminPanel')}</span>
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
					{$t(item.labelKey)}
				</Button>
			{/each}
		</nav>

		<!-- Bottom section -->
		<div class="border-t p-4">
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
					<DropdownMenuLabel>{$t('navigation.myAccount')}</DropdownMenuLabel>
					<DropdownMenuSeparator />
					<DropdownMenuGroup>
						<DropdownMenuLabel>{$t('navigation.theme')}</DropdownMenuLabel>
						<DropdownMenuItem
							onclick={() => setMode('light')}
							class={currentTheme === 'light' ? 'bg-accent' : ''}
						>
							<Sun class="mr-2 h-4 w-4" />
							{$t('navigation.themeLight')}
						</DropdownMenuItem>
						<DropdownMenuItem
							onclick={() => setMode('dark')}
							class={currentTheme === 'dark' ? 'bg-accent' : ''}
						>
							<Moon class="mr-2 h-4 w-4" />
							{$t('navigation.themeDark')}
						</DropdownMenuItem>
						<DropdownMenuItem
							onclick={() => setMode('system')}
							class={currentTheme === 'system' ? 'bg-accent' : ''}
						>
							<Monitor class="mr-2 h-4 w-4" />
							{$t('navigation.themeSystem')}
						</DropdownMenuItem>
					</DropdownMenuGroup>
					<DropdownMenuSeparator />
					<DropdownMenuGroup>
						<DropdownMenuItem onclick={handleLogout} disabled={isLoggingOut}>
							<LogOut class="mr-2 h-4 w-4" />
							{isLoggingOut ? $t('navigation.loggingOut') : $t('navigation.logout')}
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
					{$t(getPageTitleKey($page.url.pathname))}
				</h1>
			</div>

			<div class="flex items-center gap-2">
				<Button
					variant="ghost"
					size="icon"
					onclick={toggleLanguage}
					title={$currentLanguage === 'en' ? 'Switch to Russian' : 'Switch to English'}
				>
					<Globe class="h-4 w-4" />
				</Button>
				{#if wsConnected}
					<Badge variant="outline" class="text-green-600 border-green-600">
						<span class="mr-1 h-2 w-2 rounded-full bg-green-600"></span>
						{$t('common.connected')}
					</Badge>
				{:else}
					<Badge variant="outline" class="text-red-600 border-red-600">
						<span class="mr-1 h-2 w-2 rounded-full bg-red-600"></span>
						{$t('common.disconnected')}
					</Badge>
				{/if}
				<Badge variant="secondary">{$t('common.administrator')}</Badge>
			</div>
		</header>

		<!-- Page content -->
		<main class="flex-1 overflow-y-auto bg-background p-6">
			<div class="mx-auto">
				{@render children?.()}
			</div>
		</main>
	</div>
</div>
