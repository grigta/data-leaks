import type { ComponentType } from 'svelte';
import Home from '@lucide/svelte/icons/home';
import Search from '@lucide/svelte/icons/search';
import Repeat from '@lucide/svelte/icons/repeat';
import FileText from '@lucide/svelte/icons/file-text';
import Package from '@lucide/svelte/icons/package';
import Wallet from '@lucide/svelte/icons/wallet';
import Code from '@lucide/svelte/icons/code';
import HelpCircle from '@lucide/svelte/icons/help-circle';
import MessageCircle from '@lucide/svelte/icons/message-circle';

export interface NavItem {
	href: string;
	label: string;
	icon: ComponentType;
	ariaLabel: string;
}

type TranslateFunction = (key: string) => string;

export function getNavItems(t: TranslateFunction): NavItem[] {
	return [
		{
			href: '/dashboard',
			label: t('navigation.dashboard'),
			icon: Home,
			ariaLabel: `Navigate to ${t('navigation.dashboard')}`
		},
		{
			href: '/lookup-ssn',
			label: t('navigation.instantSSN'),
			icon: Search,
			ariaLabel: `Navigate to ${t('navigation.instantSSN')}`
		},
		{
			href: '/manual-ssn',
			label: t('navigation.manualSSN'),
			icon: FileText,
			ariaLabel: `Navigate to ${t('navigation.manualSSN')}`
		},
		{
			href: '/orders',
			label: t('navigation.orders'),
			icon: Package,
			ariaLabel: `Navigate to ${t('navigation.orders')}`
		},
		{
			href: '/api',
			label: t('navigation.api'),
			icon: Code,
			ariaLabel: `Navigate to ${t('navigation.api')}`
		},
		{
			href: '/telegram',
			label: t('navigation.telegram'),
			icon: MessageCircle,
			ariaLabel: `Navigate to ${t('navigation.telegram')}`
		},
		{
			href: '/support',
			label: t('navigation.support'),
			icon: HelpCircle,
			ariaLabel: `Navigate to ${t('navigation.support')}`
		}
	];
}

// Deprecated: use getNavItems() instead
export const NAV_ITEMS: NavItem[] = [
	{
		href: '/dashboard',
		label: 'Dashboard',
		icon: Home,
		ariaLabel: 'Navigate to Dashboard'
	},
	{
		href: '/lookup-ssn',
		label: 'Instant SSN',
		icon: Search,
		ariaLabel: 'Navigate to Instant SSN'
	},
	{
		href: '/manual-ssn',
		label: 'Manual SSN',
		icon: FileText,
		ariaLabel: 'Navigate to Manual SSN'
	},
	{
		href: '/orders',
		label: 'Orders',
		icon: Package,
		ariaLabel: 'Navigate to Orders'
	},
	{
		href: '/api',
		label: 'API',
		icon: Code,
		ariaLabel: 'Navigate to API'
	},
	{
		href: '/telegram',
		label: 'Telegram Bot',
		icon: MessageCircle,
		ariaLabel: 'Navigate to Telegram Bot'
	},
	{
		href: '/support',
		label: 'Support',
		icon: HelpCircle,
		ariaLabel: 'Navigate to Support'
	}
];
