<script lang="ts">
	import { onMount } from 'svelte';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Progress } from '$lib/components/ui/progress';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import {
		Bot,
		TrendingUp,
		TrendingDown,
		DollarSign,
		Users,
		Clock,
		CheckCircle,
		XCircle,
		AlertCircle,
		Activity
	} from 'lucide-svelte';
	import { getInstantSSNStats, getManualSSNStats } from '$lib/api/client';

	let selectedPeriod = $state('7d');
	let isLoading = $state(true);
	let error = $state<string | null>(null);

	// Instant SSN stats
	let instantStats = $state({
		telegram_total_attempts: 0,
		telegram_successful: 0,
		telegram_failed: 0,
		telegram_success_rate: 0,
		telegram_revenue: 0,
		telegram_api_cost: 0,
		telegram_net_profit: 0
	});

	// Manual SSN stats
	let manualStats = $state({
		telegram_total_attempts: 0,
		telegram_successful: 0,
		telegram_failed: 0,
		telegram_pending: 0,
		telegram_processing: 0,
		telegram_success_rate: 0,
		telegram_revenue: 0,
		telegram_processing_cost: 0,
		telegram_net_profit: 0,
		telegram_avg_response_time: 0
	});

	// Combined stats
	let totalRequests = $derived(instantStats.telegram_total_attempts + manualStats.telegram_total_attempts);
	let totalRevenue = $derived(instantStats.telegram_revenue + manualStats.telegram_revenue);
	let totalCosts = $derived(instantStats.telegram_api_cost + manualStats.telegram_processing_cost);
	let totalProfit = $derived(instantStats.telegram_net_profit + manualStats.telegram_net_profit);
	let overallSuccessRate = $derived(
		totalRequests > 0
			? ((instantStats.telegram_successful + manualStats.telegram_successful) / totalRequests * 100)
			: 0
	);

	async function loadStats() {
		try {
			isLoading = true;
			error = null;

			const [instantData, manualData] = await Promise.all([
				getInstantSSNStats({ period: selectedPeriod }),
				getManualSSNStats({ period: selectedPeriod })
			]);

			// Calculate telegram proportion for instant stats
			const instantTelegramRatio = instantData.total_successful > 0
				? (instantData.telegram_successful || 0) / instantData.total_successful
				: 0;

			// Update instant stats with proportional financial calculations
			instantStats = {
				telegram_total_attempts: instantData.telegram_total_attempts || 0,
				telegram_successful: instantData.telegram_successful || 0,
				telegram_failed: instantData.telegram_failed || 0,
				telegram_success_rate: instantData.telegram_success_rate || 0,
				telegram_revenue: (instantData.revenue || 0) * instantTelegramRatio,
				telegram_api_cost: (instantData.api_cost || 0) * instantTelegramRatio,
				telegram_net_profit: ((instantData.revenue || 0) - (instantData.api_cost || 0)) * instantTelegramRatio
			};

			// Calculate telegram proportion for manual stats
			const manualTelegramRatio = manualData.total_successful > 0
				? (manualData.telegram_successful || 0) / manualData.total_successful
				: 0;

			// Update manual stats with proportional financial calculations
			manualStats = {
				telegram_total_attempts: manualData.telegram_total_attempts || 0,
				telegram_successful: manualData.telegram_successful || 0,
				telegram_failed: manualData.telegram_failed || 0,
				telegram_pending: manualData.telegram_pending || 0,
				telegram_processing: manualData.telegram_processing || 0,
				telegram_success_rate: manualData.telegram_success_rate || 0,
				telegram_revenue: (manualData.revenue || 0) * manualTelegramRatio,
				telegram_processing_cost: (manualData.processing_cost || 0) * manualTelegramRatio,
				telegram_net_profit: ((manualData.revenue || 0) - (manualData.processing_cost || 0)) * manualTelegramRatio,
				telegram_avg_response_time: manualData.telegram_avg_response_time || 0
			};
		} catch (err: any) {
			console.error('Failed to load Telegram stats:', err);
			error = err.response?.data?.detail || err.message || 'Failed to load statistics';
		} finally {
			isLoading = false;
		}
	}

	onMount(() => {
		loadStats();
	});

	// Reload stats when period changes
	$effect(() => {
		if (selectedPeriod) {
			loadStats();
		}
	});

	function formatCurrency(amount: number): string {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: 'USD'
		}).format(amount);
	}

	function formatNumber(num: number): string {
		return new Intl.NumberFormat('en-US').format(num);
	}

	function formatMinutes(minutes: number): string {
		if (minutes < 60) {
			return `${Math.round(minutes)} min`;
		}
		const hours = Math.floor(minutes / 60);
		const mins = Math.round(minutes % 60);
		return `${hours}h ${mins}m`;
	}

	function getPeriodLabel(period: string): string {
		switch (period) {
			case '1d': return 'Today';
			case '7d': return 'Last 7 days';
			case '30d': return 'Last 30 days';
			case 'all': return 'All time';
			default: return period;
		}
	}
