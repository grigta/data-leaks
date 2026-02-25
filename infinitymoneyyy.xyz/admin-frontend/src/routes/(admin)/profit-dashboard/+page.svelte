<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import {
		getProfitDashboard,
		clearProfitDashboardStats,
		type ProfitDashboardResponse,
		handleApiError
	} from '$lib/api/client';
	import {
		Dialog,
		DialogContent,
		DialogDescription,
		DialogFooter,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import { formatCurrency, formatNumber } from '$lib/utils';
	import {
		TrendingUp,
		DollarSign,
		Search,
		Zap,
		FileText,
		RefreshCw,
		Loader2,
		Clock,
		Trash2
	} from '@lucide/svelte';
	import { t } from '$lib/i18n';

	// State
	let data = $state<ProfitDashboardResponse | null>(null);
	let isLoading = $state(true);
	let error = $state('');
	let selectedPeriod = $state('all');
	let showClearDialog = $state(false);
	let isClearing = $state(false);

	const periods = [
		{ value: '1d', labelKey: 'dashboard.periods.24h' },
		{ value: '7d', labelKey: 'dashboard.periods.7d' },
		{ value: '30d', labelKey: 'dashboard.periods.30d' },
		{ value: 'all', labelKey: 'dashboard.periods.all' }
	];

	async function loadData() {
		isLoading = true;
		error = '';
		try {
			data = await getProfitDashboard({ period: selectedPeriod });
		} catch (err: any) {
			error = handleApiError(err);
		} finally {
			isLoading = false;
		}
	}

	function handlePeriodChange(period: string) {
		selectedPeriod = period;
		loadData();
	}

	function fmtPct(val: number): string {
		return val.toFixed(1) + '%';
	}

	function fmtTime(seconds: number | null): string {
		if (seconds === null || seconds === undefined) return '—';
		if (seconds < 60) return seconds.toFixed(1) + ' ' + $t('dashboard.time.sec');
		const mins = Math.floor(seconds / 60);
		const secs = Math.round(seconds % 60);
		return mins + ' ' + $t('dashboard.time.min') + ' ' + secs + ' ' + $t('dashboard.time.sec');
	}

	function fmtMinutes(minutes: number | null): string {
		if (minutes === null || minutes === undefined) return '—';
		if (minutes < 60) return minutes.toFixed(1) + ' ' + $t('dashboard.time.min');
		const hours = Math.floor(minutes / 60);
		const mins = Math.round(minutes % 60);
		return hours + ' ' + $t('dashboard.time.h') + ' ' + mins + ' ' + $t('dashboard.time.min');
	}

	async function handleClear(period: string) {
		isClearing = true;
		try {
			await clearProfitDashboardStats({ period });
			showClearDialog = false;
			await loadData();
		} catch (err: any) {
			error = handleApiError(err);
		} finally {
			isClearing = false;
		}
	}

	onMount(() => {
		loadData();
	});
</script>

<div class="space-y-6">
	<!-- Period selector -->
	<div class="flex items-center gap-2">
		{#each periods as period}
			<Button
				variant={selectedPeriod === period.value ? 'default' : 'outline'}
				size="sm"
				onclick={() => handlePeriodChange(period.value)}
			>
				{$t(period.labelKey)}
			</Button>
		{/each}
		<Button variant="outline" size="sm" onclick={loadData} disabled={isLoading}>
			{#if isLoading}
				<Loader2 class="h-4 w-4 animate-spin" />
			{:else}
				<RefreshCw class="h-4 w-4" />
			{/if}
		</Button>
		<Button variant="outline" size="sm" onclick={() => showClearDialog = true} class="text-destructive hover:text-destructive">
			<Trash2 class="h-4 w-4 mr-1" />
			{$t('dashboard.clear.button')}
		</Button>
	</div>

	<!-- Clear stats dialog -->
	<Dialog bind:open={showClearDialog}>
		<DialogContent class="sm:max-w-md">
			<DialogHeader>
				<DialogTitle>{$t('dashboard.clear.title')}</DialogTitle>
				<DialogDescription>{$t('dashboard.clear.description')}</DialogDescription>
			</DialogHeader>
			<DialogFooter class="flex gap-2 sm:justify-start">
				<Button variant="destructive" size="sm" onclick={() => handleClear('1d')} disabled={isClearing}>
					{$t('dashboard.clear.last24h')}
				</Button>
				<Button variant="destructive" size="sm" onclick={() => handleClear('all')} disabled={isClearing}>
					{$t('dashboard.clear.all')}
				</Button>
				<Button variant="outline" size="sm" onclick={() => showClearDialog = false} disabled={isClearing}>
					{$t('dashboard.clear.cancel')}
				</Button>
			</DialogFooter>
		</DialogContent>
	</Dialog>

	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	{#if isLoading && !data}
		<div class="grid gap-4 md:grid-cols-3">
			{#each Array(3) as _}
				<Card>
					<CardHeader class="pb-2">
						<div class="h-4 w-24 animate-pulse rounded bg-muted"></div>
					</CardHeader>
					<CardContent>
						<div class="h-8 w-32 animate-pulse rounded bg-muted"></div>
					</CardContent>
				</Card>
			{/each}
		</div>
	{:else if data}
		<!-- Общее -->
		<div>
			<h3 class="mb-3 text-lg font-semibold">{$t('dashboard.general.title')}</h3>
			<div class="grid gap-4 md:grid-cols-4">
				<Card class="border border-border">
					<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.general.totalProfit')}</CardTitle>
						<DollarSign class="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold {data.total_profit >= 0 ? 'text-green-600' : 'text-red-600'}">
							{formatCurrency(data.total_profit)}
						</div>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.general.totalRoi')}</CardTitle>
						<TrendingUp class="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold">
							{fmtPct(data.total_roi)}
						</div>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.general.deposits')}</CardTitle>
						<DollarSign class="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold">
							{formatCurrency(data.total_deposits)}
						</div>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.general.avgDeposit')}</CardTitle>
						<DollarSign class="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold">
							{formatCurrency(data.avg_deposit)}
						</div>
					</CardContent>
				</Card>
			</div>
		</div>

		<!-- Инстант (Instant SSN) -->
		<div>
			<h3 class="mb-3 text-lg font-semibold flex items-center gap-2">
				<Zap class="h-5 w-5 text-yellow-500" />
				{$t('dashboard.instant.title')}
				<span class="text-xs font-normal text-muted-foreground">{$t('dashboard.instant.costInfo')}</span>
			</h3>
			<div class="grid gap-4 md:grid-cols-4">
				<Card class="border border-border">
					<CardHeader class="pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.instant.profit')}</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold {data.instant_profit >= 0 ? 'text-green-600' : 'text-red-600'}">
							{formatCurrency(data.instant_profit)}
						</div>
						<p class="text-xs text-muted-foreground mt-1">
							{$t('dashboard.instant.revenue')}: {formatCurrency(data.instant_revenue)} | {$t('dashboard.instant.cost')}: {formatCurrency(data.instant_cost)}
						</p>
						<p class="text-xs text-muted-foreground">
							{$t('dashboard.instant.successful')}: {formatNumber(data.instant_successful)} | {$t('dashboard.instant.attempts')}: {formatNumber(data.instant_total_attempts)}
						</p>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.instant.roi')}</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold {data.instant_roi >= 0 ? 'text-green-600' : 'text-red-600'}">
							{fmtPct(data.instant_roi)}
						</div>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.instant.successRate')}</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold">
							{fmtPct(data.instant_success_rate)}
						</div>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.instant.avgTime')}</CardTitle>
						<Clock class="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold">
							{fmtTime(data.instant_avg_search_time)}
						</div>
					</CardContent>
				</Card>
			</div>
		</div>

		<!-- Ручной пробив (Manual SSN) -->
		<div>
			<h3 class="mb-3 text-lg font-semibold flex items-center gap-2">
				<FileText class="h-5 w-5 text-blue-500" />
				{$t('dashboard.manual.title')}
				<span class="text-xs font-normal text-muted-foreground">{$t('dashboard.manual.costInfo')}</span>
			</h3>
			<div class="grid gap-4 md:grid-cols-4">
				<Card class="border border-border">
					<CardHeader class="pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.instant.profit')}</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold {data.manual_profit >= 0 ? 'text-green-600' : 'text-red-600'}">
							{formatCurrency(data.manual_profit)}
						</div>
						<p class="text-xs text-muted-foreground mt-1">
							{$t('dashboard.instant.revenue')}: {formatCurrency(data.manual_revenue)} | {$t('dashboard.instant.cost')}: {formatCurrency(data.manual_cost)}
						</p>
						<p class="text-xs text-muted-foreground">
							{$t('dashboard.instant.successful')}: {formatNumber(data.manual_successful)} | {$t('dashboard.instant.attempts')}: {formatNumber(data.manual_total_attempts)}
						</p>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.instant.roi')}</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold {data.manual_roi >= 0 ? 'text-green-600' : 'text-red-600'}">
							{fmtPct(data.manual_roi)}
						</div>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.instant.successRate')}</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold">
							{fmtPct(data.manual_success_rate)}
						</div>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.instant.avgTime')}</CardTitle>
						<Clock class="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold">
							{fmtMinutes(data.manual_avg_response_time)}
						</div>
					</CardContent>
				</Card>
			</div>
		</div>

		<!-- Статистика пробивов -->
		<div>
			<h3 class="mb-3 text-lg font-semibold flex items-center gap-2">
				<Search class="h-5 w-5 text-purple-500" />
				{$t('dashboard.stats.title')}
			</h3>
			<div class="grid gap-4 md:grid-cols-4">
				<Card class="border border-border">
					<CardHeader class="pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.stats.totalAttempts')}</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold">{formatNumber(data.total_searches)}</div>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.stats.instant')}</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold text-green-600">{formatNumber(data.instant_found)}</div>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.stats.manual')}</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold text-blue-600">{formatNumber(data.manual_found)}</div>
					</CardContent>
				</Card>
				<Card class="border border-border">
					<CardHeader class="pb-2">
						<CardTitle class="text-sm font-medium">{$t('dashboard.stats.notFound')}</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold text-orange-600">{formatNumber(data.not_found)}</div>
					</CardContent>
				</Card>
			</div>
		</div>
	{/if}
</div>
