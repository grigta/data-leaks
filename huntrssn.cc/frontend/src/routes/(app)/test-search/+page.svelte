<script lang="ts">
	import {
		testSearch,
		getTestSearchHistory,
		handleApiError,
		type TestSearchResponse,
		type TestSearchHistoryItem
	} from '$lib/api/client';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import SearchIcon from '@lucide/svelte/icons/search';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import Clock from '@lucide/svelte/icons/clock';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import CheckCircle from '@lucide/svelte/icons/check-circle';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import FlaskConical from '@lucide/svelte/icons/flask-conical';
	import ArrowRight from '@lucide/svelte/icons/arrow-right';
	import { Badge } from '$lib/components/ui/badge';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	// Queue types
	type QueueStatus = 'processing' | 'found' | 'not_found' | 'error';

	interface QueueItem {
		id: string;
		fullName: string;
		address: string;
		status: QueueStatus;
		displayName: string;
		displayAddress: string;
		ssn: string;
		dob: string;
		errorMessage?: string;
	}

	// State
	let fullName = $state('');
	let address = $state('');
	let queue = $state<QueueItem[]>([]);
	let copiedCell = $state<string | null>(null);
	let showCopyTooltip = $state(false);

	// Stats (from server)
	let totalRequests = $state(0);
	let successfulRequests = $state(0);
	let totalFound = $state(0);

	// Session stats (current session increments on top of server stats)
	let sessionRequests = $state(0);
	let sessionSuccessful = $state(0);
	let sessionFound = $state(0);

	let displayTotalRequests = $derived(totalRequests + sessionRequests);
	let displaySuccessful = $derived(successfulRequests + sessionSuccessful);
	let displayTotalFound = $derived(totalFound + sessionFound);
	let successPercent = $derived(
		displayTotalRequests > 0 ? Math.round((displaySuccessful / displayTotalRequests) * 100) : 0
	);

	// History
	let history = $state<TestSearchHistoryItem[]>([]);
	let historyLoading = $state(true);
	const HISTORY_LIMIT = 25;

	let lastHistoryItem = $derived(history.length > 0 ? history[0] : null);
	let foundHistory = $derived(history.filter((h) => h.found));

	// Load history on mount
	onMount(async () => {
		try {
			const data = await getTestSearchHistory('test_search');
			history = data.history;
			totalRequests = data.total_requests;
			successfulRequests = data.successful_requests;
			totalFound = data.total_found;
		} catch (err) {
			console.error('Failed to load test search history:', err);
		} finally {
			historyLoading = false;
		}
	});

	// Helpers
	function formatSSN(ssn: string): string {
		const digits = ssn.replace(/\D/g, '');
		if (digits.length === 9) {
			return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
		}
		return ssn;
	}

	function formatDOBddmmyyyy(dob: string): string {
		if (!dob) return '';
		if (/^\d{8}$/.test(dob)) {
			return `${dob.substring(6, 8)}/${dob.substring(4, 6)}/${dob.substring(0, 4)}`;
		}
		if (/^\d{4}-\d{2}-\d{2}$/.test(dob)) {
			const [year, month, day] = dob.split('-');
			return `${day}/${month}/${year}`;
		}
		if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(dob)) {
			const [month, day, year] = dob.split('/');
			return `${day.padStart(2, '0')}/${month.padStart(2, '0')}/${year}`;
		}
		if (/^\d{1,2}-\d{1,2}-\d{4}$/.test(dob)) {
			const [month, day, year] = dob.split('-');
			return `${day.padStart(2, '0')}/${month.padStart(2, '0')}/${year}`;
		}
		return dob;
	}

	function parseName(input: string): { firstname: string; lastname: string } {
		const parts = input.trim().split(/\s+/);
		if (parts.length >= 3) {
			return { firstname: parts[0], lastname: parts[parts.length - 1] };
		} else if (parts.length === 2) {
			return { firstname: parts[0], lastname: parts[1] };
		}
		return { firstname: parts[0] || '', lastname: '' };
	}

	function updateQueueItem(id: string, updates: Partial<QueueItem>) {
		queue = queue.map((item) => (item.id === id ? { ...item, ...updates } : item));
	}

	async function executeSearch(item: QueueItem) {
		const { firstname, lastname } = parseName(item.fullName);

		try {
			const response = await testSearch({
				firstname,
				lastname,
				address: item.address,
				fullname: item.fullName
			});

			sessionRequests++;

			if (response.count > 0 && response.ssn_results.length > 0) {
				sessionSuccessful++;
				sessionFound += response.count;

				updateQueueItem(item.id, {
					status: 'found',
					displayName: response.input_fullname || item.fullName,
					displayAddress: response.input_address || item.address,
					ssn: formatSSN(response.ssn_results[0]),
					dob: response.searchbug_dob ? formatDOBddmmyyyy(response.searchbug_dob) : ''
				});
			} else {
				updateQueueItem(item.id, {
					status: 'not_found',
					displayName: response.input_fullname || item.fullName,
					displayAddress: response.input_address || item.address,
					dob: response.searchbug_dob ? formatDOBddmmyyyy(response.searchbug_dob) : ''
				});
			}

			// Reload history from server to pick up the new entry
			try {
				const data = await getTestSearchHistory('test_search');
				history = data.history;
				// Reset session counters since server has the latest
				totalRequests = data.total_requests;
				successfulRequests = data.successful_requests;
				totalFound = data.total_found;
				sessionRequests = 0;
				sessionSuccessful = 0;
				sessionFound = 0;
			} catch {
				// Silently ignore - session stats still work as fallback
			}
		} catch (err: unknown) {
			sessionRequests++;
			updateQueueItem(item.id, {
				status: 'error',
				errorMessage: handleApiError(err)
			});
		}
	}

	function handleSearch() {
		const { firstname, lastname } = parseName(fullName);
		if (!firstname || !lastname || !address.trim()) return;

		const item: QueueItem = {
			id: crypto.randomUUID(),
			fullName: fullName.trim(),
			address: address.trim(),
			status: 'processing',
			displayName: fullName.trim(),
			displayAddress: address.trim(),
			ssn: '',
			dob: ''
		};

		queue = [item, ...queue];
		fullName = '';
		address = '';

		executeSearch(item);
	}

	function handleClear() {
		fullName = '';
		address = '';
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			handleSearch();
		}
	}

	// Copy helpers
	async function copyCellValue(value: string, cellKey: string) {
		if (!value || value === '-' || value === '...') return;
		try {
			await navigator.clipboard.writeText(value);
			copiedCell = cellKey;
			setTimeout(() => {
				if (copiedCell === cellKey) copiedCell = null;
			}, 1000);
		} catch (error) {
			console.error('Failed to copy cell value:', error);
		}
	}

	async function handleCopyRow(item: QueueItem) {
		if (item.status === 'processing') return;
		const text = [item.displayName, item.displayAddress, item.ssn, item.dob]
			.filter(Boolean)
			.join('\t');
		try {
			await navigator.clipboard.writeText(text);
			copiedCell = `row-${item.id}`;
			showCopyTooltip = true;
			setTimeout(() => {
				showCopyTooltip = false;
			}, 1500);
			setTimeout(() => {
				if (copiedCell === `row-${item.id}`) copiedCell = null;
			}, 2000);
		} catch (error) {
			console.error('Failed to copy row:', error);
		}
	}

	async function handleRowRightClick(e: MouseEvent, item: QueueItem) {
		if (item.status === 'processing') return;
		e.preventDefault();
		const text = [item.displayName, item.displayAddress, item.ssn, item.dob]
			.filter(Boolean)
			.join('\t');
		try {
			await navigator.clipboard.writeText(text);
			showCopyTooltip = true;
			setTimeout(() => {
				showCopyTooltip = false;
			}, 1500);
		} catch (error) {
			console.error('Failed to copy row:', error);
		}
	}

	async function copyHistoryRow(item: TestSearchHistoryItem, rowKey: string) {
		const text = [item.input_fullname, item.input_address, formatSSN(item.ssn), item.dob ? formatDOBddmmyyyy(item.dob) : '']
			.filter(Boolean)
			.join('\t');
		try {
			await navigator.clipboard.writeText(text);
			copiedCell = rowKey;
			setTimeout(() => {
				if (copiedCell === rowKey) copiedCell = null;
			}, 1000);
		} catch (error) {
			console.error('Failed to copy history row:', error);
		}
	}
