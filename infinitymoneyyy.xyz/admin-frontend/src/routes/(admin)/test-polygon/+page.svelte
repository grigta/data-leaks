<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Progress } from '$lib/components/ui/progress';
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
		SelectTrigger,
		SelectContent,
		SelectItem,
		SelectValue
	} from '$lib/components/ui/select';
	import Plus from '@lucide/svelte/icons/plus';
	import Play from '@lucide/svelte/icons/play';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import Eye from '@lucide/svelte/icons/eye';
	import Pencil from '@lucide/svelte/icons/pencil';
	import Download from '@lucide/svelte/icons/download';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import CheckCircle from '@lucide/svelte/icons/check-circle';
	import XCircle from '@lucide/svelte/icons/x-circle';
	import Search from '@lucide/svelte/icons/search';
	import AlertTriangle from '@lucide/svelte/icons/alert-triangle';
	import ClipboardPaste from '@lucide/svelte/icons/clipboard-paste';
	import {
		getTestPolygonTests,
		createTestPolygonTest,
		getTestPolygonTest,
		updateTestPolygonTest,
		deleteTestPolygonTest,
		runTestPolygonTest,
		getTestPolygonRun,
		getTestPolygonResults,
		getTestPolygonResultDebug,
		handleApiError,
		type TestPolygonTest,
		type TestPolygonTestDetail,
		type TestPolygonRun,
		type TestPolygonResult,
		type TestPolygonResultDebug
	} from '$lib/api/client';
	import { toast } from 'svelte-sonner';
	import { t } from '$lib/i18n';

	// ── Screen state ─────────────────────────────────────────
	type Screen = 'list' | 'create' | 'edit' | 'run';
	let screen = $state<Screen>('list');

	// ── List screen ──────────────────────────────────────────
	let tests = $state<TestPolygonTest[]>([]);
	let isLoading = $state(true);
	let totalCount = $state(0);

	// ── Create/Edit screen ───────────────────────────────────
	let editTestId = $state<string | null>(null);
	let testName = $state('');
	let testDescription = $state('');
	let editRecords = $state<Array<{ fullname: string; address: string; expected_ssn: string }>>([]);
	let inputMode = $state<'table' | 'bulk'>('table');
	let bulkText = $state('');
	let isSaving = $state(false);

	// ── Run screen ───────────────────────────────────────────
	let runTestObj = $state<TestPolygonTest | null>(null);
	let runProvider = $state('searchbug');
	let runParallelism = $state(5);
	let runSaveDebug = $state(true);
	let runPrioritization = $state('default');
	let currentRun = $state<TestPolygonRun | null>(null);
	let runResults = $state<TestPolygonResult[]>([]);
	let runResultsTotal = $state(0);
	let resultFilter = $state<string | null>(null);
	let isRunning = $state(false);
	let pollInterval = $state<ReturnType<typeof setInterval> | null>(null);

	// ── Debug dialog ─────────────────────────────────────────
	let showDebugDialog = $state(false);
	let debugResult = $state<TestPolygonResultDebug | null>(null);
	let debugLoading = $state(false);
	let debugIndex = $state(0);

	// ── Computed ─────────────────────────────────────────────
	let stats = $derived({
		totalTests: tests.length,
		totalRecords: tests.reduce((sum, t) => sum + t.records_count, 0),
		bestMatchRate: tests.reduce((best, t) => {
			const rate = t.last_run?.match_rate ?? 0;
			return rate > best ? rate : best;
		}, 0),
		lastRun: tests.reduce((latest: string | null, t) => {
			const d = t.last_run?.finished_at;
			if (!d) return latest;
			if (!latest) return d;
			return d > latest ? d : latest;
		}, null)
	});

	let runProgress = $derived(
		currentRun && currentRun.total_records > 0
			? Math.round((currentRun.processed_count / currentRun.total_records) * 100)
			: 0
	);

	// ── Load tests ───────────────────────────────────────────
	async function loadTests() {
		isLoading = true;
		try {
			const res = await getTestPolygonTests({ limit: 100 });
			tests = res.tests;
			totalCount = res.total_count;
		} catch (e: any) {
			handleApiError(e);
		} finally {
			isLoading = false;
		}
	}

	// ── Create/Edit ──────────────────────────────────────────
	function openCreate() {
		editTestId = null;
		testName = '';
		testDescription = '';
		editRecords = [{ fullname: '', address: '', expected_ssn: '' }];
		inputMode = 'table';
		bulkText = '';
		screen = 'create';
	}

	async function openEdit(test: TestPolygonTest) {
		try {
			const detail = await getTestPolygonTest(test.id);
			editTestId = test.id;
			testName = detail.name;
			testDescription = detail.description ?? '';
			editRecords = detail.records.map((r) => ({
				fullname: r.fullname,
				address: r.address,
				expected_ssn: r.expected_ssn
			}));
			inputMode = 'table';
			bulkText = '';
			screen = 'edit';
		} catch (e: any) {
			handleApiError(e);
		}
	}

	function addRow() {
		editRecords = [...editRecords, { fullname: '', address: '', expected_ssn: '' }];
	}

	function removeRow(index: number) {
		editRecords = editRecords.filter((_, i) => i !== index);
	}

	function parseBulkText() {
		const text = bulkText.trim();
		if (!text) return;

		const parsed: Array<{ fullname: string; address: string; expected_ssn: string }> = [];
		const ssnRegex = /\d{3}-\d{2}-\d{4}/;

		// Detect format: multi-line records (has SSN patterns) vs single-line CSV
		if (ssnRegex.test(text)) {
			// Smart multi-line parser — each record has name, address, SSN on separate lines
			let blocks: string[] = [];

			// Try quoted blocks first: "record1" "record2"
			const quoteRegex = /[""\u201C]([^""\u201D]+)[""\u201D]/g;
			let match;
			while ((match = quoteRegex.exec(text)) !== null) {
				blocks.push(match[1]);
			}

			// Fallback: split by double newlines
			if (blocks.length === 0) {
				blocks = text.split(/\n\s*\n/).filter((b) => b.trim());
			}

			for (const block of blocks) {
				const lines = block
					.split('\n')
					.map((l) => l.trim())
					.filter((l) => l.length > 0);

				let ssn = '';
				let name = '';
				const addressParts: string[] = [];

				for (const line of lines) {
					// SSN: 3-2-4 pattern (optionally prefixed with "ssn")
					const ssnMatch = line.match(/(?:^ssn\s+)?(\d{3}-\d{2}-\d{4})/i);
					if (ssnMatch && !ssn) {
						ssn = ssnMatch[1];
						continue;
					}

					// Phone: 10 digits, (XXX) XXX-XXXX, or XXX-XXX-XXXX
					const digitsOnly = line.replace(/[\s()\-]/g, '');
					if (/^\d{10}$/.test(digitsOnly) && !line.includes(',')) continue;
					if (/^\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}$/.test(line)) continue;

					// Email
					if (line.includes('@')) continue;

					// DOB: M/D/Y or MM/DD/YYYY
					if (/^\d{1,2}\/\d{1,2}\/\d{2,4}$/.test(line)) continue;

					// IP addresses / junk
					if (/\d+\.\d+\.\d+\.\d+/.test(line)) continue;

					// Name = first unclassified line, rest = address
					if (!name) {
						name = line;
					} else {
						addressParts.push(line);
					}
				}

				if (name && ssn) {
					parsed.push({
						fullname: name,
						address: addressParts.join(', '),
						expected_ssn: ssn
					});
				}
			}
		} else {
			// Line-by-line CSV/TSV parser (tab, comma, pipe separators)
			const lines = text
				.split('\n')
				.map((l) => l.trim())
				.filter((l) => l.length > 0);

			for (const line of lines) {
				let parts: string[] = [];
				if (line.includes('\t')) {
					parts = line.split('\t');
				} else if (line.includes('|')) {
					parts = line.split('|');
				} else if (line.includes(',')) {
					const lastComma = line.lastIndexOf(',');
					const secondLast = line.lastIndexOf(',', lastComma - 1);
					if (secondLast > 0) {
						parts = [
							line.slice(0, secondLast),
							line.slice(secondLast + 1, lastComma),
							line.slice(lastComma + 1)
						];
					} else {
						parts = line.split(',');
					}
				}

				parts = parts.map((p) => p.trim()).filter((p) => p.length > 0);
				if (parts.length >= 3) {
					parsed.push({
						fullname: parts[0],
						address: parts[1],
						expected_ssn: parts[parts.length - 1]
					});
				}
			}
		}

		if (parsed.length > 0) {
			editRecords = parsed;
			toast.success($t('test-polygon.parsedRecords', { count: parsed.length }));
			inputMode = 'table';
		} else {
			toast.error('Could not parse any records');
		}
	}

	async function handlePasteFromClipboard() {
		try {
			const text = await navigator.clipboard.readText();
			if (text) {
				bulkText = text;
				inputMode = 'bulk';
			}
		} catch {
			toast.error('Cannot read clipboard');
		}
	}

	async function saveTest() {
		const validRecords = editRecords.filter(
			(r) => r.fullname.trim() && r.address.trim() && r.expected_ssn.trim()
		);
		if (!testName.trim()) {
			toast.error('Test name is required');
			return;
		}
		if (validRecords.length === 0) {
			toast.error('At least one record is required');
			return;
		}

		isSaving = true;
		try {
			if (editTestId) {
				await updateTestPolygonTest(editTestId, {
					name: testName,
					description: testDescription || undefined,
					records: validRecords
				});
				toast.success('Test updated');
			} else {
				await createTestPolygonTest({
					name: testName,
					description: testDescription || undefined,
					records: validRecords
				});
				toast.success('Test created');
			}
			screen = 'list';
			await loadTests();
		} catch (e: any) {
			handleApiError(e);
		} finally {
			isSaving = false;
		}
	}

	// ── Delete ───────────────────────────────────────────────
	async function handleDelete(test: TestPolygonTest) {
		if (!confirm($t('test-polygon.confirmDelete'))) return;
		try {
			await deleteTestPolygonTest(test.id);
			toast.success('Test deleted');
			await loadTests();
		} catch (e: any) {
			handleApiError(e);
		}
	}

	// ── Run ──────────────────────────────────────────────────
	function openRun(test: TestPolygonTest) {
		runTestObj = test;
		currentRun = null;
		runResults = [];
		runResultsTotal = 0;
		resultFilter = null;
		screen = 'run';
	}

	async function startRun() {
		if (!runTestObj) return;
		isRunning = true;

		try {
			const run = await runTestPolygonTest(runTestObj.id, {
				provider: runProvider,
				save_debug: runSaveDebug,
				parallelism: runParallelism,
				prioritization: runPrioritization
			});
			currentRun = run;
			startPolling(run.id);
		} catch (e: any) {
			handleApiError(e);
			isRunning = false;
		}
	}

	function startPolling(runId: string) {
		stopPolling();
		pollInterval = setInterval(async () => {
			try {
				const run = await getTestPolygonRun(runId);
				currentRun = run;

				if (run.status === 'completed' || run.status === 'failed') {
					stopPolling();
					isRunning = false;
					await loadRunResults(runId);
					await loadTests(); // Refresh list stats
				}
			} catch (e) {
				console.error('Polling error:', e);
			}
		}, 2000);
	}

	function stopPolling() {
		if (pollInterval) {
			clearInterval(pollInterval);
			pollInterval = null;
		}
	}

	async function loadRunResults(runId: string) {
		try {
			const res = await getTestPolygonResults(runId, {
				status_filter: resultFilter ?? undefined,
				limit: 200
			});
			runResults = res.results;
			runResultsTotal = res.total_count;
		} catch (e: any) {
			handleApiError(e);
		}
	}

	async function changeResultFilter(filter: string | null) {
		resultFilter = filter;
		if (currentRun) {
			await loadRunResults(currentRun.id);
		}
	}

	// ── View existing run results ────────────────────────────
	async function openRunResults(test: TestPolygonTest) {
		if (!test.last_run) return;
		runTestObj = test;

		try {
			currentRun = await getTestPolygonRun(test.last_run.id);
			resultFilter = null;
			await loadRunResults(test.last_run.id);
			screen = 'run';
		} catch (e: any) {
			handleApiError(e);
		}
	}

	// ── Debug dialog ─────────────────────────────────────────
	async function openDebug(result: TestPolygonResult, index: number) {
		if (!currentRun) return;
		debugIndex = index;
		debugResult = null;
		debugLoading = true;
		showDebugDialog = true;

		try {
			console.log('[debug] fetching debug for result', result.id);
			const data = await getTestPolygonResultDebug(currentRun.id, result.id);
			console.log('[debug] got data', data?.status, 'debug_data:', !!data?.debug_data);
			debugResult = data;
			console.log('[debug] debugResult set, debugLoading will be false');
		} catch (e: any) {
			console.error('[debug] error:', e);
			toast.error(handleApiError(e));
			showDebugDialog = false;
		} finally {
			debugLoading = false;
			console.log('[debug] debugLoading =', debugLoading, 'debugResult =', !!debugResult);
		}
	}

	async function navigateDebug(direction: -1 | 1) {
		const newIndex = debugIndex + direction;
		if (newIndex < 0 || newIndex >= runResults.length || !currentRun) return;
		debugIndex = newIndex;
		debugLoading = true;

		try {
			const data = await getTestPolygonResultDebug(currentRun.id, runResults[newIndex].id);
			debugResult = data;
		} catch (e: any) {
			toast.error(handleApiError(e));
		} finally {
			debugLoading = false;
		}
	}

	// ── Export CSV ────────────────────────────────────────────
	function exportCsv() {
		if (runResults.length === 0) return;
		const header = 'Fullname,Address,Expected SSN,Found SSN,Status,Best Method,Keys Count,Search Time\n';
		const rows = runResults
			.map(
				(r) =>
					`"${r.fullname}","${r.address}","${r.expected_ssn}","${r.found_ssn ?? ''}","${r.status}","${r.best_method ?? ''}",${r.matched_keys_count},${r.search_time?.toFixed(2) ?? ''}`
			)
			.join('\n');

		const blob = new Blob([header + rows], { type: 'text/csv' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `test-polygon-results-${new Date().toISOString().slice(0, 10)}.csv`;
		a.click();
		URL.revokeObjectURL(url);
	}

	// ── Helpers ──────────────────────────────────────────────
	function getStatusBadge(status: string): { variant: 'default' | 'secondary' | 'destructive' | 'outline'; label: string } {
		switch (status) {
			case 'match':
				return { variant: 'default', label: $t('test-polygon.matched') };
			case 'not_found':
				return { variant: 'secondary', label: $t('test-polygon.notFound') };
			case 'wrong_ssn':
				return { variant: 'destructive', label: $t('test-polygon.wrongSsn') };
			case 'error':
				return { variant: 'destructive', label: $t('test-polygon.errors') };
			default:
				return { variant: 'outline', label: status };
		}
	}

	function getDiagnosis(): string {
		if (!debugResult?.debug_data) return '';
		const dd = debugResult.debug_data;
		if (dd.level1_candidates_count === 0) return $t('test-polygon.diagnosisNoBloom');
		if (dd.final_results.length === 0) return $t('test-polygon.diagnosisNoL2');
		if (debugResult.status === 'wrong_ssn') return $t('test-polygon.diagnosisWrongSsn');
		if (debugResult.status === 'match') return $t('test-polygon.diagnosisMatch');
		return '';
	}

	function formatTime(seconds: number | null): string {
		if (seconds === null) return '-';
		return `${seconds.toFixed(2)}s`;
	}

	function formatDate(dateStr: string | null): string {
		if (!dateStr) return '-';
		return new Date(dateStr).toLocaleString();
	}

	function goBack() {
		stopPolling();
		screen = 'list';
	}

	onMount(() => {
		loadTests();
		return () => stopPolling();
	});
</script>

<!-- ═══════════════════════════════════════════════════════════ -->
<!-- SCREEN: TEST LIST                                         -->
<!-- ═══════════════════════════════════════════════════════════ -->
{#if screen === 'list'}
	<div class="space-y-6">
		<!-- Stats cards -->
		<div class="grid grid-cols-4 gap-4">
			<Card>
				<CardContent class="pt-6">
					<div class="text-2xl font-bold">{stats.totalTests}</div>
					<p class="text-sm text-muted-foreground">{$t('test-polygon.totalTests')}</p>
				</CardContent>
			</Card>
			<Card>
				<CardContent class="pt-6">
					<div class="text-2xl font-bold">{stats.totalRecords}</div>
					<p class="text-sm text-muted-foreground">{$t('test-polygon.totalRecords')}</p>
				</CardContent>
			</Card>
			<Card>
				<CardContent class="pt-6">
					<div class="text-2xl font-bold">{stats.bestMatchRate}%</div>
					<p class="text-sm text-muted-foreground">{$t('test-polygon.bestMatchRate')}</p>
				</CardContent>
			</Card>
			<Card>
				<CardContent class="pt-6">
					<div class="text-2xl font-bold text-sm">{formatDate(stats.lastRun)}</div>
					<p class="text-sm text-muted-foreground">{$t('test-polygon.lastRunDate')}</p>
				</CardContent>
			</Card>
		</div>

		<!-- Header + Create button -->
		<div class="flex items-center justify-between">
			<h2 class="text-lg font-semibold">{$t('test-polygon.title')}</h2>
			<Button onclick={openCreate}>
				<Plus class="mr-2 h-4 w-4" />
				{$t('test-polygon.createTest')}
			</Button>
		</div>

		<!-- Tests table -->
		{#if isLoading}
			<div class="flex items-center justify-center py-12">
				<Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
			</div>
		{:else if tests.length === 0}
			<Card>
				<CardContent class="py-12 text-center text-muted-foreground">
					{$t('test-polygon.noTests')}
				</CardContent>
			</Card>
		{:else}
			<Card>
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>{$t('test-polygon.testName')}</TableHead>
							<TableHead class="text-center">{$t('test-polygon.records')}</TableHead>
							<TableHead class="text-center">{$t('test-polygon.matchRate')}</TableHead>
							<TableHead>{$t('test-polygon.lastRun')}</TableHead>
							<TableHead class="text-right">Actions</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each tests as test}
							<TableRow>
								<TableCell>
									<div class="font-medium">{test.name}</div>
									{#if test.description}
										<div class="text-sm text-muted-foreground">{test.description}</div>
									{/if}
								</TableCell>
								<TableCell class="text-center">{test.records_count}</TableCell>
								<TableCell class="text-center">
									{#if test.last_run}
										<Badge
											variant={test.last_run.match_rate >= 80 ? 'default' : test.last_run.match_rate >= 50 ? 'secondary' : 'destructive'}
										>
											{test.last_run.match_rate}%
										</Badge>
									{:else}
										<span class="text-muted-foreground">-</span>
									{/if}
								</TableCell>
								<TableCell>
									{#if test.last_run}
										<div class="text-sm">{formatDate(test.last_run.finished_at)}</div>
										<div class="text-xs text-muted-foreground">
											{test.last_run.matched_count}M / {test.last_run.not_found_count}NF / {test.last_run.wrong_ssn_count}W
										</div>
									{:else}
										<span class="text-muted-foreground">Never</span>
									{/if}
								</TableCell>
								<TableCell class="text-right">
									<div class="flex items-center justify-end gap-1">
										<Button variant="ghost" size="icon" onclick={() => openRun(test)} title={$t('test-polygon.runTest')}>
											<Play class="h-4 w-4" />
										</Button>
										{#if test.last_run}
											<Button variant="ghost" size="icon" onclick={() => openRunResults(test)} title={$t('test-polygon.results')}>
												<Eye class="h-4 w-4" />
											</Button>
										{/if}
										<Button variant="ghost" size="icon" onclick={() => openEdit(test)} title={$t('test-polygon.editTest')}>
											<Pencil class="h-4 w-4" />
										</Button>
										<Button variant="ghost" size="icon" onclick={() => handleDelete(test)} title={$t('test-polygon.deleteTest')}>
											<Trash2 class="h-4 w-4 text-destructive" />
										</Button>
									</div>
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
			</Card>
		{/if}
	</div>

<!-- ═══════════════════════════════════════════════════════════ -->
<!-- SCREEN: CREATE / EDIT TEST                                -->
<!-- ═══════════════════════════════════════════════════════════ -->
{:else if screen === 'create' || screen === 'edit'}
	<div class="space-y-6">
		<div class="flex items-center gap-4">
			<Button variant="ghost" size="icon" onclick={goBack}>
				<ArrowLeft class="h-5 w-5" />
			</Button>
			<h2 class="text-lg font-semibold">
				{screen === 'create' ? $t('test-polygon.createTitle') : $t('test-polygon.editTitle')}
			</h2>
		</div>

		<!-- Name & Description -->
		<Card>
			<CardContent class="space-y-4 pt-6">
				<div class="space-y-2">
					<Label>{$t('test-polygon.testName')}</Label>
					<Input bind:value={testName} placeholder="Test Set #1" />
				</div>
				<div class="space-y-2">
					<Label>{$t('test-polygon.description')}</Label>
					<Input bind:value={testDescription} placeholder="Optional description" />
				</div>
			</CardContent>
		</Card>

		<!-- Input mode toggle -->
		<div class="flex items-center gap-2">
			<Button
				variant={inputMode === 'table' ? 'default' : 'outline'}
				size="sm"
				onclick={() => (inputMode = 'table')}
			>
				{$t('test-polygon.tableInput')}
			</Button>
			<Button
				variant={inputMode === 'bulk' ? 'default' : 'outline'}
				size="sm"
				onclick={() => (inputMode = 'bulk')}
			>
				{$t('test-polygon.bulkPaste')}
			</Button>
			<div class="flex-1"></div>
			<Button variant="outline" size="sm" onclick={handlePasteFromClipboard}>
				<ClipboardPaste class="mr-2 h-4 w-4" />
				{$t('test-polygon.pasteClipboard')}
			</Button>
		</div>

		<!-- Table input -->
		{#if inputMode === 'table'}
			<Card>
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead class="w-8">#</TableHead>
							<TableHead>{$t('test-polygon.fullname')}</TableHead>
							<TableHead>{$t('test-polygon.address')}</TableHead>
							<TableHead class="w-40">{$t('test-polygon.expectedSsn')}</TableHead>
							<TableHead class="w-20"></TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each editRecords as record, i}
							<TableRow>
								<TableCell class="text-muted-foreground">{i + 1}</TableCell>
								<TableCell>
									<Input
										bind:value={record.fullname}
										placeholder="JOHN SMITH"
										class="h-8"
									/>
								</TableCell>
								<TableCell>
									<Input
										bind:value={record.address}
										placeholder="123 MAIN ST, CITY, ST 12345"
										class="h-8"
									/>
								</TableCell>
								<TableCell>
									<Input
										bind:value={record.expected_ssn}
										placeholder="123-45-6789"
										class="h-8"
									/>
								</TableCell>
								<TableCell>
									<Button
										variant="ghost"
										size="icon"
										onclick={() => removeRow(i)}
										disabled={editRecords.length <= 1}
									>
										<Trash2 class="h-4 w-4 text-destructive" />
									</Button>
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
				<div class="border-t p-3">
					<Button variant="outline" size="sm" onclick={addRow}>
						<Plus class="mr-2 h-4 w-4" />
						{$t('test-polygon.addRow')}
					</Button>
					<span class="ml-4 text-sm text-muted-foreground">
						{editRecords.filter((r) => r.fullname.trim()).length} {$t('test-polygon.records').toLowerCase()}
					</span>
				</div>
			</Card>

		<!-- Bulk paste -->
		{:else}
			<Card>
				<CardContent class="space-y-4 pt-6">
					<Textarea
						bind:value={bulkText}
						placeholder={$t('test-polygon.bulkPlaceholder')}
						rows={12}
						class="font-mono text-sm"
					/>
					<Button onclick={parseBulkText}>
						{$t('test-polygon.parseData')}
					</Button>
				</CardContent>
			</Card>
		{/if}

		<!-- Save/Cancel -->
		<div class="flex items-center gap-3">
			<Button onclick={saveTest} disabled={isSaving}>
				{#if isSaving}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
				{/if}
				{$t('test-polygon.save')}
			</Button>
			<Button variant="outline" onclick={goBack}>
				{$t('test-polygon.cancel')}
			</Button>
		</div>
	</div>

<!-- ═══════════════════════════════════════════════════════════ -->
<!-- SCREEN: RUN TEST & RESULTS                                -->
<!-- ═══════════════════════════════════════════════════════════ -->
{:else if screen === 'run'}
	<div class="space-y-6">
		<div class="flex items-center gap-4">
			<Button variant="ghost" size="icon" onclick={goBack}>
				<ArrowLeft class="h-5 w-5" />
			</Button>
			<h2 class="text-lg font-semibold">
				{runTestObj?.name ?? 'Test'}
			</h2>
			{#if currentRun}
				<Badge variant={currentRun.status === 'completed' ? 'default' : currentRun.status === 'failed' ? 'destructive' : 'secondary'}>
					{currentRun.status}
				</Badge>
			{/if}
		</div>

		<!-- Run config (before run or for re-run) -->
		{#if !currentRun || currentRun.status === 'completed' || currentRun.status === 'failed'}
			<Card>
				<CardHeader>
					<CardTitle class="text-base">{$t('test-polygon.runConfig')}</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="grid grid-cols-4 gap-4">
						<div class="space-y-2">
							<Label>{$t('test-polygon.provider')}</Label>
							<Select
								value={runProvider}
								onSelectedChange={(sel) => {
									if (sel?.value) runProvider = sel.value;
								}}
							>
								<SelectTrigger>
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="searchbug">{$t('test-polygon.searchbug')}</SelectItem>
									<SelectItem value="whitepages">{$t('test-polygon.whitepages')}</SelectItem>
								</SelectContent>
							</Select>
						</div>

						<div class="space-y-2">
							<Label>{$t('test-polygon.prioritization')}</Label>
							<Select
								value={runPrioritization}
								onSelectedChange={(sel) => {
									if (sel?.value) runPrioritization = sel.value;
								}}
							>
								<SelectTrigger>
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="default">{$t('test-polygon.prioritizationDefault')}</SelectItem>
									<SelectItem value="quality_first">{$t('test-polygon.prioritizationQuality')}</SelectItem>
									<SelectItem value="quantity_first">{$t('test-polygon.prioritizationQuantity')}</SelectItem>
								</SelectContent>
							</Select>
						</div>

						<div class="space-y-2">
							<Label>{$t('test-polygon.parallelism')}</Label>
							<Input type="number" bind:value={runParallelism} min={1} max={20} />
						</div>

						<div class="flex items-end space-x-2">
							<label class="flex items-center gap-2 cursor-pointer">
								<input type="checkbox" bind:checked={runSaveDebug} class="h-4 w-4" />
								<span class="text-sm">{$t('test-polygon.saveDebug')}</span>
							</label>
						</div>
					</div>

					<Button onclick={startRun} disabled={isRunning}>
						{#if isRunning}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							{$t('test-polygon.running')}
						{:else}
							<Play class="mr-2 h-4 w-4" />
							{currentRun ? $t('test-polygon.reRunTest') : $t('test-polygon.startRun')}
						{/if}
					</Button>
				</CardContent>
			</Card>
		{/if}

		<!-- Running progress -->
		{#if currentRun && currentRun.status === 'running'}
			<Card>
				<CardContent class="space-y-4 pt-6">
					<div class="flex items-center justify-between text-sm">
						<span>{$t('test-polygon.processed')}: {currentRun.processed_count} / {currentRun.total_records}</span>
						<span>{runProgress}%</span>
					</div>
					<Progress value={runProgress} class="h-2" />
					<div class="grid grid-cols-4 gap-4 text-center">
						<div>
							<div class="text-lg font-bold text-green-600">{currentRun.matched_count}</div>
							<div class="text-xs text-muted-foreground">{$t('test-polygon.matched')}</div>
						</div>
						<div>
							<div class="text-lg font-bold text-gray-500">{currentRun.not_found_count}</div>
							<div class="text-xs text-muted-foreground">{$t('test-polygon.notFound')}</div>
						</div>
						<div>
							<div class="text-lg font-bold text-red-600">{currentRun.wrong_ssn_count}</div>
							<div class="text-xs text-muted-foreground">{$t('test-polygon.wrongSsn')}</div>
						</div>
						<div>
							<div class="text-lg font-bold text-orange-600">{currentRun.error_count}</div>
							<div class="text-xs text-muted-foreground">{$t('test-polygon.errors')}</div>
						</div>
					</div>
				</CardContent>
			</Card>
		{/if}

		<!-- Results -->
		{#if currentRun && (currentRun.status === 'completed' || currentRun.status === 'failed')}
			<!-- Summary cards -->
			<div class="grid grid-cols-5 gap-3">
				<Card class="cursor-pointer" onclick={() => changeResultFilter(null)}>
					<CardContent class="pt-4 text-center">
						<div class="text-xl font-bold">{currentRun.total_records}</div>
						<div class="text-xs text-muted-foreground">{$t('test-polygon.allResults')}</div>
					</CardContent>
				</Card>
				<Card class="cursor-pointer" onclick={() => changeResultFilter('match')}>
					<CardContent class="pt-4 text-center">
						<div class="text-xl font-bold text-green-600">{currentRun.matched_count}</div>
						<div class="text-xs text-muted-foreground">{$t('test-polygon.filterMatched')}</div>
					</CardContent>
				</Card>
				<Card class="cursor-pointer" onclick={() => changeResultFilter('not_found')}>
					<CardContent class="pt-4 text-center">
						<div class="text-xl font-bold text-gray-500">{currentRun.not_found_count}</div>
						<div class="text-xs text-muted-foreground">{$t('test-polygon.filterNotFound')}</div>
					</CardContent>
				</Card>
				<Card class="cursor-pointer" onclick={() => changeResultFilter('wrong_ssn')}>
					<CardContent class="pt-4 text-center">
						<div class="text-xl font-bold text-red-600">{currentRun.wrong_ssn_count}</div>
						<div class="text-xs text-muted-foreground">{$t('test-polygon.filterWrongSsn')}</div>
					</CardContent>
				</Card>
				<Card class="cursor-pointer" onclick={() => changeResultFilter('error')}>
					<CardContent class="pt-4 text-center">
						<div class="text-xl font-bold text-orange-600">{currentRun.error_count}</div>
						<div class="text-xs text-muted-foreground">{$t('test-polygon.filterErrors')}</div>
					</CardContent>
				</Card>
			</div>

			<!-- Filter bar + export -->
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-2">
					<Button
						variant={resultFilter === null ? 'default' : 'outline'}
						size="sm"
						onclick={() => changeResultFilter(null)}
					>
						{$t('test-polygon.allResults')} ({currentRun.total_records})
					</Button>
					<Button
						variant={resultFilter === 'match' ? 'default' : 'outline'}
						size="sm"
						onclick={() => changeResultFilter('match')}
					>
						<CheckCircle class="mr-1 h-3 w-3" />
						{$t('test-polygon.filterMatched')}
					</Button>
					<Button
						variant={resultFilter === 'not_found' ? 'default' : 'outline'}
						size="sm"
						onclick={() => changeResultFilter('not_found')}
					>
						<Search class="mr-1 h-3 w-3" />
						{$t('test-polygon.filterNotFound')}
					</Button>
					<Button
						variant={resultFilter === 'wrong_ssn' ? 'default' : 'outline'}
						size="sm"
						onclick={() => changeResultFilter('wrong_ssn')}
					>
						<XCircle class="mr-1 h-3 w-3" />
						{$t('test-polygon.filterWrongSsn')}
					</Button>
					<Button
						variant={resultFilter === 'error' ? 'default' : 'outline'}
						size="sm"
						onclick={() => changeResultFilter('error')}
					>
						<AlertTriangle class="mr-1 h-3 w-3" />
						{$t('test-polygon.filterErrors')}
					</Button>
				</div>

				<Button variant="outline" size="sm" onclick={exportCsv}>
					<Download class="mr-2 h-4 w-4" />
					{$t('test-polygon.exportCsv')}
				</Button>
			</div>

			<!-- Results table -->
			{#if runResults.length === 0}
				<Card>
					<CardContent class="py-8 text-center text-muted-foreground">
						{$t('test-polygon.noResults')}
					</CardContent>
				</Card>
			{:else}
				<Card>
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead class="w-8">#</TableHead>
								<TableHead>{$t('test-polygon.fullname')}</TableHead>
								<TableHead>{$t('test-polygon.address')}</TableHead>
								<TableHead>{$t('test-polygon.expectedSsn')}</TableHead>
								<TableHead>{$t('test-polygon.foundSsn')}</TableHead>
								<TableHead class="text-center">Status</TableHead>
								<TableHead>{$t('test-polygon.bestMethod')}</TableHead>
								<TableHead class="text-center">{$t('test-polygon.keysCount')}</TableHead>
								<TableHead class="text-center">{$t('test-polygon.searchTime')}</TableHead>
								<TableHead class="w-12"></TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each runResults as result, i}
								{@const badge = getStatusBadge(result.status)}
								<TableRow>
									<TableCell class="text-muted-foreground">{result.sort_order + 1}</TableCell>
									<TableCell class="max-w-[200px] truncate font-mono text-xs">{result.fullname}</TableCell>
									<TableCell class="max-w-[250px] truncate font-mono text-xs">{result.address}</TableCell>
									<TableCell class="font-mono text-xs">{result.expected_ssn}</TableCell>
									<TableCell class="font-mono text-xs">{result.found_ssn ?? '-'}</TableCell>
									<TableCell class="text-center">
										<Badge variant={badge.variant}>{badge.label}</Badge>
									</TableCell>
									<TableCell class="text-xs">{result.best_method ?? '-'}</TableCell>
									<TableCell class="text-center">{result.matched_keys_count}</TableCell>
									<TableCell class="text-center text-xs">{formatTime(result.search_time)}</TableCell>
									<TableCell>
										<Button variant="ghost" size="icon" onclick={() => openDebug(result, i)}>
											<Eye class="h-4 w-4" />
										</Button>
									</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				</Card>
			{/if}
		{/if}
	</div>
{/if}

<!-- ═══════════════════════════════════════════════════════════ -->
<!-- DIALOG: DEBUG REPORT                                      -->
<!-- ═══════════════════════════════════════════════════════════ -->
<Dialog bind:open={showDebugDialog}>
	<DialogContent class="max-w-4xl max-h-[90vh] overflow-y-auto">
		<DialogHeader>
			<div class="flex items-center justify-between">
				<DialogTitle>{$t('test-polygon.debugTitle')}</DialogTitle>
				<div class="flex items-center gap-2">
					<Button
						variant="outline"
						size="sm"
						disabled={debugIndex === 0}
						onclick={() => navigateDebug(-1)}
					>
						<ChevronLeft class="h-4 w-4" />
						{$t('test-polygon.prev')}
					</Button>
					<span class="text-sm text-muted-foreground">{debugIndex + 1} / {runResults.length}</span>
					<Button
						variant="outline"
						size="sm"
						disabled={debugIndex >= runResults.length - 1}
						onclick={() => navigateDebug(1)}
					>
						{$t('test-polygon.next')}
						<ChevronRight class="h-4 w-4" />
					</Button>
				</div>
			</div>
		</DialogHeader>

		{#if !debugResult}
			<div class="flex items-center justify-center py-12">
				<Loader2 class="h-8 w-8 animate-spin" />
			</div>
		{:else}
			<div class="space-y-6">
				<!-- Record info -->
				<div class="rounded-md border p-4 space-y-2">
					<div class="grid grid-cols-2 gap-4 text-sm">
						<div>
							<span class="text-muted-foreground">{$t('test-polygon.fullname')}:</span>
							<span class="ml-2 font-mono">{debugResult.fullname}</span>
						</div>
						<div>
							<span class="text-muted-foreground">{$t('test-polygon.address')}:</span>
							<span class="ml-2 font-mono">{debugResult.address}</span>
						</div>
						<div>
							<span class="text-muted-foreground">{$t('test-polygon.expectedSsn')}:</span>
							<span class="ml-2 font-mono">{debugResult.expected_ssn}</span>
						</div>
						<div>
							<span class="text-muted-foreground">{$t('test-polygon.foundSsn')}:</span>
							<span class="ml-2 font-mono">{debugResult.found_ssn ?? '-'}</span>
							<Badge variant={getStatusBadge(debugResult.status).variant} class="ml-2">{getStatusBadge(debugResult.status).label}</Badge>
						</div>
					</div>
				</div>

				<!-- Diagnosis -->
				{#if getDiagnosis()}
					<div class="rounded-md border-l-4 p-4 {debugResult.status === 'match' ? 'border-green-500 bg-green-50 dark:bg-green-950' : 'border-yellow-500 bg-yellow-50 dark:bg-yellow-950'}">
						<div class="font-medium text-sm">{$t('test-polygon.diagnosis')}</div>
						<div class="text-sm mt-1">{getDiagnosis()}</div>
					</div>
				{/if}

				{#if !debugResult.debug_data}
					<div class="py-8 text-center text-muted-foreground">
						{$t('test-polygon.noDebugData')}
					</div>
				{:else}
					{@const dd = debugResult.debug_data}

					<!-- SearchBug Response -->
					<div>
						<h4 class="font-medium text-sm mb-2">{$t('test-polygon.searchbugResponse')}</h4>
						<div class="rounded-md border p-3 text-xs font-mono space-y-1">
							<div>Name: {dd.searchbug_data.firstname} {dd.searchbug_data.middlename ?? ''} {dd.searchbug_data.lastname}</div>
							<div>DOB: {dd.searchbug_data.dob || '-'}</div>
							<div>Phones: {dd.searchbug_data.phones.join(', ') || '-'}</div>
							{#each dd.searchbug_data.addresses as addr}
								<div>Address: {addr.address}, {addr.state}</div>
							{/each}
						</div>
					</div>

					<!-- Bloom Keys -->
					<div>
						<h4 class="font-medium text-sm mb-2">{$t('test-polygon.bloomKeys')}</h4>
						<div class="grid grid-cols-2 gap-4">
							<div>
								<div class="text-xs text-muted-foreground mb-1">{$t('test-polygon.phoneKeys')}</div>
								{#each dd.bloom_keys_phone as bk}
									<div class="flex items-center gap-2 text-xs font-mono py-0.5">
										{#if bk.found}
											<CheckCircle class="h-3 w-3 text-green-600" />
										{:else}
											<XCircle class="h-3 w-3 text-gray-400" />
										{/if}
										{bk.key}
										{#if bk.count > 0}
											<span class="text-muted-foreground">({bk.count})</span>
										{/if}
									</div>
								{/each}
								{#if dd.bloom_keys_phone.length === 0}
									<div class="text-xs text-muted-foreground">-</div>
								{/if}
							</div>
							<div>
								<div class="text-xs text-muted-foreground mb-1">{$t('test-polygon.addressKeys')}</div>
								{#each dd.bloom_keys_address as bk}
									<div class="flex items-center gap-2 text-xs font-mono py-0.5">
										{#if bk.found}
											<CheckCircle class="h-3 w-3 text-green-600" />
										{:else}
											<XCircle class="h-3 w-3 text-gray-400" />
										{/if}
										{bk.key}
										{#if bk.count > 0}
											<span class="text-muted-foreground">({bk.count})</span>
										{/if}
									</div>
								{/each}
								{#if dd.bloom_keys_address.length === 0}
									<div class="text-xs text-muted-foreground">-</div>
								{/if}
							</div>
						</div>
					</div>

					<!-- Search Keys (L2) -->
					{#if dd.query_keys.length > 0}
						<div>
							<h4 class="font-medium text-sm mb-2">{$t('test-polygon.searchKeys')}</h4>
							<div class="rounded-md border overflow-hidden">
								<Table>
									<TableHeader>
										<TableRow>
											<TableHead class="text-xs">{$t('test-polygon.method')}</TableHead>
											<TableHead class="text-xs">{$t('test-polygon.key')}</TableHead>
											<TableHead class="text-xs text-center">{$t('test-polygon.matchedKey')}</TableHead>
										</TableRow>
									</TableHeader>
									<TableBody>
										{#each dd.query_keys as qk}
											<TableRow class={qk.matched ? 'bg-green-50 dark:bg-green-950' : ''}>
												<TableCell class="text-xs">{qk.method}</TableCell>
												<TableCell class="text-xs font-mono">{qk.key}</TableCell>
												<TableCell class="text-center">
													{#if qk.matched}
														<CheckCircle class="h-3 w-3 text-green-600 inline" />
													{:else}
														<span class="text-muted-foreground">-</span>
													{/if}
												</TableCell>
											</TableRow>
										{/each}
									</TableBody>
								</Table>
							</div>
						</div>
					{/if}

					<!-- Candidates -->
					{#if dd.candidates.length > 0}
						<div>
							<h4 class="font-medium text-sm mb-2">
								{$t('test-polygon.allCandidates')} ({dd.candidates.length})
							</h4>
							<div class="rounded-md border overflow-x-auto">
								<Table>
									<TableHeader>
										<TableRow>
											<TableHead class="text-xs">SSN</TableHead>
											<TableHead class="text-xs">Name</TableHead>
											<TableHead class="text-xs">Address</TableHead>
											<TableHead class="text-xs">{$t('test-polygon.sourceTable')}</TableHead>
											<TableHead class="text-xs text-center">{$t('test-polygon.keysCount')}</TableHead>
											<TableHead class="text-xs">{$t('test-polygon.priority')}</TableHead>
										</TableRow>
									</TableHeader>
									<TableBody>
										{#each [...dd.candidates].sort((a, b) => b.matched_keys_count - a.matched_keys_count) as cand}
											<TableRow class={cand.matched_keys_count > 0 ? 'bg-green-50 dark:bg-green-950' : ''}>
												<TableCell class="text-xs font-mono">{cand.ssn}</TableCell>
												<TableCell class="text-xs">{cand.firstname} {cand.lastname}</TableCell>
												<TableCell class="text-xs max-w-[200px] truncate">{cand.address}</TableCell>
												<TableCell class="text-xs">{cand.source_table}</TableCell>
												<TableCell class="text-center text-xs">{cand.matched_keys_count}</TableCell>
												<TableCell class="text-xs">{cand.best_priority ?? '-'}</TableCell>
											</TableRow>
										{/each}
									</TableBody>
								</Table>
							</div>
						</div>
					{/if}
				{/if}
			</div>
		{/if}
	</DialogContent>
</Dialog>
