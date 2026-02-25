<script lang="ts">
	import { page } from '$app/stores';
	import { unviewedOrdersCount } from '$lib/stores/orders';
	import { unviewedTicketsCount } from '$lib/stores/tickets';
	import { user } from '$lib/stores/auth';
	import { getNavItems, getAdminNavItems } from '$lib/constants/navigation';
	import {
		TooltipProvider,
		Tooltip,
		TooltipTrigger,
		TooltipContent
	} from '$lib/components/ui/tooltip';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { cn } from '$lib/utils';
	import { SIDEBAR_WIDTH_ICON, SIDEBAR_WIDTH } from '$lib/components/ui/sidebar/constants';
	import { t } from '$lib/i18n';
	import Logo from '$lib/components/Logo.svelte';

	let isHovered = $state(false);

	// Get translated nav items
	let navItems = $derived(getNavItems((key) => $t(key)));
	let adminNavItems = $derived($user?.is_admin ? getAdminNavItems() : []);

	function isActive(href: string): boolean {
		return (
			$page.url.pathname === href ||
			(href !== '/' && $page.url.pathname.startsWith(href + '/'))
		);
	}
</script>

<aside
	class="sticky top-0 h-screen flex-shrink-0 z-40 bg-[hsl(var(--sidebar-background))] text-[hsl(var(--sidebar-foreground))] border-r border-border transition-[width] duration-200"
	style="width: {isHovered ? SIDEBAR_WIDTH : SIDEBAR_WIDTH_ICON}"
	aria-label="Primary navigation"
	onmouseenter={() => (isHovered = true)}
	onmouseleave={() => (isHovered = false)}
>
	<TooltipProvider delayDuration={150}>
		<div class="flex h-full flex-col">
			<!-- Logo/Brand Section -->
			<div class="flex h-14 items-center justify-center px-2">
				{#if isHovered}
					<Logo size="small" variant="full" />
				{:else}
					<Logo size="small" variant="compact" />
				{/if}
			</div>

			<!-- Navigation Section -->
			<nav class="mt-2 grid gap-1 px-2">
				{#each navItems as item (item.href)}
					<Tooltip open={isHovered ? false : undefined}>
						<TooltipTrigger>
							<a
								href={item.href}
								aria-label={item.ariaLabel}
								class={cn(
									'inline-flex items-center whitespace-nowrap text-sm font-medium rounded-md ring-offset-background transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
									'h-10 relative',
									isHovered ? 'justify-start gap-2 px-3 w-full' : 'justify-center w-10 mx-auto',
									isActive(item.href)
										? 'bg-accent text-accent-foreground'
										: 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
								)}
							>
								<svelte:component this={item.icon} class="h-5 w-5 flex-shrink-0" />
								{#if isHovered}
									<span>{item.label}</span>
								{:else}
									<span class="sr-only">{item.label}</span>
								{/if}

								{#if item.href === '/orders' && $unviewedOrdersCount > 0}
									<Badge
										variant="secondary"
										class={cn(
											'absolute h-5 min-w-5 px-1 text-xs bg-primary text-primary-foreground rounded-full',
											isHovered ? 'top-1/2 -translate-y-1/2 right-2' : '-top-1 -right-1'
										)}
									>
										{$unviewedOrdersCount}
									</Badge>
								{/if}

								{#if item.href === '/manual-ssn' && $unviewedTicketsCount > 0}
									<Badge
										variant="secondary"
										class={cn(
											'absolute h-5 min-w-5 px-1 text-xs bg-primary text-primary-foreground rounded-full',
											isHovered ? 'top-1/2 -translate-y-1/2 right-2' : '-top-1 -right-1'
										)}
									>
										{$unviewedTicketsCount}
									</Badge>
								{/if}
							</a>
						</TooltipTrigger>
						<TooltipContent side="right" align="center" class="select-none">
							{item.label}
						</TooltipContent>
					</Tooltip>
				{/each}

				<!-- Admin Navigation Items -->
				{#if adminNavItems.length > 0}
					<div class="my-2 border-t border-border" />
					{#each adminNavItems as item (item.href)}
						<Tooltip open={isHovered ? false : undefined}>
							<TooltipTrigger>
								<a
									href={item.href}
									aria-label={item.ariaLabel}
									class={cn(
										'inline-flex items-center whitespace-nowrap text-sm font-medium rounded-md ring-offset-background transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
										'h-10 relative',
										isHovered ? 'justify-start gap-2 px-3 w-full' : 'justify-center w-10 mx-auto',
										isActive(item.href)
											? 'bg-primary text-primary-foreground'
											: 'text-primary hover:bg-primary hover:text-primary-foreground'
									)}
								>
									<svelte:component this={item.icon} class="h-5 w-5 flex-shrink-0" />
									{#if isHovered}
										<span>{item.label}</span>
									{:else}
										<span class="sr-only">{item.label}</span>
									{/if}
								</a>
							</TooltipTrigger>
							<TooltipContent side="right" align="center" class="select-none">
								{item.label} (Admin)
							</TooltipContent>
						</Tooltip>
					{/each}
				{/if}
			</nav>
		</div>
	</TooltipProvider>
</aside>