</script>

<div class="w-full space-y-6 py-2">
	<!-- Copy Tooltip -->
	{#if showCopyTooltip}
		<div
			class="fixed top-16 right-4 z-50 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-lg animate-tooltip-fade"
		>
			Row copied to clipboard
		</div>
	{/if}

	<!-- Header -->
	<div class="flex items-center justify-center gap-3">
		<div class="rounded-full bg-purple-100 p-2 dark:bg-purple-900/30">
			<FlaskConical class="h-5 w-5 text-purple-600 dark:text-purple-400" />
		</div>
		<h1 class="text-2xl font-semibold">Test Search</h1>
		{#if displayTotalRequests > 0}
			<Badge variant="secondary" class="text-sm px-3 py-1">
				{displaySuccessful}/{displayTotalRequests} ({successPercent}%)
			</Badge>
		{/if}
	</div>

	<!-- Search Form -->
	<Card class="mx-auto max-w-6xl">
		<CardContent class="pt-6">
			<div class="flex flex-col gap-4">
				<div class="flex flex-col gap-4 sm:flex-row sm:items-end">
					<div class="flex-1 space-y-2">
						<label for="fullName" class="text-sm font-medium text-foreground">Full Name</label>
						<Input
							id="fullName"
							type="text"
							placeholder="John Smith"
							bind:value={fullName}
							onkeydown={handleKeydown}
						/>
					</div>

					<div class="flex-1 space-y-2">
						<label for="address" class="text-sm font-medium text-foreground">Address</label>
						<Input
							id="address"
							type="text"
							placeholder="123 Main St"
							bind:value={address}
							onkeydown={handleKeydown}
						/>
					</div>

					<Button
						variant="outline"
						size="icon"
						onclick={handleClear}
						disabled={!fullName.trim() && !address.trim()}
						class="text-muted-foreground hover:text-destructive"
					>
						<Trash2 class="h-4 w-4" />
					</Button>
				</div>

				<div class="flex justify-center">
					<Button onclick={handleSearch} disabled={!fullName.trim() || !address.trim()}>
						<SearchIcon class="mr-2 h-4 w-4" />
						Test Search
					</Button>
				</div>
			</div>
		</CardContent>
	</Card>

	<!-- History Section -->
	{#if !historyLoading && foundHistory.length > 0}
		<Card class="mx-auto max-w-6xl">
			<CardContent class="p-4">
				<div class="flex items-center justify-between mb-3">
					<h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
						Last 25 searches
					</h2>
				</div>

				<Table>
					<TableHeader>
						<TableRow>
							<TableHead class="w-12 text-center"></TableHead>
							<TableHead class="text-center">Full Name</TableHead>
							<TableHead class="text-center">Full Address</TableHead>
							<TableHead class="text-center">SSN</TableHead>
							<TableHead class="text-center">DOB</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each foundHistory.slice(0, HISTORY_LIMIT) as item (item.id)}
							<TableRow>
								<!-- Copy Button -->
								<TableCell class="text-center">
									<Button
										variant="ghost"
										size="sm"
										onclick={() => copyHistoryRow(item, `hist-${item.id}`)}
										class="mx-auto h-8 w-8 p-0"
									>
										{#if copiedCell === `hist-${item.id}`}
											<Check class="h-4 w-4 text-primary" />
										{:else}
											<Copy class="h-4 w-4" />
										{/if}
									</Button>
								</TableCell>

								<!-- Full Name -->
								<TableCell
									class="cursor-pointer text-center text-sm transition-all duration-150"
									onclick={() => copyCellValue(item.input_fullname, `hist-${item.id}-name`)}
								>
									{copiedCell === `hist-${item.id}-name` ? 'Copied' : item.input_fullname}
								</TableCell>

								<!-- Full Address -->
								<TableCell
									class="cursor-pointer text-center text-sm transition-all duration-150"
									onclick={() => copyCellValue(item.input_address, `hist-${item.id}-addr`)}
								>
									{copiedCell === `hist-${item.id}-addr` ? 'Copied' : item.input_address}
								</TableCell>

								<!-- SSN -->
								<TableCell
									class="cursor-pointer text-center transition-all duration-150"
									onclick={() => copyCellValue(formatSSN(item.ssn), `hist-${item.id}-ssn`)}
								>
									{#if copiedCell === `hist-${item.id}-ssn`}
										<span class="text-sm">Copied</span>
									{:else}
										<code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs"
											>{formatSSN(item.ssn)}</code
										>
									{/if}
								</TableCell>

								<!-- DOB -->
								<TableCell
									class="cursor-pointer text-center text-sm transition-all duration-150"
									onclick={() => copyCellValue(item.dob ? formatDOBddmmyyyy(item.dob) : '', `hist-${item.id}-dob`)}
								>
									{#if copiedCell === `hist-${item.id}-dob`}
										Copied
									{:else if item.dob}
										{formatDOBddmmyyyy(item.dob)}
									{:else}
										-
									{/if}
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>

				{#if foundHistory.length > HISTORY_LIMIT}
					<div class="flex justify-center mt-4">
						<Button variant="outline" onclick={() => goto('/orders')}>
							Show All
							<ArrowRight class="ml-2 h-4 w-4" />
						</Button>
					</div>
				{/if}
			</CardContent>
		</Card>
	{/if}
</div>

<style>
	@keyframes tooltip-fade {
		0% {
			opacity: 0;
			transform: translateY(-8px);
		}
		15% {
			opacity: 1;
			transform: translateY(0);
		}
		85% {
			opacity: 1;
			transform: translateY(0);
		}
		100% {
			opacity: 0;
			transform: translateY(-8px);
		}
	}

	:global(.animate-tooltip-fade) {
		animation: tooltip-fade 1.5s ease-in-out;
	}
</style>
