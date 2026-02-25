<script lang="ts">
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
	import ArrowRight from '@lucide/svelte/icons/arrow-right';
	import { unifiedSearch, getTestSearchHistory, handleApiError, type TestSearchHistoryItem } from '$lib/api/client';
	import { user, setUser } from '$lib/stores/auth';
	import { goto } from '$app/navigation';
	import { onMount, onDestroy } from 'svelte';

	// State
	let fullName = $state('');
	let address = $state('');
	let copiedCell = $state<string | null>(null);
	let showCopyTooltip = $state(false);
	let searchLoading = $state(false);
	let errorMessage = $state('');

	// History
	let history = $state<TestSearchHistoryItem[]>([]);
	let historyLoading = $state(true);
	const HISTORY_LIMIT = 25;

	// Polling
	let pollInterval: ReturnType<typeof setInterval> | null = null;

	let hasProcessing = $derived(history.some((h) => h.status === 'processing'));

	// Load history on mount
	onMount(async () => {
		await loadHistory();
		historyLoading = false;
	});

	onDestroy(() => {
		stopPolling();
	});

	async function loadHistory() {
		try {
			const data = await getTestSearchHistory();
			history = data.history;
		} catch (err) {
			console.error('Failed to load search history:', err);
		}
	}

	function startPolling() {
		if (pollInterval) return;
		pollInterval = setInterval(async () => {
			await loadHistory();
			// Stop polling when no more processing items
			if (!history.some((h) => h.status === 'processing')) {
				stopPolling();
			}
		}, 3000);
	}

	function stopPolling() {
		if (pollInterval) {
			clearInterval(pollInterval);
			pollInterval = null;
		}
	}

	// Start/stop polling based on processing items
	$effect(() => {
		if (hasProcessing) {
			startPolling();
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

	async function handleSearch() {
		if (!fullName.trim() || !address.trim()) return;

		searchLoading = true;
		errorMessage = '';

		try {
			const response = await unifiedSearch({
				fullname: fullName.trim(),
				address: address.trim()
			});

			// Update balance in header
			if (response.new_balance != null && $user) {
				setUser({ ...$user, balance: response.new_balance });
			}

			// Clear form for next search
			fullName = '';
			address = '';

			// Reload history to see the new "processing" entry
			await loadHistory();

			// Start polling for status updates
			startPolling();
		} catch (err: unknown) {
			errorMessage = handleApiError(err);
		} finally {
			searchLoading = false;
		}
	}

	function handleClear() {
		fullName = '';
		address = '';
		errorMessage = '';
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

	async function copyHistoryRow(item: TestSearchHistoryItem, rowKey: string) {
		const text = [item.input_fullname, item.input_address, item.ssn ? formatSSN(item.ssn) : '', item.dob ? formatDOBddmmyyyy(item.dob) : '']
			.filter(Boolean)
			.join('\t');
		try {
			await navigator.clipboard.writeText(text);
			copiedCell = rowKey;
			showCopyTooltip = true;
			setTimeout(() => {
				showCopyTooltip = false;
			}, 1500);
			setTimeout(() => {
				if (copiedCell === rowKey) copiedCell = null;
			}, 1000);
		} catch (error) {
			console.error('Failed to copy history row:', error);
		}
	}

	async function handleRowRightClick(e: MouseEvent, item: TestSearchHistoryItem) {
		if (item.status === 'processing') return;
		e.preventDefault();
		const text = [item.input_fullname, item.input_address, item.ssn ? formatSSN(item.ssn) : '', item.dob ? formatDOBddmmyyyy(item.dob) : '']
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

	<div class="flex items-center justify-center">
		<h1 class="text-2xl font-semibold">Search</h1>
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

				{#if errorMessage}
					<p class="text-center text-sm text-destructive">{errorMessage}</p>
				{/if}

				<div class="flex justify-center">
					<Button onclick={handleSearch} disabled={!fullName.trim() || !address.trim() || searchLoading}>
						<SearchIcon class="mr-2 h-4 w-4" />
						Search — ${($user?.search_price ?? 2.00).toFixed(2)}
					</Button>
				</div>
			</div>
		</CardContent>
	</Card>

	<!-- History Section -->
	{#if !historyLoading && history.length > 0}
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
							<TableHead class="w-12 text-center">Status</TableHead>
							<TableHead class="text-center">Full Name</TableHead>
							<TableHead class="text-center">Full Address</TableHead>
							<TableHead class="text-center">SSN</TableHead>
							<TableHead class="text-center">DOB</TableHead>
							<TableHead class="text-center">Time</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each history.slice(0, HISTORY_LIMIT) as item (item.id)}
							<TableRow oncontextmenu={(e) => handleRowRightClick(e, item)}>
								<!-- Copy Button -->
								<TableCell class="text-center">
									<Button
										variant="ghost"
										size="sm"
										onclick={() => copyHistoryRow(item, `hist-${item.id}`)}
										disabled={item.status === 'processing'}
										class="mx-auto h-8 w-8 p-0"
									>
										{#if copiedCell === `hist-${item.id}`}
											<Check class="h-4 w-4 text-primary" />
										{:else}
											<Copy class="h-4 w-4" />
										{/if}
									</Button>
								</TableCell>

								<!-- Status -->
								<TableCell class="text-center">
									{#if item.status === 'processing'}
										<Clock class="mx-auto h-5 w-5 animate-pulse text-yellow-500" />
									{:else if item.status === 'done'}
										<CheckCircle class="mx-auto h-5 w-5 text-green-500" />
									{:else if item.status === 'nf'}
										<span class="mx-auto block text-xs font-bold text-red-500">NF</span>
									{/if}
								</TableCell>

								<!-- Full Name -->
								<TableCell
									class="cursor-pointer text-center text-sm transition-all duration-150"
									onclick={() => copyCellValue(item.status === 'done' ? (item.result_fullname || item.input_fullname) : item.input_fullname, `hist-${item.id}-name`)}
								>
									{#if copiedCell === `hist-${item.id}-name`}
										Copied
									{:else}
										{item.status === 'done' ? (item.result_fullname || item.input_fullname) : item.input_fullname}
									{/if}
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
									onclick={() => item.ssn && copyCellValue(formatSSN(item.ssn), `hist-${item.id}-ssn`)}
								>
									{#if copiedCell === `hist-${item.id}-ssn`}
										<span class="text-sm">Copied</span>
									{:else if item.ssn}
										<code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs"
											>{formatSSN(item.ssn)}</code
										>
									{:else if item.status === 'processing'}
										<span class="text-muted-foreground">...</span>
									{:else}
										<span class="text-muted-foreground">-</span>
									{/if}
								</TableCell>

								<!-- DOB -->
								<TableCell
									class="cursor-pointer text-center text-sm transition-all duration-150"
									onclick={() => item.dob && copyCellValue(formatDOBddmmyyyy(item.dob), `hist-${item.id}-dob`)}
								>
									{#if copiedCell === `hist-${item.id}-dob`}
										Copied
									{:else if item.dob}
										{formatDOBddmmyyyy(item.dob)}
									{:else if item.status === 'processing'}
										...
									{:else}
										-
									{/if}
								</TableCell>

								<!-- Time -->
								<TableCell class="text-center text-sm text-muted-foreground">
									{#if item.search_time != null}
										{item.search_time}s
									{:else if item.status === 'processing'}
										...
									{:else}
										-
									{/if}
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>

				{#if history.length > HISTORY_LIMIT}
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
