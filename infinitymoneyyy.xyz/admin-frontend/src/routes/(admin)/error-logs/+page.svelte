<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
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
	import {
		Select,
		SelectContent,
		SelectItem,
		SelectTrigger,
		SelectValue
	} from '$lib/components/ui/select';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import AlertTriangle from '@lucide/svelte/icons/alert-triangle';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import {
		getErrorLogs,
		getErrorStats,
		cleanupOldErrors,
		handleApiError,
		type ErrorLogItem,
		type ErrorStatsResponse
	} from '$lib/api/client';
	import { formatDateTime } from '$lib/utils';
	import { toast } from 'svelte-sonner';
	import { t } from '$lib/i18n';

	// State
	let logs = $state<ErrorLogItem[]>([]);
	let stats = $state<ErrorStatsResponse | null>(null);
	let isLoading = $state(true);
	let error = $state('');
	let total = $state(0);
	let currentPage = $state(1);
	let pageSize = $state(50);
	let filterApi = $state<string>('');
	let selectedLog = $state<ErrorLogItem | null>(null);
	let showDetailDialog = $state(false);
	let isCleaning = $state(false);

	async function loadLogs() {
		isLoading = true;
		error = '';
		try {
			const params: any = { page: currentPage, page_size: pageSize };
			if (filterApi) params.api_name = filterApi;

			const [logsData, statsData] = await Promise.all([
				getErrorLogs(params),
				getErrorStats()
			]);

			logs = logsData.items;
			total = logsData.total;
			stats = statsData;
		} catch (err: any) {
			error = handleApiError(err);
		} finally {
			isLoading = false;
		}
	}

	async function handleCleanup() {
		isCleaning = true;
		try {
			const result = await cleanupOldErrors();
			toast.success($t('errors.cleanupSuccess', { values: { count: result.deleted } }));
			await loadLogs();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isCleaning = false;
		}
	}

	function openDetail(log: ErrorLogItem) {
		selectedLog = log;
		showDetailDialog = true;
	}

	function goPage(page: number) {
		currentPage = page;
		loadLogs();
	}

	function applyFilter(api: string) {
		filterApi = api;
		currentPage = 1;
		loadLogs();
	}

	$effect(() => {
		// unused — just to trigger when filterApi changes externally
		filterApi;
	});

	let totalPages = $derived(Math.ceil(total / pageSize) || 1);

	function getStatusBadgeVariant(code: number | null): 'destructive' | 'secondary' | 'outline' {
		if (!code) return 'secondary';
		if (code >= 500) return 'destructive';
		return 'outline';
	}

	function getApiBadgeVariant(api: string): 'default' | 'secondary' {
		return api === 'searchbug' ? 'default' : 'secondary';
	}

	onMount(() => {
		loadLogs();
	});
</script>

