import type { ComponentType } from 'svelte';
import Package from '@lucide/svelte/icons/package';
import HelpCircle from '@lucide/svelte/icons/help-circle';
import Bug from '@lucide/svelte/icons/bug';
import Database from '@lucide/svelte/icons/database';
import Search from '@lucide/svelte/icons/search';
import FlaskConical from '@lucide/svelte/icons/flask-conical';

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
			href: '/search',
			label: t('navigation.search'),
			icon: Search,
			ariaLabel: `Navigate to ${t('navigation.search')}`
		},
		{
			href: '/test-search',
			label: t('navigation.testSearch'),
			icon: FlaskConical,
			ariaLabel: `Navigate to ${t('navigation.testSearch')}`
		},
		{
			href: '/orders',
			label: t('navigation.orders'),
			icon: Package,
			ariaLabel: `Navigate to ${t('navigation.orders')}`
		},
		{
			href: '/support',
			label: t('navigation.support'),
			icon: HelpCircle,
			ariaLabel: `Navigate to ${t('navigation.support')}`
		}
	];
}

export function getAdminNavItems(): NavItem[] {
	return [
		{
			href: '/debug-flow',
			label: 'Debug Flow',
			icon: Bug,
			ariaLabel: 'Navigate to Debug Flow'
		},
		{
			href: '/search-db',
			label: 'Search DB',
			icon: Database,
			ariaLabel: 'Navigate to Search DB'
		}
	];
}

// Deprecated: use getNavItems() instead
export const NAV_ITEMS: NavItem[] = [
	{
		href: '/search',
		label: 'Search',
		icon: Search,
		ariaLabel: 'Navigate to Search'
	},
	{
		href: '/orders',
		label: 'Orders',
		icon: Package,
		ariaLabel: 'Navigate to Orders'
	},
	{
		href: '/support',
		label: 'Support',
		icon: HelpCircle,
		ariaLabel: 'Navigate to Support'
	}
];
