<script lang="ts">
	import { onMount } from 'svelte';
	import { goto, invalidateAll } from '$app/navigation';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import {
		getUserStats,
		getFinancialStats,
		getTransactionStats,
		getProductStats,
		getStatsTickets,
		getStatsWorkers,
		getInstantSSNStats,
		type UserStatsResponse,
		type FinancialStatsResponse,
		type TransactionStatsResponse,
		type ProductStatsResponse,
		type StatsResponse,
		type InstantSSNStatsResponse
	} from '$lib/api/client';
	import { formatCurrency, formatNumber, formatPercentage } from '$lib/utils';
	import { Users, DollarSign, ShoppingCart, TrendingUp, RefreshCw, Loader2, CheckCircle2 } from '@lucide/svelte';
	import { Chart, registerables } from 'chart.js';
	import StatsCardsGrid from '$lib/components/ui/stats-cards-grid.svelte';
	import PeriodSelector from '$lib/components/ui/period-selector.svelte';
	import { wsManager, TICKET_CREATED, TICKET_UPDATED, STATS_UPDATED } from '$lib/websocket/manager';

	// Register Chart.js components
	Chart.register(...registerables);

	// Props from load function
	interface Props {
		data: {
			period: string;
			stats: StatsResponse | null;
			error?: string;
		};
	}

	let { data }: Props = $props();

	// State
	let userStats = $state<UserStatsResponse | null>(null);
	let financialStats = $state<FinancialStatsResponse | null>(null);
	let transactionStats = $state<TransactionStatsResponse | null>(null);
	let productStats = $state<ProductStatsResponse | null>(null);
	let instantSSNStats = $state<InstantSSNStatsResponse | null>(null);
	let isLoading = $state(true);
	let error = $state('');
	let autoRefresh = $state(true);
	let refreshInterval = $state(10); // seconds

	// New stats state
	let selectedPeriod = $state(data.period);
	let stats = $state(data.stats);
	let isLoadingStats = $state(false);
	let lastUpdated = $state(new Date().toLocaleTimeString());

	// AbortControllers for canceling requests
	let abortController: AbortController | null = null;
	let statsAbortController: AbortController | null = null;

	// Sync stats when data changes (after navigation)
	$effect(() => {
		stats = data.stats;
		selectedPeriod = data.period;
		lastUpdated = new Date().toLocaleTimeString();
	});

	// Chart instances
	let userGrowthChart: Chart | null = null;
	let transactionChart: Chart | null = null;

	// Canvas refs
	let userGrowthCanvas = $state<HTMLCanvasElement | null>(null);
	let transactionCanvas = $state<HTMLCanvasElement | null>(null);

	// Load stats data
	async function loadStats() {
		// Cancel previous request if exists
		if (abortController) {
			abortController.abort();
		}

		abortController = new AbortController();
		const currentController = abortController;

		isLoading = true;
		error = '';

		try {
			// Load main stats (users, financial, transactions, products)
			const [users, financial, transactions, products] = await Promise.all([
				getUserStats(),
				getFinancialStats(),
				getTransactionStats(),
				getProductStats()
			]);

			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				userStats = users;
				financialStats = financial;
				transactionStats = transactions;
				productStats = products;

				// Create charts after data is loaded
				setTimeout(() => {
					if (!currentController.signal.aborted) {
						createUserGrowthChart();
						createTransactionChart();
					}
				}, 100);
			}
		} catch (err: any) {
			if (!currentController.signal.aborted) {
				error = err.message || 'Не удалось загрузить статистику';
			}
		} finally {
			if (!currentController.signal.aborted) {
				isLoading = false;
			}
		}

		// Load Instant SSN stats separately (don't block main dashboard)
		try {
			const instantSSN = await getInstantSSNStats();
			if (!currentController.signal.aborted) {
				instantSSNStats = instantSSN;
			}
		} catch (err: any) {
			// Silently fail - don't block main dashboard
			if (!currentController.signal.aborted) {
				console.error('Failed to load Instant SSN stats:', err);
				instantSSNStats = null;
			}
		}
	}

	// Load ticket/worker stats
	async function loadTicketWorkerStats() {
		// Cancel previous stats request if exists
		if (statsAbortController) {
			statsAbortController.abort();
		}

		statsAbortController = new AbortController();
		const currentController = statsAbortController;

		isLoadingStats = true;

		try {
			const [tickets, workers] = await Promise.all([
				getStatsTickets({ period: selectedPeriod }),
				getStatsWorkers({ period: selectedPeriod })
			]);

			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				stats = { tickets, workers };
				lastUpdated = new Date().toLocaleTimeString();
			}
		} catch (err: any) {
			if (!currentController.signal.aborted) {
				console.error('Failed to load ticket/worker stats:', err);
				stats = null;
			}
		} finally {
			if (!currentController.signal.aborted) {
				isLoadingStats = false;
			}
		}
	}

	// Handle period change
	async function handlePeriodChange(period: string) {
		selectedPeriod = period;
		await goto(`/dashboard?period=${period}`, { keepFocus: true, invalidateAll: true });
	}

	// Create user growth chart
	function createUserGrowthChart() {
		if (!userStats || !userGrowthCanvas) return;

		// Destroy existing chart
		if (userGrowthChart) {
			userGrowthChart.destroy();
		}

		const ctx = userGrowthCanvas.getContext('2d');
		if (!ctx) return;

		userGrowthChart = new Chart(ctx, {
			type: 'line',
			data: {
				labels: ['Last 24h', 'Last 30 days', 'All Time'],
				datasets: [
					{
						label: 'New Users',
						data: [
							userStats.new_users_1_day,
							userStats.new_users_30_days,
							userStats.total_users
						],
						borderColor: 'rgb(59, 130, 246)',
						backgroundColor: 'rgba(59, 130, 246, 0.1)',
						tension: 0.4,
						fill: true
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: {
						display: false
					},
					title: {
						display: false
					}
				},
				scales: {
					y: {
						beginAtZero: true,
						ticks: {
							precision: 0
						}
					}
				}
			}
		});
	}

	// Create transaction status chart
	function createTransactionChart() {
		if (!transactionStats || !transactionCanvas) return;

		// Destroy existing chart
		if (transactionChart) {
			transactionChart.destroy();
		}

		const ctx = transactionCanvas.getContext('2d');
		if (!ctx) return;

		transactionChart = new Chart(ctx, {
			type: 'doughnut',
			data: {
				labels: ['Ожидающие', 'Оплаченные', 'Истёкшие', 'Неудачные'],
				datasets: [
					{
						data: [
							transactionStats.pending,
							transactionStats.paid,
							transactionStats.expired,
							transactionStats.failed
						],
						backgroundColor: [
							'rgba(234, 179, 8, 0.8)', // yellow
							'rgba(34, 197, 94, 0.8)', // green
							'rgba(156, 163, 175, 0.8)', // gray
							'rgba(239, 68, 68, 0.8)' // red
						],
						borderColor: [
							'rgb(234, 179, 8)',
							'rgb(34, 197, 94)',
							'rgb(156, 163, 175)',
							'rgb(239, 68, 68)'
						],
						borderWidth: 2
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: {
						position: 'bottom'
					},
					title: {
						display: false
					}
				}
			}
		});
	}

	// Cleanup charts on unmount
	onMount(() => {
		loadStats();

		// Setup auto-refresh interval
		let intervalId: NodeJS.Timeout | null = null;

		function setupInterval() {
			if (intervalId) clearInterval(intervalId);

			if (autoRefresh) {
				intervalId = setInterval(() => {
					loadStats();
				}, refreshInterval * 1000);
			}
		}

		setupInterval();

		// Re-setup interval when settings change
		$effect(() => {
			if (autoRefresh || refreshInterval) {
				setupInterval();
			}
		});

		// Subscribe to WebSocket events for real-time stats updates
		const unsubscribeStatsUpdated = wsManager.on(STATS_UPDATED, (eventData: any) => {
			// Reload stats if no period filter or if event matches current period
			if (!eventData.period || eventData.period === selectedPeriod) {
				loadTicketWorkerStats();
			}
		});

		// Also refresh stats when tickets are created/updated
		const unsubscribeTicketCreated = wsManager.on(TICKET_CREATED, () => {
			loadTicketWorkerStats();
		});

		const unsubscribeTicketUpdated = wsManager.on(TICKET_UPDATED, () => {
			loadTicketWorkerStats();
		});

		return () => {
			// Cancel any pending requests
			if (abortController) abortController.abort();
			if (statsAbortController) statsAbortController.abort();

			// Destroy charts
			if (userGrowthChart) userGrowthChart.destroy();
			if (transactionChart) transactionChart.destroy();

			// Clear intervals
			if (intervalId) clearInterval(intervalId);

			// Unsubscribe from WebSocket events
			unsubscribeStatsUpdated();
			unsubscribeTicketCreated();
			unsubscribeTicketUpdated();
		};
	});
</script>

<div class="space-y-6">
	<!-- Header with refresh button -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">Обзор аналитики</h2>
			<p class="text-muted-foreground">Статистика и метрики платформы</p>
		</div>
		<div class="flex items-center gap-4">
			<!-- Auto-refresh toggle -->
			<div class="flex items-center gap-2">
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={autoRefresh} class="h-4 w-4" />
					<span class="text-muted-foreground">
						Автообновление ({refreshInterval}с)
					</span>
				</label>
			</div>
			<!-- Manual refresh button -->
			<Button variant="outline" onclick={loadStats} disabled={isLoading}>
				{#if isLoading}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					Загрузка...
				{:else}
					<RefreshCw class="mr-2 h-4 w-4" />
					Обновить
				{/if}
			</Button>
		</div>
	</div>

	<!-- Error alert -->
	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Metrics grid -->
	{#if isLoading && !userStats}
		<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
			{#each Array(4) as _}
				<Card>
					<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
						<div class="h-4 w-24 animate-pulse rounded bg-muted"></div>
						<div class="h-4 w-4 animate-pulse rounded bg-muted"></div>
					</CardHeader>
					<CardContent>
						<div class="h-8 w-32 animate-pulse rounded bg-muted"></div>
						<div class="mt-2 h-3 w-20 animate-pulse rounded bg-muted"></div>
					</CardContent>
				</Card>
			{/each}
		</div>
	{:else if userStats && financialStats && transactionStats && productStats}
		<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
			<!-- Total Users -->
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Всего пользователей</CardTitle>
					<Users class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{formatNumber(userStats.total_users)}</div>
					<p class="text-xs text-muted-foreground">
						+{formatNumber(userStats.new_users_1_day)} сегодня
					</p>
				</CardContent>
			</Card>

			<!-- Total Deposited -->
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Всего пополнено</CardTitle>
					<DollarSign class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{formatCurrency(financialStats.total_deposited)}</div>
					<p class="text-xs text-muted-foreground">Доход платформы</p>
				</CardContent>
			</Card>

			<!-- Total Spent -->
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Всего потрачено</CardTitle>
					<ShoppingCart class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{formatCurrency(financialStats.total_spent)}</div>
					<p class="text-xs text-muted-foreground">
						{financialStats.usage_percentage.toFixed(2)}% использование
					</p>
				</CardContent>
			</Card>

			<!-- Total Orders -->
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Всего заказов</CardTitle>
					<TrendingUp class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{formatNumber(productStats.total_orders)}</div>
					<p class="text-xs text-muted-foreground">Все покупки</p>
				</CardContent>
			</Card>
		</div>

		<!-- Charts grid -->
		<div class="grid gap-4 md:grid-cols-2">
			<!-- User Growth Chart -->
			<Card>
				<CardHeader>
					<CardTitle>Рост пользователей</CardTitle>
				</CardHeader>
				<CardContent>
					<div class="h-80">
						<canvas bind:this={userGrowthCanvas}></canvas>
					</div>
				</CardContent>
			</Card>

			<!-- Transaction Status Chart -->
			<Card>
				<CardHeader>
					<CardTitle>Статус транзакций</CardTitle>
				</CardHeader>
				<CardContent>
					<div class="h-80">
						<canvas bind:this={transactionCanvas}></canvas>
					</div>
				</CardContent>
			</Card>
		</div>

		<!-- Additional stats -->
		<div class="grid gap-4 md:grid-cols-3">
			<!-- Financial Usage -->
			<Card>
				<CardHeader>
					<CardTitle class="text-base">Финансовое использование</CardTitle>
				</CardHeader>
				<CardContent>
					<div class="space-y-2">
						<div class="flex justify-between text-sm">
							<span class="text-muted-foreground">Сумма использования:</span>
							<span class="font-medium">{formatCurrency(financialStats.usage_amount)}</span>
						</div>
						<div class="flex justify-between text-sm">
							<span class="text-muted-foreground">Процент использования:</span>
							<span class="font-medium">{financialStats.usage_percentage.toFixed(2)}%</span>
						</div>
						<div class="h-2 w-full rounded-full bg-muted">
							<div
								class="h-full rounded-full bg-primary transition-all"
								style="width: {Math.min(financialStats.usage_percentage, 100)}%"
							></div>
						</div>
					</div>
				</CardContent>
			</Card>

			<!-- Instant SSN Success Rate -->
			{#if instantSSNStats}
				<Card>
					<CardHeader>
						<CardTitle class="text-base flex items-center gap-2">
							<CheckCircle2 class="h-4 w-4 text-green-600" />
							% успешности пробивов
						</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="space-y-2">
							<div class="text-3xl font-bold text-green-600">
								{instantSSNStats.success_rate.toFixed(2)}%
							</div>
							<div class="flex justify-between text-sm">
								<span class="text-muted-foreground">Всего попыток:</span>
								<span class="font-medium">{formatNumber(instantSSNStats.total_attempts)}</span>
							</div>
							<div class="flex justify-between text-sm">
								<span class="text-muted-foreground">Успешных:</span>
								<span class="font-medium">{formatNumber(instantSSNStats.successful_searches)}</span>
							</div>
						</div>
					</CardContent>
				</Card>
			{/if}

			<!-- Transaction Summary -->
			<Card>
				<CardHeader>
					<CardTitle class="text-base">Сводка транзакций</CardTitle>
				</CardHeader>
				<CardContent>
					<div class="space-y-2">
						<div class="flex justify-between text-sm">
							<span class="text-muted-foreground">Всего:</span>
							<span class="font-medium"
								>{formatNumber(transactionStats.total_transactions)}</span
							>
						</div>
						<div class="flex justify-between text-sm">
							<span class="text-yellow-600">Ожидающие:</span>
							<span class="font-medium">{formatNumber(transactionStats.pending)}</span>
						</div>
						<div class="flex justify-between text-sm">
							<span class="text-green-600">Оплаченные:</span>
							<span class="font-medium">{formatNumber(transactionStats.paid)}</span>
						</div>
					</div>
				</CardContent>
			</Card>
		</div>
	{/if}
</div>
