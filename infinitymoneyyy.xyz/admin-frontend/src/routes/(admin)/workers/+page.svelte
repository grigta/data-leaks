<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Input } from '$lib/components/ui/input';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import {
		Dialog,
		DialogContent,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Plus from '@lucide/svelte/icons/plus';
	import Copy from '@lucide/svelte/icons/copy';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import Check from '@lucide/svelte/icons/check';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Settings from '@lucide/svelte/icons/settings';
	import Save from '@lucide/svelte/icons/save';
	import Bell from '@lucide/svelte/icons/bell';
	import DollarSign from '@lucide/svelte/icons/dollar-sign';
	import Receipt from '@lucide/svelte/icons/receipt';
	import Square from '@lucide/svelte/icons/square';
	import Clock from '@lucide/svelte/icons/clock';
	import History from '@lucide/svelte/icons/history';
	import {
		getWorkers,
		getDistributionConfig,
		updateDistributionConfig,
		generateWorkerCode,
		removeWorkerRole,
		getWorkerStats,
		getWorkerInvoices,
		getPendingInvoiceCount,
		markInvoicePaid,
		getWorkerInvoicesById,
		getWorkerShifts,
		forceStopWorkerShift,
		handleApiError,
		type WorkerResponse,
		type DistributionConfigResponse,
		type WorkerStatsItem,
		type WorkerInvoiceItem,
		type WorkerShiftResponse
	} from '$lib/api/client';
	import { wsManager, WORKER_INVOICE_CREATED, WORKER_SHIFT_UPDATED } from '$lib/websocket/manager';
	import { onlineWorkerCount } from '$lib/stores/workers';
	import { formatDateTime } from '$lib/utils';
	import { toast } from 'svelte-sonner';
	import { t } from '$lib/i18n';

	// State
	let workers = $state<WorkerResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let totalCount = $state(0);
	let onlineCount = $derived(workers.filter((w) => w.is_online).length);

	// Distribution config
	let distConfig = $state<DistributionConfigResponse | null>(null);
	let distMode = $state<'even' | 'percentage'>('even');
	let percentages = $state<Record<string, number>>({});
	let isSavingDist = $state(false);
	let percentageSum = $derived(Object.values(percentages).reduce((a, b) => a + (b || 0), 0));

	// Generate dialog
	let showGenerateDialog = $state(false);
	let isGenerating = $state(false);
	let generatedCode = $state('');
	let codeCopied = $state(false);

	// Remove dialog
	let showRemoveDialog = $state(false);
	let selectedWorker = $state<WorkerResponse | null>(null);
	let isRemoving = $state(false);

	// Worker stats
	let workerStats = $state<Record<string, WorkerStatsItem>>({});
	let pendingInvoiceCount = $state(0);

	// Invoice dialog (per worker)
	let showInvoiceDialog = $state(false);
	let selectedWorkerForInvoice = $state<WorkerResponse | null>(null);
	let workerInvoices = $state<WorkerInvoiceItem[]>([]);
	let isLoadingInvoices = $state(false);
	let isPayingInvoice = $state('');

	// All pending invoices dialog (bell)
	let showAllInvoicesDialog = $state(false);
	let allInvoices = $state<WorkerInvoiceItem[]>([]);
	let isLoadingAllInvoices = $state(false);

	// All invoices history dialog
	let showAllInvoicesHistoryDialog = $state(false);
	let allInvoicesHistory = $state<WorkerInvoiceItem[]>([]);
	let isLoadingAllInvoicesHistory = $state(false);
	let invoicesHistoryFilter = $state<string>('all');

	// Shift history dialog
	let showShiftHistoryDialog = $state(false);
	let selectedWorkerForShifts = $state<WorkerResponse | null>(null);
	let workerShifts = $state<WorkerShiftResponse[]>([]);
	let isLoadingShifts = $state(false);
	let isForceStoppingShift = $state('');

	function formatDuration(seconds: number): string {
		const h = Math.floor(seconds / 3600);
		const m = Math.floor((seconds % 3600) / 60);
		if (h > 0) return `${h}h ${m}m`;
		return `${m}m`;
	}

	async function openShiftHistory(worker: WorkerResponse) {
		selectedWorkerForShifts = worker;
		showShiftHistoryDialog = true;
		isLoadingShifts = true;
		try {
			const res = await getWorkerShifts(worker.id, { limit: 50 });
			workerShifts = res.shifts;
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
		isLoadingShifts = false;
	}

	async function handleForceStop(worker: WorkerResponse) {
		isForceStoppingShift = worker.id;
		try {
			await forceStopWorkerShift(worker.id);
			const idx = workers.findIndex(w => w.id === worker.id);
			if (idx !== -1) {
				workers[idx].worker_status = 'idle';
				workers[idx].current_shift_started_at = null;
			}
			toast.success(`Shift force-stopped for ${worker.username}`);
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isForceStoppingShift = '';
		}
	}

	// Auto-refresh interval
	let refreshInterval: ReturnType<typeof setInterval> | null = null;
	let unsubInvoice: (() => void) | null = null;
	let unsubShift: (() => void) | null = null;

	async function loadWorkers() {
		isLoading = true;
		error = '';
		try {
			const [workersData, configData, stats, pendingCount] = await Promise.all([
				getWorkers({ limit: 100 }),
				getDistributionConfig(),
				getWorkerStats(),
				getPendingInvoiceCount()
			]);
			workers = workersData.workers;
			totalCount = workersData.total_count;
			applyDistConfig(configData);

			const statsMap: Record<string, WorkerStatsItem> = {};
			for (const s of stats) {
				statsMap[s.worker_id] = s;
			}
			workerStats = statsMap;
			pendingInvoiceCount = pendingCount;
		} catch (err: any) {
			error = handleApiError(err);
		} finally {
			isLoading = false;
		}
	}

	function applyDistConfig(config: DistributionConfigResponse) {
		distConfig = config;
		distMode = config.distribution_mode as 'even' | 'percentage';
		const pcts: Record<string, number> = {};
		for (const w of config.workers) {
			pcts[w.worker_id] = w.load_percentage ?? 0;
		}
		percentages = pcts;
	}

	async function silentRefresh() {
		try {
			const [workersData, configData, stats, pendingCount] = await Promise.all([
				getWorkers({ limit: 100 }),
				getDistributionConfig(),
				getWorkerStats(),
				getPendingInvoiceCount()
			]);
			workers = workersData.workers;
			totalCount = workersData.total_count;

			const statsMap: Record<string, WorkerStatsItem> = {};
			for (const s of stats) {
				statsMap[s.worker_id] = s;
			}
			workerStats = statsMap;
			pendingInvoiceCount = pendingCount;

			// Only update online status from config, don't override user edits
			if (distConfig) {
				for (const w of configData.workers) {
					const existing = distConfig.workers.find((ew) => ew.worker_id === w.worker_id);
					if (existing) {
						existing.is_online = w.is_online;
					}
				}
			}
		} catch {
			// Silent fail
		}
	}

	async function handleGenerate() {
		isGenerating = true;
		try {
			const result = await generateWorkerCode();
			generatedCode = result.access_code;
			codeCopied = false;
			toast.success($t('workers.generate.generated'));
			await loadWorkers();
		} catch (err: any) {
			toast.error(handleApiError(err));
			showGenerateDialog = false;
		} finally {
			isGenerating = false;
		}
	}

	async function copyCode(code: string) {
		try {
			await navigator.clipboard.writeText(code);
			codeCopied = true;
			toast.success($t('workers.copied'));
			setTimeout(() => (codeCopied = false), 2000);
		} catch {
			toast.error($t('workers.copyFailed'));
		}
	}

	async function handleRemove() {
		if (!selectedWorker) return;
		isRemoving = true;
		try {
			await removeWorkerRole(selectedWorker.id);
			toast.success($t('workers.remove.removed', { values: { username: selectedWorker.username } }));
			showRemoveDialog = false;
			selectedWorker = null;
			await loadWorkers();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isRemoving = false;
		}
	}

	function handleDistributeEvenly() {
		if (!distConfig) return;
		const workerCount = distConfig.workers.length;
		if (workerCount === 0) return;
		const base = Math.floor(100 / workerCount);
		const remainder = 100 - base * workerCount;
		const pcts: Record<string, number> = {};
		distConfig.workers.forEach((w, i) => {
			pcts[w.worker_id] = base + (i < remainder ? 1 : 0);
		});
		percentages = pcts;
	}

	async function saveDistribution() {
		if (distMode === 'percentage' && percentageSum !== 100) {
			toast.error($t('workers.distribution.sumError', { values: { sum: percentageSum } }));
			return;
		}

		isSavingDist = true;
		try {
			const workerData =
				distMode === 'percentage' && distConfig
					? distConfig.workers.map((w) => ({
							worker_id: w.worker_id,
							load_percentage: percentages[w.worker_id] ?? 0
						}))
					: undefined;

			await updateDistributionConfig({
				distribution_mode: distMode,
				workers: workerData
			});
			toast.success($t('workers.distribution.saved'));
			// Reload to get fresh data
			const configData = await getDistributionConfig();
			applyDistConfig(configData);
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isSavingDist = false;
		}
	}

	async function openWorkerInvoices(worker: WorkerResponse) {
		selectedWorkerForInvoice = worker;
		showInvoiceDialog = true;
		isLoadingInvoices = true;
		try {
			const res = await getWorkerInvoicesById(worker.id);
			workerInvoices = res.invoices;
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
		isLoadingInvoices = false;
	}

	async function handlePayInvoice(invoiceId: string) {
		isPayingInvoice = invoiceId;
		try {
			await markInvoicePaid(invoiceId);
			toast.success($t('workers.invoices.markedPaid'));
			// Refresh invoices in dialog
			if (selectedWorkerForInvoice) {
				const res = await getWorkerInvoicesById(selectedWorkerForInvoice.id);
				workerInvoices = res.invoices;
			}
			// Refresh stats and pending count
			const [stats, pendingCount] = await Promise.all([
				getWorkerStats(),
				getPendingInvoiceCount()
			]);
			const statsMap: Record<string, WorkerStatsItem> = {};
			for (const s of stats) statsMap[s.worker_id] = s;
			workerStats = statsMap;
			pendingInvoiceCount = pendingCount;
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
		isPayingInvoice = '';
	}

	async function openAllInvoices() {
		showAllInvoicesDialog = true;
		isLoadingAllInvoices = true;
		try {
			const res = await getWorkerInvoices({ status_filter: 'pending', limit: 100 });
			allInvoices = res.invoices;
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
		isLoadingAllInvoices = false;
	}

	async function copyWallet(address: string) {
		try {
			await navigator.clipboard.writeText(address);
			toast.success($t('workers.copied'));
		} catch {
			toast.error($t('workers.copyFailed'));
		}
	}

	async function openAllInvoicesHistory() {
		showAllInvoicesHistoryDialog = true;
		invoicesHistoryFilter = 'all';
		await loadInvoicesHistory();
	}

	async function loadInvoicesHistory() {
		isLoadingAllInvoicesHistory = true;
		try {
			const params: Record<string, any> = { limit: 200 };
			if (invoicesHistoryFilter !== 'all') params.status_filter = invoicesHistoryFilter;
			const res = await getWorkerInvoices(params);
			allInvoicesHistory = res.invoices;
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
		isLoadingAllInvoicesHistory = false;
	}

	// Sync online count to global store for layout header
	$effect(() => {
		onlineWorkerCount.set(onlineCount);
	});

	onMount(() => {
		loadWorkers();
		refreshInterval = setInterval(silentRefresh, 10000);
		unsubInvoice = wsManager.on(WORKER_INVOICE_CREATED, () => {
			pendingInvoiceCount += 1;
			toast.info($t('workers.pendingRequests.newRequest'));
		});
		unsubShift = wsManager.on(WORKER_SHIFT_UPDATED, (data: any) => {
			const idx = workers.findIndex(w => w.id === data.worker_id);
			if (idx !== -1) {
				workers[idx].worker_status = data.worker_status ?? 'idle';
				workers[idx].current_shift_started_at = data.current_shift_started_at ?? null;
			}
		});
	});

	onDestroy(() => {
		if (refreshInterval) {
			clearInterval(refreshInterval);
		}
		unsubInvoice?.();
		unsubShift?.();
		onlineWorkerCount.set(null);
	});
</script>

<div class="space-y-6">
	<div class="flex items-center justify-end">
		<div class="flex items-center gap-2">
			<Button
				variant="outline"
				size="icon"
				onclick={openAllInvoices}
				title={$t('workers.pendingInvoices')}
				class="relative"
			>
				<Bell class="h-4 w-4" />
				{#if pendingInvoiceCount > 0}
					<span
						class="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] font-bold text-destructive-foreground"
					>
						{pendingInvoiceCount}
					</span>
				{/if}
			</Button>
			<Button variant="outline" size="icon" onclick={openAllInvoicesHistory} title="Invoices">
				<Receipt class="h-4 w-4" />
			</Button>
			<Button variant="outline" size="icon" onclick={silentRefresh} title={$t('common.refresh')}>
				<RefreshCw class="h-4 w-4" />
			</Button>
			<Button
				onclick={() => {
					generatedCode = '';
					codeCopied = false;
					showGenerateDialog = true;
				}}
			>
				<Plus class="mr-2 h-4 w-4" />
				{$t('workers.generateCode')}
			</Button>
		</div>
	</div>

	<!-- Error -->
	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Load Distribution Config -->
	{#if distConfig && distConfig.workers.length > 0}
		<Card>
			<CardHeader class="pb-3">
				<CardTitle class="flex items-center gap-2">
					<Settings class="h-5 w-5" />
					{$t('workers.distribution.title')}
				</CardTitle>
			</CardHeader>
			<CardContent>
				<!-- Mode selector -->
				<div class="mb-4 flex items-center gap-3">
					<span class="text-sm text-muted-foreground">{$t('workers.distribution.mode')}</span>
					<div class="flex rounded-md border">
						<button
							class="px-3 py-1.5 text-sm transition-colors rounded-l-md {distMode === 'even'
								? 'bg-primary text-primary-foreground'
								: 'hover:bg-muted'}"
							onclick={() => (distMode = 'even')}
						>
							{$t('workers.distribution.even')}
						</button>
						<button
							class="px-3 py-1.5 text-sm transition-colors rounded-r-md border-l {distMode ===
							'percentage'
								? 'bg-primary text-primary-foreground'
								: 'hover:bg-muted'}"
							onclick={() => {
								distMode = 'percentage';
								// Auto-fill if all zeros
								if (percentageSum === 0) handleDistributeEvenly();
							}}
						>
							{$t('workers.distribution.percentage')}
						</button>
					</div>
					{#if distMode === 'percentage'}
						<Button variant="outline" size="sm" onclick={handleDistributeEvenly}>
							{$t('workers.distribution.distributeEvenly')}
						</Button>
						<span
							class="text-sm {percentageSum === 100
								? 'text-green-600'
								: 'text-destructive font-semibold'}"
						>
							{$t('workers.distribution.total', { values: { sum: percentageSum } })}
						</span>
					{/if}
				</div>

				<!-- Worker percentages (only in percentage mode) -->
				{#if distMode === 'percentage'}
					<div class="grid gap-2 mb-4">
						{#each distConfig.workers as w}
							<div class="flex items-center gap-3">
								<div class="flex w-32 items-center gap-1.5 shrink-0">
									{#if w.is_online}
										<span class="h-2 w-2 rounded-full bg-green-500 shrink-0"></span>
									{:else}
										<span
											class="h-2 w-2 rounded-full bg-muted-foreground/40 shrink-0"
										></span>
									{/if}
									<span
										class="text-sm truncate"
										class:text-muted-foreground={!w.is_online}
									>
										{w.username}
									</span>
								</div>
								<div class="flex items-center gap-1">
									<Input
										type="number"
										min={0}
										max={100}
										value={percentages[w.worker_id] ?? 0}
										oninput={(e) => {
											const val = parseInt(
												(e.target as HTMLInputElement).value
											);
											percentages[w.worker_id] = isNaN(val) ? 0 : val;
											percentages = { ...percentages };
										}}
										class="w-20 h-8 text-center"
									/>
									<span class="text-sm text-muted-foreground">%</span>
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<p class="text-sm text-muted-foreground mb-4">
						{$t('workers.distribution.evenDescription')}
					</p>
				{/if}

				<!-- Save button -->
				<Button onclick={saveDistribution} disabled={isSavingDist} size="sm">
					{#if isSavingDist}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{:else}
						<Save class="mr-2 h-4 w-4" />
					{/if}
					{$t('common.save')}
				</Button>
			</CardContent>
		</Card>
	{/if}

	<!-- Workers Table -->
	<Card>
		<CardHeader>
			<CardTitle class="flex items-center justify-between">
				<span>{$t('workers.title')}</span>
				<span class="text-sm font-normal text-muted-foreground">{$t('workers.total', { values: { count: totalCount } })}</span>
			</CardTitle>
		</CardHeader>
		<CardContent>
			{#if isLoading}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
				</div>
			{:else if workers.length === 0}
				<p class="py-8 text-center text-muted-foreground">{$t('workers.noWorkers')}</p>
			{:else}
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead class="w-[80px]">{$t('workers.table.status')}</TableHead>
							<TableHead>{$t('workers.table.username')}</TableHead>
							<TableHead>{$t('workers.table.accessCode')}</TableHead>
							<TableHead class="text-center">{$t('workers.table.assigned')}</TableHead>
							<TableHead class="text-center">{$t('workers.table.completed')}</TableHead>
							<TableHead class="text-center">{$t('workers.table.avgTime')}</TableHead>
							<TableHead class="text-center">{$t('workers.table.earned')}</TableHead>
							<TableHead class="text-center">{$t('workers.table.debt')}</TableHead>
							<TableHead>Shift</TableHead>
							<TableHead>{$t('workers.table.created')}</TableHead>
							<TableHead>{$t('workers.table.actions')}</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each workers as worker}
							<TableRow>
								<TableCell>
									{#if worker.is_online}
										<Badge
											variant="outline"
											class="border-green-600 text-green-600"
										>
											<span
												class="mr-1.5 h-2 w-2 rounded-full bg-green-500"
											></span>
											{$t('common.online')}
										</Badge>
									{:else}
										<Badge
											variant="outline"
											class="border-muted-foreground text-muted-foreground"
										>
											<span
												class="mr-1.5 h-2 w-2 rounded-full bg-muted-foreground/50"
											></span>
											{$t('common.offline')}
										</Badge>
									{/if}
								</TableCell>
								<TableCell class="font-medium">{worker.username}</TableCell>
								<TableCell>
									<button
										class="inline-flex items-center gap-1.5 rounded bg-muted px-2 py-1 font-mono text-sm hover:bg-muted/80 transition-colors cursor-pointer"
										onclick={() => copyCode(worker.access_code)}
										title={$t('workers.clickToCopy')}
									>
										{worker.access_code}
										<Copy class="h-3 w-3 text-muted-foreground" />
									</button>
								</TableCell>
								<TableCell class="text-center tabular-nums">
									{workerStats[worker.id]?.total_assigned ?? 0}
								</TableCell>
								<TableCell class="text-center tabular-nums text-green-600">
									{workerStats[worker.id]?.total_completed ?? 0}
								</TableCell>
								<TableCell class="text-center text-muted-foreground tabular-nums">
									{workerStats[worker.id]?.avg_completion_time_minutes
										? `${workerStats[worker.id].avg_completion_time_minutes}m`
										: '—'}
								</TableCell>
								<TableCell class="text-center tabular-nums">
									${workerStats[worker.id]?.total_earned ?? '0.00'}
								</TableCell>
								<TableCell
									class="text-center tabular-nums font-medium {parseFloat(
										workerStats[worker.id]?.debt ?? '0'
									) > 0
										? 'text-orange-500'
										: ''}"
								>
									${workerStats[worker.id]?.debt ?? '0.00'}
								</TableCell>
								<TableCell>
									{#if worker.worker_status === 'active'}
										<Badge variant="outline" class="border-green-600 text-green-600">
											Active
										</Badge>
									{:else if worker.worker_status === 'paused'}
										<Badge variant="outline" class="border-orange-500 text-orange-500">
											Paused
										</Badge>
									{:else}
										<Badge variant="outline" class="border-muted-foreground text-muted-foreground">
											Idle
										</Badge>
									{/if}
								</TableCell>
								<TableCell class="text-muted-foreground">
									{formatDateTime(worker.created_at)}
								</TableCell>
								<TableCell>
									<div class="flex items-center">
										{#if worker.worker_status === 'active' || worker.worker_status === 'paused'}
											<Button
												variant="ghost"
												size="icon"
												onclick={() => handleForceStop(worker)}
												disabled={isForceStoppingShift === worker.id}
												title="Force stop shift"
											>
												{#if isForceStoppingShift === worker.id}
													<Loader2 class="h-4 w-4 animate-spin" />
												{:else}
													<Square class="h-4 w-4 text-destructive" />
												{/if}
											</Button>
										{/if}
										<Button
											variant="ghost"
											size="icon"
											onclick={() => openShiftHistory(worker)}
											title="Shift history"
										>
											<History class="h-4 w-4" />
										</Button>
										<Button
											variant="ghost"
											size="icon"
											onclick={() => openWorkerInvoices(worker)}
											title={$t('workers.invoices.title', { values: { username: '' } })}
										>
											<DollarSign class="h-4 w-4 text-green-600" />
										</Button>
										<Button
											variant="ghost"
											size="icon"
											onclick={() => {
												selectedWorker = worker;
												showRemoveDialog = true;
											}}
											title={$t('workers.remove.title')}
										>
											<Trash2 class="h-4 w-4 text-destructive" />
										</Button>
									</div>
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
			{/if}
		</CardContent>
	</Card>
</div>

<!-- Generate Dialog -->
<Dialog bind:open={showGenerateDialog}>
	<DialogContent class="sm:max-w-md">
		<DialogHeader>
			<DialogTitle>{$t('workers.generate.title')}</DialogTitle>
		</DialogHeader>

		{#if generatedCode}
			<div class="space-y-4">
				<p class="text-sm text-muted-foreground">
					{$t('workers.generate.successMessage')}
				</p>
				<div class="flex items-center gap-2">
					<code
						class="flex-1 rounded-md border bg-muted px-4 py-3 text-center font-mono text-lg tracking-wider"
					>
						{generatedCode}
					</code>
					<Button variant="outline" size="icon" onclick={() => copyCode(generatedCode)}>
						{#if codeCopied}
							<Check class="h-4 w-4 text-green-600" />
						{:else}
							<Copy class="h-4 w-4" />
						{/if}
					</Button>
				</div>
				<Button class="w-full" onclick={() => (showGenerateDialog = false)}>{$t('workers.generate.done')}</Button>
			</div>
		{:else}
			<div class="space-y-4">
				<p class="text-sm text-muted-foreground">
					{$t('workers.generate.confirmMessage')}
				</p>
				<div class="flex justify-end gap-2">
					<Button variant="outline" onclick={() => (showGenerateDialog = false)}>
						{$t('common.cancel')}
					</Button>
					<Button onclick={handleGenerate} disabled={isGenerating}>
						{#if isGenerating}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						{/if}
						{$t('workers.generate.generate')}
					</Button>
				</div>
			</div>
		{/if}
	</DialogContent>
</Dialog>

<!-- Remove Worker Dialog -->
<Dialog bind:open={showRemoveDialog}>
	<DialogContent class="sm:max-w-md">
		<DialogHeader>
			<DialogTitle>{$t('workers.remove.title')}</DialogTitle>
		</DialogHeader>
		<div class="space-y-4">
			<p class="text-sm text-muted-foreground">
				{@html $t('workers.remove.confirm', { values: { username: selectedWorker?.username } })}
			</p>
			<div class="flex justify-end gap-2">
				<Button variant="outline" onclick={() => (showRemoveDialog = false)}>{$t('common.cancel')}</Button>
				<Button variant="destructive" onclick={handleRemove} disabled={isRemoving}>
					{#if isRemoving}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					{/if}
					{$t('workers.remove.remove')}
				</Button>
			</div>
		</div>
	</DialogContent>
</Dialog>

<!-- Worker Invoice Dialog ($) -->
<Dialog bind:open={showInvoiceDialog}>
	<DialogContent class="sm:max-w-2xl">
		<DialogHeader>
			<DialogTitle>{$t('workers.invoices.title', { values: { username: selectedWorkerForInvoice?.username } })}</DialogTitle>
		</DialogHeader>

		{#if selectedWorkerForInvoice}
			{@const stats = workerStats[selectedWorkerForInvoice.id]}
			<div class="rounded-md bg-muted p-3 text-sm space-y-1">
				<div>
					<span class="text-muted-foreground">{$t('workers.invoices.wallet')}</span>
					<span class="font-mono">{stats?.wallet_address || $t('workers.invoices.notSet')}</span>
				</div>
				<div>
					<span class="text-muted-foreground">{$t('workers.invoices.network')}</span>
					{stats?.wallet_network?.toUpperCase() || '—'}
				</div>
				<div class="flex gap-4 mt-1">
					<span>
						<span class="text-muted-foreground">{$t('workers.invoices.earned')}</span>
						<span class="font-medium">${stats?.total_earned ?? '0.00'}</span>
					</span>
					<span>
						<span class="text-muted-foreground">{$t('workers.invoices.paid')}</span>
						<span class="font-medium">${stats?.total_paid ?? '0.00'}</span>
					</span>
					<span>
						<span class="text-muted-foreground">{$t('workers.invoices.debt')}</span>
						<span class="font-semibold text-orange-500">${stats?.debt ?? '0.00'}</span>
					</span>
				</div>
			</div>
		{/if}

		{#if isLoadingInvoices}
			<div class="flex justify-center py-4">
				<Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
			</div>
		{:else if workerInvoices.length === 0}
			<p class="text-center text-muted-foreground py-4">{$t('workers.invoices.noInvoices')}</p>
		{:else}
			<div class="max-h-80 overflow-y-auto space-y-2">
				{#each workerInvoices as inv}
					<div class="flex items-center justify-between rounded-md border p-3">
						<div>
							<div class="font-medium">${inv.amount}</div>
							<div class="text-xs text-muted-foreground">
								{formatDateTime(inv.created_at)}
							</div>
							<div class="flex items-center gap-1">
								<span class="text-xs font-mono text-muted-foreground truncate max-w-[260px]">
									{inv.wallet_address}
								</span>
								<button
									class="shrink-0 cursor-pointer text-muted-foreground hover:text-foreground transition-colors"
									onclick={() => copyWallet(inv.wallet_address)}
									title="Copy wallet"
								>
									<Copy class="h-3 w-3" />
								</button>
							</div>
							<div class="text-xs text-muted-foreground">
								{inv.wallet_network.toUpperCase()}
							</div>
						</div>
						<div>
							{#if inv.status === 'pending'}
								<Button
									size="sm"
									onclick={() => handlePayInvoice(inv.id)}
									disabled={isPayingInvoice === inv.id}
								>
									{isPayingInvoice === inv.id ? '...' : $t('workers.invoices.markPaid')}
								</Button>
							{:else}
								<Badge variant="outline" class="text-green-600 border-green-600">
									{$t('workers.invoices.paidStatus')}
								</Badge>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</DialogContent>
</Dialog>

<!-- All Pending Invoices Dialog (Bell) -->
<Dialog bind:open={showAllInvoicesDialog}>
	<DialogContent class="sm:max-w-2xl">
		<DialogHeader>
			<DialogTitle>{$t('workers.pendingRequests.title')}</DialogTitle>
		</DialogHeader>

		{#if isLoadingAllInvoices}
			<div class="flex justify-center py-4">
				<Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
			</div>
		{:else if allInvoices.length === 0}
			<p class="text-center text-muted-foreground py-4">{$t('workers.pendingRequests.noPending')}</p>
		{:else}
			<div class="max-h-96 overflow-y-auto space-y-2">
				{#each allInvoices as inv}
					<div class="flex items-center justify-between rounded-md border p-3">
						<div>
							<div class="flex items-center gap-2">
								<span class="font-medium">${inv.amount}</span>
								<Badge variant="secondary" class="text-xs">
									{inv.worker_username}
								</Badge>
							</div>
							<div class="text-xs text-muted-foreground">
								{formatDateTime(inv.created_at)}
							</div>
							<div class="flex items-center gap-1">
								<span class="text-xs font-mono text-muted-foreground truncate max-w-[300px]">
									{inv.wallet_address}
								</span>
								<button
									class="shrink-0 cursor-pointer text-muted-foreground hover:text-foreground transition-colors"
									onclick={() => copyWallet(inv.wallet_address)}
									title="Copy wallet"
								>
									<Copy class="h-3 w-3" />
								</button>
							</div>
							<div class="text-xs text-muted-foreground">
								{inv.wallet_network.toUpperCase()}
							</div>
						</div>
						<div>
							<Button
								size="sm"
								onclick={async () => {
									isPayingInvoice = inv.id;
									try {
										await markInvoicePaid(inv.id);
										toast.success($t('workers.invoices.markedPaid'));
										allInvoices = allInvoices.filter((i) => i.id !== inv.id);
										const [stats, pendingCount] = await Promise.all([
											getWorkerStats(),
											getPendingInvoiceCount()
										]);
										const statsMap: Record<string, WorkerStatsItem> = {};
										for (const s of stats) statsMap[s.worker_id] = s;
										workerStats = statsMap;
										pendingInvoiceCount = pendingCount;
									} catch (err) {
										toast.error(handleApiError(err));
									}
									isPayingInvoice = '';
								}}
								disabled={isPayingInvoice === inv.id}
							>
								{isPayingInvoice === inv.id ? '...' : $t('workers.invoices.markPaid')}
							</Button>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</DialogContent>
</Dialog>

<!-- All Invoices History Dialog -->
<Dialog bind:open={showAllInvoicesHistoryDialog}>
	<DialogContent class="sm:max-w-2xl max-h-[80vh] flex flex-col">
		<DialogHeader>
			<DialogTitle>Invoices</DialogTitle>
		</DialogHeader>

		<!-- Filter tabs -->
		<div class="flex gap-2">
			{#each [{ value: 'all', label: 'All' }, { value: 'paid', label: 'Paid' }, { value: 'pending', label: 'Pending' }] as filter}
				<Button
					variant={invoicesHistoryFilter === filter.value ? 'default' : 'outline'}
					size="sm"
					onclick={() => {
						invoicesHistoryFilter = filter.value;
						loadInvoicesHistory();
					}}
				>
					{filter.label}
				</Button>
			{/each}
		</div>

		{#if isLoadingAllInvoicesHistory}
			<div class="flex justify-center py-4">
				<Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
			</div>
		{:else if allInvoicesHistory.length === 0}
			<p class="text-center text-muted-foreground py-4">No invoices</p>
		{:else}
			<div class="flex-1 overflow-y-auto space-y-2 max-h-[500px]">
				{#each allInvoicesHistory as inv}
					<div class="flex items-center justify-between rounded-md border p-3">
						<div>
							<div class="flex items-center gap-2">
								<span class="font-medium">${inv.amount}</span>
								<Badge variant="secondary" class="text-xs">
									{inv.worker_username}
								</Badge>
								{#if inv.status === 'paid'}
									<Badge variant="outline" class="text-green-600 border-green-600 text-xs">
										Paid
									</Badge>
								{:else}
									<Badge variant="destructive" class="text-xs">
										Pending
									</Badge>
								{/if}
							</div>
							<div class="text-xs text-muted-foreground">
								{formatDateTime(inv.created_at)}
								{#if inv.paid_at}
									<span class="ml-2">→ paid {formatDateTime(inv.paid_at)}</span>
								{/if}
							</div>
							<div class="flex items-center gap-1">
								<span class="text-xs font-mono text-muted-foreground truncate max-w-[300px]">
									{inv.wallet_address}
								</span>
								<button
									class="shrink-0 cursor-pointer text-muted-foreground hover:text-foreground transition-colors"
									onclick={() => copyWallet(inv.wallet_address)}
									title="Copy wallet"
								>
									<Copy class="h-3 w-3" />
								</button>
							</div>
							<div class="text-xs text-muted-foreground">
								{inv.wallet_network.toUpperCase()}
							</div>
						</div>
						{#if inv.status === 'pending'}
							<div>
								<Button
									size="sm"
									onclick={async () => {
										isPayingInvoice = inv.id;
										try {
											await markInvoicePaid(inv.id);
											toast.success($t('workers.invoices.markedPaid'));
											await loadInvoicesHistory();
											const [stats, pendingCount] = await Promise.all([
												getWorkerStats(),
												getPendingInvoiceCount()
											]);
											const statsMap: Record<string, WorkerStatsItem> = {};
											for (const s of stats) statsMap[s.worker_id] = s;
											workerStats = statsMap;
											pendingInvoiceCount = pendingCount;
										} catch (err) {
											toast.error(handleApiError(err));
										}
										isPayingInvoice = '';
									}}
									disabled={isPayingInvoice === inv.id}
								>
									{isPayingInvoice === inv.id ? '...' : $t('workers.invoices.markPaid')}
								</Button>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</DialogContent>
</Dialog>

<!-- Shift History Dialog -->
<Dialog bind:open={showShiftHistoryDialog}>
	<DialogContent class="sm:max-w-2xl max-h-[80vh] flex flex-col">
		<DialogHeader>
			<DialogTitle>Shift History — {selectedWorkerForShifts?.username}</DialogTitle>
		</DialogHeader>

		{#if isLoadingShifts}
			<div class="flex justify-center py-4">
				<Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
			</div>
		{:else if workerShifts.length === 0}
			<p class="text-center text-muted-foreground py-4">No shifts recorded</p>
		{:else}
			<div class="flex-1 overflow-y-auto max-h-[500px]">
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>Started</TableHead>
							<TableHead>Ended</TableHead>
							<TableHead class="text-center">Duration</TableHead>
							<TableHead class="text-center">Paused</TableHead>
							<TableHead class="text-center">Completed</TableHead>
							<TableHead class="text-center">Rejected</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each workerShifts as shift}
							<TableRow>
								<TableCell class="text-sm">{formatDateTime(shift.started_at)}</TableCell>
								<TableCell class="text-sm">
									{#if shift.ended_at}
										{formatDateTime(shift.ended_at)}
									{:else}
										<Badge variant="outline" class="border-green-600 text-green-600">Active</Badge>
									{/if}
								</TableCell>
								<TableCell class="text-center text-sm tabular-nums">
									{formatDuration(shift.duration_seconds)}
								</TableCell>
								<TableCell class="text-center text-sm tabular-nums text-muted-foreground">
									{formatDuration(shift.pause_duration_seconds)}
								</TableCell>
								<TableCell class="text-center text-sm tabular-nums text-green-600">
									{shift.tickets_completed}
								</TableCell>
								<TableCell class="text-center text-sm tabular-nums text-destructive">
									{shift.tickets_rejected}
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
			</div>
		{/if}
	</DialogContent>
</Dialog>
