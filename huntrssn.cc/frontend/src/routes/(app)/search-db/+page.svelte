<script lang="ts">
	import { onMount } from 'svelte';
	import {
		searchDB,
		handleApiError,
		type SearchDBResponse,
		type SearchDBRecord
	} from '$lib/api/client';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Badge } from '$lib/components/ui/badge';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import Database from '@lucide/svelte/icons/database';
	import Search from '@lucide/svelte/icons/search';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import { toast } from 'svelte-sonner';
	import { user } from '$lib/stores/auth';
	import { goto } from '$app/navigation';
	import { formatDOB } from '$lib/utils';
	import { dateFormat } from '$lib/stores/dateFormat';

	// State
	let ssn = $state('');
	let isLoading = $state(false);
	let errorMessage = $state('');
	let result = $state<SearchDBResponse | null>(null);
	let copiedId = $state<string | null>(null);

	// Check admin access
	onMount(() => {
		if (!$user?.is_admin) {
			toast.error('Admin access required');
			goto('/dashboard');
		}
	});

	async function handleSearch() {
		const cleanSSN = ssn.trim().replace(/\s/g, '');
		if (!cleanSSN || cleanSSN.length < 4) {
			toast.error('Please enter at least 4 digits of SSN');
			return;
		}

		isLoading = true;
		errorMessage = '';
		result = null;

		try {
			result = await searchDB({ ssn: cleanSSN });
			if (result.count > 0) {
				toast.success(`Found ${result.count} record(s)`);
			} else {
				toast.info('No records found');
			}
		} catch (error) {
			errorMessage = handleApiError(error);
			toast.error(errorMessage);
		} finally {
			isLoading = false;
		}
	}

	async function copyToClipboard(text: string, id: string) {
		try {
			await navigator.clipboard.writeText(text);
			toast.success('Copied to clipboard');
			copiedId = id;
			setTimeout(() => {
				copiedId = null;
			}, 2000);
		} catch (error) {
			toast.error('Failed to copy');
		}
	}

	async function copyAllResults() {
		if (!result?.results.length) return;
		try {
			const text = JSON.stringify(result.results, null, 2);
			await navigator.clipboard.writeText(text);
			toast.success('All results copied');
		} catch (error) {
			toast.error('Failed to copy');
		}
	}


	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !isLoading) {
			handleSearch();
		}
	}
</script>

<svelte:head>
	<title>Search DB | Hunter SSN</title>
</svelte:head>

<div class="container mx-auto max-w-7xl space-y-6 p-4">
	<!-- Header -->
	<div class="flex items-center gap-3">
		<Database class="h-8 w-8 text-orange-500" />
		<div>
			<h1 class="text-2xl font-bold">Search DB</h1>
			<p class="text-muted-foreground text-sm">Direct database lookup by SSN (Admin only)</p>
		</div>
	</div>

	<!-- Search Form -->
	<Card>
		<CardHeader>
			<CardTitle class="text-lg">Search Parameters</CardTitle>
		</CardHeader>
		<CardContent>
			<div class="flex flex-col gap-4 sm:flex-row sm:items-end">
				<div class="flex-1 space-y-2">
					<Label for="ssn">SSN (full or last 4 digits)</Label>
					<Input
						id="ssn"
						type="text"
						placeholder="XXX-XX-XXXX or XXXX"
						bind:value={ssn}
						onkeydown={handleKeydown}
						disabled={isLoading}
						class="font-mono"
					/>
				</div>
				<Button onclick={handleSearch} disabled={isLoading} class="min-w-[120px]">
					{#if isLoading}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						Searching...
					{:else}
						<Search class="mr-2 h-4 w-4" />
						Search
					{/if}
				</Button>
			</div>
		</CardContent>
	</Card>

	<!-- Error -->
	{#if errorMessage}
		<Alert variant="destructive">
			<AlertCircle class="h-4 w-4" />
			<AlertDescription>{errorMessage}</AlertDescription>
		</Alert>
	{/if}

	<!-- Results -->
	{#if result}
		<Card>
			<CardHeader class="flex flex-row items-center justify-between">
				<div>
					<CardTitle class="text-lg">Results</CardTitle>
					<p class="text-muted-foreground text-sm">
						Query: <code class="font-mono">{result.query}</code> |
						Found: <Badge variant={result.count > 0 ? 'default' : 'secondary'}>{result.count}</Badge>
					</p>
				</div>
				{#if result.count > 0}
					<Button variant="outline" size="sm" onclick={copyAllResults}>
						<Copy class="mr-2 h-4 w-4" />
						Copy All
					</Button>
				{/if}
			</CardHeader>
			<CardContent>
				{#if result.count === 0}
					<p class="text-muted-foreground py-8 text-center">No records found for this SSN</p>
				{:else}
					<div class="overflow-x-auto">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead class="w-[120px]">SSN</TableHead>
									<TableHead>Name</TableHead>
									<TableHead>DOB</TableHead>
									<TableHead>Address</TableHead>
									<TableHead>Phone</TableHead>
									<TableHead>Email</TableHead>
									<TableHead class="w-[80px]">Source</TableHead>
									<TableHead class="w-[60px]"></TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each result.results as record, i}
									<TableRow>
										<TableCell class="font-mono text-sm">{record.ssn}</TableCell>
										<TableCell>
											<div class="space-y-0.5">
												<div class="font-medium">
													{record.firstname || ''} {record.middlename || ''} {record.lastname || ''}
												</div>
											</div>
										</TableCell>
										<TableCell class="text-sm">{formatDOB(record.dob || '', $dateFormat) || '-'}</TableCell>
										<TableCell>
											<div class="max-w-[200px] space-y-0.5 text-sm">
												<div>{record.address || '-'}</div>
												{#if record.city || record.state || record.zip}
													<div class="text-muted-foreground">
														{record.city || ''}{record.city && record.state ? ', ' : ''}{record.state || ''} {record.zip || ''}
													</div>
												{/if}
											</div>
										</TableCell>
										<TableCell class="font-mono text-sm">{record.phone || '-'}</TableCell>
										<TableCell class="max-w-[150px] truncate text-sm">{record.email || '-'}</TableCell>
										<TableCell>
											<Badge variant="outline" class="text-xs">{record.source_table || '-'}</Badge>
										</TableCell>
										<TableCell>
											<Button
												variant="ghost"
												size="icon"
												onclick={() => copyToClipboard(JSON.stringify(record, null, 2), `record-${i}`)}
											>
												{#if copiedId === `record-${i}`}
													<Check class="h-4 w-4 text-green-500" />
												{:else}
													<Copy class="h-4 w-4" />
												{/if}
											</Button>
										</TableCell>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					</div>
				{/if}
			</CardContent>
		</Card>
	{/if}
</div>