</script>

<div class="space-y-6 p-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div class="flex items-center gap-3">
			<Bot class="h-8 w-8 text-primary" />
			<div>
				<h1 class="text-3xl font-bold">Telegram Bot Statistics</h1>
				<p class="text-muted-foreground">Track all requests from Telegram bot</p>
			</div>
		</div>

		<!-- Period selector -->
		<div class="flex items-center gap-2">
			<select
				bind:value={selectedPeriod}
				class="flex h-10 w-[180px] items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
			>
				<option value="1d">Today</option>
				<option value="7d">Last 7 days</option>
				<option value="30d">Last 30 days</option>
				<option value="all">All time</option>
			</select>
		</div>
	</div>

	<!-- Error alert -->
	{#if error}
		<Alert variant="destructive">
			<AlertCircle class="h-4 w-4" />
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Overview Cards -->
	<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
		<!-- Total Requests -->
		<Card>
			<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
				<CardTitle class="text-sm font-medium">Total Requests</CardTitle>
				<Users class="h-4 w-4 text-muted-foreground" />
			</CardHeader>
			<CardContent>
				{#if isLoading}
					<Skeleton class="h-8 w-24" />
				{:else}
					<div class="text-2xl font-bold">{formatNumber(totalRequests)}</div>
					<p class="text-xs text-muted-foreground mt-1">
						From Telegram bot
					</p>
				{/if}
			</CardContent>
		</Card>

		<!-- Success Rate -->
		<Card>
			<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
				<CardTitle class="text-sm font-medium">Success Rate</CardTitle>
				<Activity class="h-4 w-4 text-muted-foreground" />
			</CardHeader>
			<CardContent>
				{#if isLoading}
					<Skeleton class="h-8 w-24" />
				{:else}
					<div class="text-2xl font-bold">{overallSuccessRate.toFixed(1)}%</div>
					<Progress value={overallSuccessRate} class="mt-2 h-1" />
				{/if}
			</CardContent>
		</Card>

		<!-- Total Revenue -->
		<Card>
			<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
				<CardTitle class="text-sm font-medium">Total Revenue</CardTitle>
				<TrendingUp class="h-4 w-4 text-green-600" />
			</CardHeader>
			<CardContent>
				{#if isLoading}
					<Skeleton class="h-8 w-24" />
				{:else}
					<div class="text-2xl font-bold text-green-600">
						{formatCurrency(totalRevenue)}
					</div>
					<p class="text-xs text-muted-foreground mt-1">
						Gross income
					</p>
				{/if}
			</CardContent>
		</Card>

		<!-- Net Profit -->
		<Card>
			<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
				<CardTitle class="text-sm font-medium">Net Profit</CardTitle>
				<DollarSign class="h-4 w-4 text-primary" />
			</CardHeader>
			<CardContent>
				{#if isLoading}
					<Skeleton class="h-8 w-24" />
				{:else}
					<div class="text-2xl font-bold text-primary">
						{formatCurrency(totalProfit)}
					</div>
					<p class="text-xs text-muted-foreground mt-1">
						After costs: {formatCurrency(totalCosts)}
					</p>
				{/if}
			</CardContent>
		</Card>
	</div>

	<!-- Detailed Stats -->
	<div class="grid gap-6 lg:grid-cols-2">
		<!-- Instant SSN Stats -->
		<Card>
			<CardHeader>
				<div class="flex items-center justify-between">
					<div>
						<CardTitle class="flex items-center gap-2">
							<Badge variant="default">⚡ Instant SSN</Badge>
						</CardTitle>
						<CardDescription class="mt-1">
							Automated searches from Telegram
						</CardDescription>
					</div>
				</div>
			</CardHeader>
			<CardContent>
				{#if isLoading}
					<div class="space-y-2">
						{#each Array(5) as _}
							<Skeleton class="h-12 w-full" />
						{/each}
					</div>
				{:else}
					<div class="space-y-4">
						<!-- Attempts breakdown -->
						<div class="space-y-2">
							<div class="flex items-center justify-between">
								<span class="text-sm font-medium">Total Attempts</span>
								<span class="text-sm font-bold">{formatNumber(instantStats.telegram_total_attempts)}</span>
							</div>
							<div class="flex items-center gap-2">
								<CheckCircle class="h-4 w-4 text-green-600" />
								<span class="text-sm">Successful</span>
								<span class="ml-auto text-sm font-semibold text-green-600">
									{formatNumber(instantStats.telegram_successful)} ({instantStats.telegram_success_rate.toFixed(1)}%)
								</span>
							</div>
							<div class="flex items-center gap-2">
								<XCircle class="h-4 w-4 text-red-600" />
								<span class="text-sm">Failed</span>
								<span class="ml-auto text-sm font-semibold text-red-600">
									{formatNumber(instantStats.telegram_failed)}
								</span>
							</div>
						</div>

						<div class="border-t pt-4">
							<!-- Financial stats -->
							<div class="space-y-2">
								<div class="flex items-center justify-between">
									<span class="text-sm">Revenue</span>
									<span class="text-sm font-semibold text-green-600">
										{formatCurrency(instantStats.telegram_revenue)}
									</span>
								</div>
								<div class="flex items-center justify-between">
									<span class="text-sm">API Costs</span>
									<span class="text-sm font-semibold text-orange-600">
										{formatCurrency(instantStats.telegram_api_cost)}
									</span>
								</div>
								<div class="flex items-center justify-between pt-2 border-t">
									<span class="text-sm font-medium">Net Profit</span>
									<span class="text-sm font-bold text-primary">
										{formatCurrency(instantStats.telegram_net_profit)}
									</span>
								</div>
							</div>
						</div>

						<!-- Average cost per search -->
						{#if instantStats.telegram_successful > 0}
							<div class="bg-muted/50 rounded-lg p-3">
								<div class="flex items-center justify-between">
									<span class="text-xs text-muted-foreground">Avg cost per success</span>
									<span class="text-xs font-medium">
										{formatCurrency(instantStats.telegram_api_cost / instantStats.telegram_successful)}
									</span>
								</div>
							</div>
						{/if}
					</div>
				{/if}
			</CardContent>
		</Card>

		<!-- Manual SSN Stats -->
		<Card>
			<CardHeader>
				<div class="flex items-center justify-between">
					<div>
						<CardTitle class="flex items-center gap-2">
							<Badge variant="secondary">👤 Manual SSN</Badge>
						</CardTitle>
						<CardDescription class="mt-1">
							Manual searches from Telegram
						</CardDescription>
					</div>
				</div>
			</CardHeader>
			<CardContent>
				{#if isLoading}
					<div class="space-y-2">
						{#each Array(5) as _}
							<Skeleton class="h-12 w-full" />
						{/each}
					</div>
				{:else}
					<div class="space-y-4">
						<!-- Requests breakdown -->
						<div class="space-y-2">
							<div class="flex items-center justify-between">
								<span class="text-sm font-medium">Total Requests</span>
								<span class="text-sm font-bold">{formatNumber(manualStats.telegram_total_attempts)}</span>
							</div>
							<div class="flex items-center gap-2">
								<CheckCircle class="h-4 w-4 text-green-600" />
								<span class="text-sm">Completed</span>
								<span class="ml-auto text-sm font-semibold text-green-600">
									{formatNumber(manualStats.telegram_successful)} ({manualStats.telegram_success_rate.toFixed(1)}%)
								</span>
							</div>
							<div class="flex items-center gap-2">
								<XCircle class="h-4 w-4 text-red-600" />
								<span class="text-sm">Rejected</span>
								<span class="ml-auto text-sm font-semibold text-red-600">
									{formatNumber(manualStats.telegram_failed)}
								</span>
							</div>
							{#if manualStats.telegram_pending > 0}
								<div class="flex items-center gap-2">
									<AlertCircle class="h-4 w-4 text-yellow-600" />
									<span class="text-sm">Pending</span>
									<span class="ml-auto text-sm font-semibold text-yellow-600">
										{formatNumber(manualStats.telegram_pending)}
									</span>
								</div>
							{/if}
							{#if manualStats.telegram_processing > 0}
								<div class="flex items-center gap-2">
									<Clock class="h-4 w-4 text-blue-600" />
									<span class="text-sm">Processing</span>
									<span class="ml-auto text-sm font-semibold text-blue-600">
										{formatNumber(manualStats.telegram_processing)}
									</span>
								</div>
							{/if}
						</div>

						<div class="border-t pt-4">
							<!-- Financial stats -->
							<div class="space-y-2">
								<div class="flex items-center justify-between">
									<span class="text-sm">Revenue</span>
									<span class="text-sm font-semibold text-green-600">
										{formatCurrency(manualStats.telegram_revenue)}
									</span>
								</div>
								<div class="flex items-center justify-between">
									<span class="text-sm">Processing Costs</span>
									<span class="text-sm font-semibold text-orange-600">
										{formatCurrency(manualStats.telegram_processing_cost)}
									</span>
								</div>
								<div class="flex items-center justify-between pt-2 border-t">
									<span class="text-sm font-medium">Net Profit</span>
									<span class="text-sm font-bold text-primary">
										{formatCurrency(manualStats.telegram_net_profit)}
									</span>
								</div>
							</div>
						</div>

						<!-- Average response time -->
						{#if manualStats.telegram_avg_response_time > 0}
							<div class="bg-muted/50 rounded-lg p-3">
								<div class="flex items-center justify-between">
									<span class="text-xs text-muted-foreground">Avg response time</span>
									<span class="text-xs font-medium">
										{formatMinutes(manualStats.telegram_avg_response_time)}
									</span>
								</div>
							</div>
						{/if}
					</div>
				{/if}
			</CardContent>
		</Card>
	</div>

	<!-- Summary -->
	{#if !isLoading && totalRequests > 0}
		<Card class="bg-muted/30">
			<CardHeader>
				<CardTitle class="text-lg">Summary for {getPeriodLabel(selectedPeriod)}</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
					<div>
						<p class="text-sm text-muted-foreground">Total Searches</p>
						<p class="text-2xl font-bold">{formatNumber(totalRequests)}</p>
					</div>
					<div>
						<p class="text-sm text-muted-foreground">Success Rate</p>
						<p class="text-2xl font-bold">{overallSuccessRate.toFixed(1)}%</p>
					</div>
					<div>
						<p class="text-sm text-muted-foreground">Total Spent</p>
						<p class="text-2xl font-bold text-orange-600">{formatCurrency(totalCosts)}</p>
					</div>
					<div>
						<p class="text-sm text-muted-foreground">Net Profit</p>
						<p class="text-2xl font-bold text-green-600">{formatCurrency(totalProfit)}</p>
					</div>
				</div>
			</CardContent>
		</Card>
	{/if}
</div>