<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import {
		getManualSSNStats,
		type ManualSSNStatsResponse
	} from '$lib/api/client';
	import { RefreshCw, Loader2, TrendingUp, TrendingDown, DollarSign, Search, CheckCircle2, XCircle, Clock, AlertCircle, MessageSquare } from '@lucide/svelte';
	import { formatNumber } from '$lib/utils';

	// State
	let stats = $state<ManualSSNStatsResponse | null>(null);
	let isLoading = $state(true);
	let error = $state('');
	let selectedPeriod = $state('all');
	let autoRefresh = $state(false);
	let refreshInterval = $state(30); // seconds

	// Period options
	const periods = [
		{ value: 'all', label: 'Всё время' },
		{ value: '1d', label: 'Сегодня' },
		{ value: 'yesterday', label: 'Вчера' },
		{ value: '7d', label: 'Последние 7 дней' },
		{ value: '30d', label: 'Последние 30 дней' }
	];

	// Load stats
	async function loadStats() {
		isLoading = true;
		error = '';

		try {
			const data = await getManualSSNStats({ period: selectedPeriod });
			stats = data;
		} catch (err: any) {
			error = err.response?.data?.detail || 'Failed to load statistics';
			console.error('Failed to load Manual SSN stats:', err);
		} finally {
			isLoading = false;
		}
	}

	// Handle period change
	function handlePeriodChange(period: string) {
		selectedPeriod = period;
		loadStats();
	}

	// Setup auto-refresh
	onMount(() => {
		loadStats();

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

		return () => {
			if (intervalId) clearInterval(intervalId);
		};
	});
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">Статистика Manual SSN</h2>
			<p class="text-muted-foreground">Аналитика ручного пробива и финансовые метрики</p>
		</div>
		<div class="flex items-center gap-4">
			<!-- Period selector -->
			<select
				bind:value={selectedPeriod}
				onchange={() => handlePeriodChange(selectedPeriod)}
				class="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
			>
				{#each periods as period}
					<option value={period.value}>{period.label}</option>
				{/each}
			</select>

			<!-- Auto-refresh toggle -->
			<div class="flex items-center gap-2">
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={autoRefresh} class="h-4 w-4" />
					<span class="text-muted-foreground">Авто-обновление ({refreshInterval}с)</span>
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

	<!-- Stats cards -->
	{#if isLoading && !stats}
		<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
			{#each Array(9) as _}
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
	{:else if stats}
		<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
			<!-- Total Attempts -->
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Всего попыток</CardTitle>
					<Search class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{formatNumber(stats.total_attempts)}</div>
					<p class="text-xs text-muted-foreground">Все заявки на пробив</p>
				</CardContent>
			</Card>

			<!-- Successful Searches -->
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Успешные поиски</CardTitle>
					<CheckCircle2 class="h-4 w-4 text-green-600" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold text-green-600">
						{formatNumber(stats.successful_searches)}
					</div>
					<p class="text-xs text-muted-foreground">
						{stats.success_rate.toFixed(2)}% успешности
					</p>
				</CardContent>
			</Card>

			<!-- Failed Searches -->
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Неудачные поиски</CardTitle>
					<XCircle class="h-4 w-4 text-red-600" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold text-red-600">{formatNumber(stats.failed_searches)}</div>
					<p class="text-xs text-muted-foreground">
						{stats.failure_rate.toFixed(2)}% неудач
					</p>
				</CardContent>
			</Card>

			<!-- Total Revenue -->
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Общая выручка</CardTitle>
					<DollarSign class="h-4 w-4 text-green-600" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold text-green-600">
						${Number(stats.total_revenue).toFixed(2)}
					</div>
					<p class="text-xs text-muted-foreground">От успешных поисков</p>
				</CardContent>
			</Card>

			<!-- Processing Costs -->
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Затраты на обработку</CardTitle>
					<TrendingDown class="h-4 w-4 text-red-600" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold text-red-600">${Number(stats.processing_cost).toFixed(2)}</div>
					<p class="text-xs text-muted-foreground">Ручная работа</p>
				</CardContent>
			</Card>

			<!-- Net Profit -->
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Чистая прибыль</CardTitle>
					<TrendingUp class="h-4 w-4 text-green-600" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold text-green-600">${Number(stats.net_profit).toFixed(2)}</div>
					<p class="text-xs text-muted-foreground">
						${Number(stats.profit_per_search).toFixed(2)} за успех
					</p>
				</CardContent>
			</Card>

			<!-- Average Response Time -->
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Среднее время ответа</CardTitle>
					<Clock class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">
						{#if stats.avg_response_time !== null}
							{stats.avg_response_time.toFixed(1)} мин
						{:else}
							N/A
						{/if}
					</div>
					<p class="text-xs text-muted-foreground">Для завершенных тикетов</p>
				</CardContent>
			</Card>
		</div>

		<!-- Telegram Statistics Section -->
		{#if stats.telegram_total_attempts > 0}
			<div class="mt-6">
				<h3 class="text-lg font-semibold mb-4">Статистика Telegram бота</h3>
			</div>

			<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
				<!-- Telegram Total Attempts -->
				<Card>
					<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle class="text-sm font-medium">Всего через Telegram</CardTitle>
						<MessageSquare class="h-4 w-4 text-muted-foreground" />
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold">{formatNumber(stats.telegram_total_attempts)}</div>
						<p class="text-xs text-muted-foreground">Все тикеты через бота</p>
					</CardContent>
				</Card>

				<!-- Telegram Successful -->
				<Card>
					<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle class="text-sm font-medium">Успешные через Telegram</CardTitle>
						<CheckCircle2 class="h-4 w-4 text-green-600" />
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold text-green-600">
							{formatNumber(stats.telegram_successful)}
						</div>
						<p class="text-xs text-muted-foreground">
							{stats.telegram_success_rate.toFixed(2)}% успешности
						</p>
					</CardContent>
				</Card>

				<!-- Telegram Failed -->
				<Card>
					<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
						<CardTitle class="text-sm font-medium">Неудачные через Telegram</CardTitle>
						<XCircle class="h-4 w-4 text-red-600" />
					</CardHeader>
					<CardContent>
						<div class="text-2xl font-bold text-red-600">{formatNumber(stats.telegram_failed)}</div>
						<p class="text-xs text-muted-foreground">
							{(100 - stats.telegram_success_rate).toFixed(2)}% неудач
						</p>
					</CardContent>
				</Card>
			</div>
		{/if}

		<!-- Additional Info -->
		<Card>
			<CardHeader>
				<CardTitle>Финансовая детализация</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="space-y-4">
					<div class="flex justify-between items-center">
						<span class="text-sm text-muted-foreground">Плата с пользователя за успех:</span>
						<span class="font-medium">$3.00</span>
					</div>
					<div class="flex justify-between items-center">
						<span class="text-sm text-muted-foreground">Затраты на обработку:</span>
						<span class="font-medium">$0.00 (ручная работа)</span>
					</div>
					<div class="flex justify-between items-center">
						<span class="text-sm text-muted-foreground">Прибыль за успех:</span>
						<span class="font-medium text-green-600">$3.00</span>
					</div>
					{#if stats.avg_response_time !== null}
						<div class="pt-4 border-t">
							<div class="flex justify-between items-center">
								<span class="text-sm font-semibold">Среднее время обработки:</span>
								<span class="font-bold text-blue-600">
									{stats.avg_response_time.toFixed(1)} минут
								</span>
							</div>
						</div>
					{/if}
				</div>
			</CardContent>
		</Card>
	{/if}
</div>