<div class="space-y-6">
	<!-- Stats cards -->
	{#if stats}
		<div class="grid grid-cols-1 gap-4 md:grid-cols-3">
			<Card>
				<CardHeader class="pb-2">
					<CardTitle class="text-sm font-medium text-muted-foreground">{$t('errors.stats.totalErrors')}</CardTitle>
				</CardHeader>
				<CardContent>
					<p class="text-2xl font-bold">{stats.total_errors}</p>
				</CardContent>
			</Card>
			<Card>
				<CardHeader class="pb-2">
					<CardTitle class="text-sm font-medium text-muted-foreground">{$t('errors.stats.today')}</CardTitle>
				</CardHeader>
				<CardContent>
					<p class="text-2xl font-bold text-destructive">{stats.errors_today}</p>
				</CardContent>
			</Card>
			<Card>
				<CardHeader class="pb-2">
					<CardTitle class="text-sm font-medium text-muted-foreground">{$t('errors.stats.byApi')}</CardTitle>
				</CardHeader>
				<CardContent>
					<div class="flex gap-3">
						{#each Object.entries(stats.errors_by_api) as [api, count]}
							<div class="flex items-center gap-1.5">
								<Badge variant={getApiBadgeVariant(api)}>{api}</Badge>
								<span class="text-sm font-semibold">{count}</span>
							</div>
						{/each}
						{#if Object.keys(stats.errors_by_api).length === 0}
							<span class="text-sm text-muted-foreground">{$t('common.noData')}</span>
						{/if}
					</div>
				</CardContent>
			</Card>
		</div>
	{/if}

	<!-- Filters & actions -->
	<Card>
		<CardContent class="pt-6">
			<div class="flex items-center justify-between gap-4">
				<div class="flex items-center gap-2">
					<Button
						variant={filterApi === '' ? 'default' : 'outline'}
						size="sm"
						onclick={() => applyFilter('')}
					>
						{$t('errors.filters.all')}
					</Button>
					<Button
						variant={filterApi === 'searchbug' ? 'default' : 'outline'}
						size="sm"
						onclick={() => applyFilter('searchbug')}
					>
						SearchBug
					</Button>
					<Button
						variant={filterApi === 'whitepages' ? 'default' : 'outline'}
						size="sm"
						onclick={() => applyFilter('whitepages')}
					>
						WhitePages
					</Button>
				</div>
				<div class="flex items-center gap-2">
					<Button variant="outline" size="sm" onclick={() => loadLogs()} disabled={isLoading}>
						<RefreshCw class="mr-1.5 h-3.5 w-3.5" />
						{$t('common.refresh')}
					</Button>
					<Button
						variant="destructive"
						size="sm"
						onclick={handleCleanup}
						disabled={isCleaning}
					>
						{#if isCleaning}
							<Loader2 class="mr-1.5 h-3.5 w-3.5 animate-spin" />
						{:else}
							<Trash2 class="mr-1.5 h-3.5 w-3.5" />
						{/if}
						{$t('errors.cleanup')}
					</Button>
				</div>
			</div>
		</CardContent>
	</Card>

	<!-- Error logs table -->
	<Card>
		<CardContent class="p-0">
			{#if isLoading}
				<div class="flex items-center justify-center py-12">
					<Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
				</div>
			{:else if error}
				<Alert variant="destructive" class="m-4">
					<AlertDescription>{error}</AlertDescription>
				</Alert>
			{:else if logs.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<AlertTriangle class="mb-3 h-10 w-10 text-muted-foreground/50" />
					<p class="text-muted-foreground">{$t('errors.noErrors')}</p>
				</div>
			{:else}
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead class="w-[140px]">{$t('errors.table.date')}</TableHead>
							<TableHead class="w-[100px]">{$t('errors.table.api')}</TableHead>
							<TableHead class="w-[120px]">{$t('errors.table.errorType')}</TableHead>
							<TableHead class="w-[80px]">{$t('errors.table.code')}</TableHead>
							<TableHead>{$t('errors.table.message')}</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each logs as log}
							<TableRow
								class="cursor-pointer hover:bg-muted/50"
								onclick={() => openDetail(log)}
							>
								<TableCell class="text-xs text-muted-foreground">
									{formatDateTime(log.created_at)}
								</TableCell>
								<TableCell>
									<Badge variant={getApiBadgeVariant(log.api_name)} class="text-xs">
										{log.api_name}
									</Badge>
								</TableCell>
								<TableCell class="text-xs font-mono">
									{log.error_type}
								</TableCell>
								<TableCell>
									{#if log.status_code}
										<Badge variant={getStatusBadgeVariant(log.status_code)} class="text-xs">
											{log.status_code}
										</Badge>
									{:else}
										<span class="text-xs text-muted-foreground">—</span>
									{/if}
								</TableCell>
								<TableCell class="max-w-[400px] truncate text-xs">
									{log.error_message}
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>

				<!-- Pagination -->
				{#if totalPages > 1}
					<div class="flex items-center justify-between border-t px-4 py-3">
						<span class="text-sm text-muted-foreground">
							{$t('common.pagination.records', { values: { total, current: currentPage, totalPages } })}
						</span>
						<div class="flex gap-1">
							<Button
								variant="outline"
								size="sm"
								disabled={currentPage <= 1}
								onclick={() => goPage(currentPage - 1)}
							>
								<ChevronLeft class="h-4 w-4" />
							</Button>
							<Button
								variant="outline"
								size="sm"
								disabled={currentPage >= totalPages}
								onclick={() => goPage(currentPage + 1)}
							>
								<ChevronRight class="h-4 w-4" />
							</Button>
						</div>
					</div>
				{/if}
			{/if}
		</CardContent>
	</Card>
</div>

<!-- Detail dialog -->
<Dialog bind:open={showDetailDialog}>
	<DialogContent class="max-w-2xl">
		<DialogHeader>
			<DialogTitle class="flex items-center gap-2">
				<AlertTriangle class="h-5 w-5 text-destructive" />
				{$t('errors.detail.title')}
			</DialogTitle>
		</DialogHeader>

		{#if selectedLog}
			<div class="space-y-4">
				<div class="grid grid-cols-2 gap-4">
					<div>
						<p class="text-xs text-muted-foreground mb-1">{$t('errors.table.api')}</p>
						<Badge variant={getApiBadgeVariant(selectedLog.api_name)}>
							{selectedLog.api_name}
						</Badge>
					</div>
					<div>
						<p class="text-xs text-muted-foreground mb-1">{$t('errors.detail.httpCode')}</p>
						{#if selectedLog.status_code}
							<Badge variant={getStatusBadgeVariant(selectedLog.status_code)}>
								{selectedLog.status_code}
							</Badge>
						{:else}
							<span class="text-sm text-muted-foreground">—</span>
						{/if}
					</div>
					<div>
						<p class="text-xs text-muted-foreground mb-1">{$t('errors.detail.method')}</p>
						<p class="text-sm font-mono">{selectedLog.method}</p>
					</div>
					<div>
						<p class="text-xs text-muted-foreground mb-1">{$t('errors.detail.errorType')}</p>
						<p class="text-sm font-mono">{selectedLog.error_type}</p>
					</div>
					<div class="col-span-2">
						<p class="text-xs text-muted-foreground mb-1">{$t('errors.detail.date')}</p>
						<p class="text-sm">{formatDateTime(selectedLog.created_at)}</p>
					</div>
				</div>

				<div>
					<p class="text-xs text-muted-foreground mb-1">{$t('errors.detail.errorMessage')}</p>
					<pre class="rounded-md bg-muted p-3 text-xs whitespace-pre-wrap break-all">{selectedLog.error_message}</pre>
				</div>

				{#if selectedLog.request_params}
					<div>
						<p class="text-xs text-muted-foreground mb-1">{$t('errors.detail.requestParams')}</p>
						<pre class="rounded-md bg-muted p-3 text-xs whitespace-pre-wrap break-all">{JSON.stringify(selectedLog.request_params, null, 2)}</pre>
					</div>
				{/if}
			</div>
		{/if}
	</DialogContent>
</Dialog>
