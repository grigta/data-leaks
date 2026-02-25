<script lang="ts">
	import { onMount } from 'svelte';
	import {
		debugFlowSearch,
		handleApiError,
		type DebugFlowResponse,
		type BloomKeyResult,
		type SearchKeyResult,
		type CandidateResult
	} from '$lib/api/client';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Badge } from '$lib/components/ui/badge';
	import { Tabs, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import Bug from '@lucide/svelte/icons/bug';
	import Search from '@lucide/svelte/icons/search';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import { toast } from 'svelte-sonner';
	import { user } from '$lib/stores/auth';
	import { goto } from '$app/navigation';

	// State
	let fullname = $state('');
	let address = $state('');
	let provider = $state<'searchbug'>('searchbug');  // whitepages temporarily disabled
	let isLoading = $state(false);
	let errorMessage = $state('');
	let result = $state<DebugFlowResponse | null>(null);
	let copiedKeys = $state<Set<string>>(new Set());

	// Collapsible sections
	let showSearchbugRaw = $state(false);
	let showAllCandidates = $state(false);
	let showNotFoundBloom = $state(false);
	let showNotMatchedKeys = $state(false);

	// Check admin access
	onMount(() => {
		if (!$user?.is_admin) {
			toast.error('Admin access required');
			goto('/dashboard');
		}
	});

	function parseName(input: string): { firstname: string; lastname: string } {
		const parts = input.trim().split(/\s+/);
		if (parts.length >= 3) {
			// firstname middlename lastname — middlename игнорируем (SearchBug найдёт сам)
			return { firstname: parts[0], lastname: parts[parts.length - 1] };
		} else if (parts.length === 2) {
			return { firstname: parts[0], lastname: parts[1] };
		}
		return { firstname: parts[0] || '', lastname: '' };
	}

	async function handleSearch() {
		const { firstname, lastname } = parseName(fullname);
		if (!firstname || !lastname || !address.trim()) {
			toast.error('Enter name (first last) and address');
			return;
		}

		isLoading = true;
		errorMessage = '';
		result = null;

		try {
			result = await debugFlowSearch({
				firstname,
				lastname,
				address: address.trim(),
				provider
			});
			toast.success(`Search completed. Found ${result.final_count} result(s)`);
		} catch (error) {
			errorMessage = handleApiError(error);
			toast.error(errorMessage);
		} finally {
			isLoading = false;
		}
	}

	async function copyToClipboard(data: any, label: string, key?: string) {
		try {
			const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
			await navigator.clipboard.writeText(text);
			toast.success(`${label} copied`);
			if (key) {
				copiedKeys.add(key);
				copiedKeys = new Set(copiedKeys);
				setTimeout(() => {
					copiedKeys.delete(key);
					copiedKeys = new Set(copiedKeys);
				}, 2000);
			}
		} catch (error) {
			toast.error('Failed to copy');
		}
	}

	function formatPhones(phones: any[]): string {
		if (!phones || phones.length === 0) return '-';
		return phones.map(p => typeof p === 'string' ? p : p.phone_number || p).join(', ');
	}

	function formatAddresses(addresses: any[]): string {
		if (!addresses || addresses.length === 0) return '-';
		return addresses.map(a => `${a.address || a.full_street} (${a.state})`).join('; ');
	}
</script>

<div class="container mx-auto max-w-7xl px-4 py-8 space-y-6">
	<!-- Header -->
	<div class="flex items-center gap-3">
		<div class="rounded-full bg-orange-100 p-2 dark:bg-orange-900/30">
			<Bug class="h-6 w-6 text-orange-600 dark:text-orange-400" />
		</div>
		<div>
			<h1 class="text-2xl font-bold">Debug Flow</h1>
			<p class="text-sm text-muted-foreground">Visualize the full two-level search flow</p>
		</div>
	</div>

	<!-- Search Form -->
	<Card>
		<CardContent class="pt-6 space-y-4">
			<!-- whitepages tab temporarily disabled -->
		<Tabs value={provider} onValueChange={(v) => { if (v) provider = v as 'searchbug'; }}>
				<TabsList>
					<TabsTrigger value="searchbug">SearchBug</TabsTrigger>
					<!-- <TabsTrigger value="whitepages">WhitePages</TabsTrigger> -->
				</TabsList>
			</Tabs>
			<form onsubmit={(e) => { e.preventDefault(); handleSearch(); }} class="flex gap-3 items-end">
				<div class="space-y-2 flex-1">
					<Label for="fullname">Name</Label>
					<Input
						id="fullname"
						type="text"
						bind:value={fullname}
						placeholder="Thomas Trapp  or  Thomas M Trapp"
						disabled={isLoading}
					/>
				</div>
				<div class="space-y-2 flex-1">
					<Label for="address">Address</Label>
					<Input
						id="address"
						type="text"
						bind:value={address}
						placeholder="3080 Demartini Rd"
						disabled={isLoading}
					/>
				</div>
				<Button type="submit" disabled={isLoading}>
					{#if isLoading}
						<Loader2 class="h-4 w-4 animate-spin" />
					{:else}
						<Search class="h-4 w-4" />
					{/if}
				</Button>
			</form>
		</CardContent>
	</Card>

	{#if errorMessage}
		<Alert variant="destructive">
			<AlertCircle class="h-4 w-4" />
			<AlertDescription>{errorMessage}</AlertDescription>
		</Alert>
	{/if}

	{#if result}
		<!-- Found Fullz (top) -->
		<Card>
			<CardHeader class="flex flex-row items-center justify-between pb-2">
				<CardTitle class="text-lg flex items-center gap-2">
					Found Fullz
					<Badge variant={result.final_count > 0 ? 'default' : 'secondary'} class={result.final_count > 0 ? 'bg-green-600' : ''}>
						{result.final_count}
					</Badge>
				</CardTitle>
				<Button
					variant="outline"
					size="sm"
					onclick={() => copyToClipboard(result.final_results, 'Found fullz', 'fullz')}
				>
					{#if copiedKeys.has('fullz')}
						<Check class="h-4 w-4" />
					{:else}
						<Copy class="h-4 w-4" />
					{/if}
				</Button>
			</CardHeader>
			<CardContent>
				{#if result.final_results.length === 0}
					<p class="text-sm text-muted-foreground">No fullz found matching all criteria</p>
				{:else}
					<div class="overflow-x-auto">
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead class="w-[40px]">#</TableHead>
									<TableHead>SSN</TableHead>
									<TableHead>Name</TableHead>
									<TableHead>DOB</TableHead>
									<TableHead>Address</TableHead>
									<TableHead>State</TableHead>
									<TableHead>Phone</TableHead>
									<TableHead>Source</TableHead>
									<TableHead class="w-[60px]">Keys</TableHead>
									<TableHead class="w-[80px]">Priority</TableHead>
									<TableHead>Matched Keys</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each result.final_results as fullz, i}
									<TableRow class={i === 0 ? 'bg-green-100 dark:bg-green-950/40 font-medium' : 'bg-green-50 dark:bg-green-950/20'}>
										<TableCell>
											{#if i === 0}
												<Badge class="bg-green-600">1</Badge>
											{:else}
												<span class="text-muted-foreground">{i + 1}</span>
											{/if}
										</TableCell>
										<TableCell class="font-mono font-medium">{fullz.ssn}</TableCell>
										<TableCell>{fullz.firstname} {fullz.lastname}</TableCell>
										<TableCell>{fullz.dob || '-'}</TableCell>
										<TableCell class="max-w-[200px] truncate" title="{fullz.address}, {fullz.city}">
											{fullz.address || '-'}
										</TableCell>
										<TableCell>{fullz.state || '-'}</TableCell>
										<TableCell class="font-mono text-sm">{fullz.phone || '-'}</TableCell>
										<TableCell>
											<Badge variant="outline">{fullz.source_table || '-'}</Badge>
										</TableCell>
										<TableCell>
											<Badge variant="secondary">{fullz.matched_keys_count}</Badge>
										</TableCell>
										<TableCell>
											{#if fullz.best_match_priority}
												<Badge variant={fullz.best_match_priority <= 4 ? 'default' : 'secondary'}
													class={fullz.best_match_priority <= 4 ? 'bg-green-600' : fullz.best_match_priority <= 8 ? 'bg-yellow-600' : ''}>
													P{fullz.best_match_priority}
												</Badge>
											{:else}
												<span class="text-muted-foreground">-</span>
											{/if}
										</TableCell>
										<TableCell>
											<div class="flex flex-wrap gap-1">
												{#each fullz.matched_keys.slice(0, 2) as key}
													<Badge variant="secondary" class="text-xs font-mono truncate max-w-[150px]" title={key}>
														{key.length > 20 ? key.slice(0, 20) + '...' : key}
													</Badge>
												{/each}
												{#if fullz.matched_keys.length > 2}
													<Badge variant="outline">+{fullz.matched_keys.length - 2}</Badge>
												{/if}
											</div>
										</TableCell>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					</div>
				{/if}
			</CardContent>
		</Card>

		<!-- 1. SearchBug Response -->
		<Card>
			<CardHeader class="flex flex-row items-center justify-between pb-2">
				<CardTitle class="text-lg flex items-center gap-2">
					<Badge variant="outline">1</Badge>
					{result.provider === 'whitepages' ? 'WhitePages' : 'SearchBug'} Response
				</CardTitle>
				<Button
					variant="outline"
					size="sm"
					onclick={() => copyToClipboard(result.searchbug_data, `${result.provider === 'whitepages' ? 'WhitePages' : 'SearchBug'} data`, 'searchbug')}
				>
					{#if copiedKeys.has('searchbug')}
						<Check class="h-4 w-4" />
					{:else}
						<Copy class="h-4 w-4" />
					{/if}
				</Button>
			</CardHeader>
			<CardContent class="space-y-4">
				<div class="overflow-x-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>Firstname</TableHead>
								<TableHead>Middlename</TableHead>
								<TableHead>Lastname</TableHead>
								<TableHead>DOB</TableHead>
								<TableHead>Address</TableHead>
								<TableHead>State</TableHead>
								<TableHead>Phone</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each (result.searchbug_data.names || []) as name, i}
								<TableRow>
									<TableCell class="font-medium">{name.first_name || result.searchbug_data.firstname || '-'}</TableCell>
									<TableCell>{name.middle_name || '-'}</TableCell>
									<TableCell class="font-medium">{name.last_name || result.searchbug_data.lastname || '-'}</TableCell>
									<TableCell>{i === 0 ? (result.searchbug_data.dob || '-') : ''}</TableCell>
									<TableCell class="text-xs">{result.searchbug_data.addresses?.[i]?.address || ''}</TableCell>
									<TableCell>{result.searchbug_data.addresses?.[i]?.state || ''}</TableCell>
									<TableCell class="font-mono text-xs">{result.searchbug_data.phones?.[i] || ''}</TableCell>
								</TableRow>
							{/each}
							{#if (result.searchbug_data.addresses?.length || 0) > (result.searchbug_data.names?.length || 0)}
								{#each result.searchbug_data.addresses.slice(result.searchbug_data.names?.length || 0) as addr}
									<TableRow>
										<TableCell></TableCell>
										<TableCell></TableCell>
										<TableCell></TableCell>
										<TableCell></TableCell>
										<TableCell class="text-xs">{addr.address || ''}</TableCell>
										<TableCell>{addr.state || ''}</TableCell>
										<TableCell></TableCell>
									</TableRow>
								{/each}
							{/if}
							{#if (result.searchbug_data.phones?.length || 0) > (result.searchbug_data.names?.length || 0)}
								{#each result.searchbug_data.phones.slice(result.searchbug_data.names?.length || 0) as phone}
									<TableRow>
										<TableCell></TableCell>
										<TableCell></TableCell>
										<TableCell></TableCell>
										<TableCell></TableCell>
										<TableCell></TableCell>
										<TableCell></TableCell>
										<TableCell class="font-mono text-xs">{phone}</TableCell>
									</TableRow>
								{/each}
							{/if}
						</TableBody>
					</Table>
				</div>

				<!-- Expandable raw data -->
				<div class="border-t pt-4">
					<button
						class="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
						onclick={() => showSearchbugRaw = !showSearchbugRaw}
					>
						{#if showSearchbugRaw}
							<ChevronDown class="h-4 w-4" />
						{:else}
							<ChevronRight class="h-4 w-4" />
						{/if}
						Show raw data
					</button>
					{#if showSearchbugRaw}
						<pre class="mt-2 p-3 bg-muted rounded text-xs overflow-x-auto max-h-64">{JSON.stringify(result.searchbug_data, null, 2)}</pre>
					{/if}
				</div>
			</CardContent>
		</Card>

		<!-- 2. Bloom Keys (Level 1) -->
		{@const allBloom = [...result.bloom_keys_phone, ...result.bloom_keys_address]}
		{@const foundBloom = allBloom.filter(b => b.found_in_db)}
		{@const notFoundBloom = allBloom.filter(b => !b.found_in_db)}
		<Card>
			<CardHeader class="flex flex-row items-center justify-between pb-2">
				<CardTitle class="text-lg flex items-center gap-2">
					<Badge variant="outline">2</Badge>
					Bloom Keys (Level 1)
					<Badge variant="secondary">{result.level1_candidates_count} candidates</Badge>
					{#if foundBloom.length > 0}
						<Badge class="bg-green-600">{foundBloom.length} found</Badge>
					{/if}
				</CardTitle>
				<Button
					variant="outline"
					size="sm"
					onclick={() => copyToClipboard(allBloom, 'Bloom keys', 'bloom')}
				>
					{#if copiedKeys.has('bloom')}
						<Check class="h-4 w-4" />
					{:else}
						<Copy class="h-4 w-4" />
					{/if}
				</Button>
			</CardHeader>
			<CardContent>
				{#if allBloom.length === 0}
					<p class="text-sm text-muted-foreground">No bloom keys generated</p>
				{:else}
					{#if foundBloom.length > 0}
						<div class="flex items-center justify-between mb-2">
							<span class="text-sm text-muted-foreground">{foundBloom.length} found</span>
							<Button
								variant="outline"
								size="sm"
								onclick={() => copyToClipboard(foundBloom, 'Found bloom keys', 'bloom-found')}
							>
								{#if copiedKeys.has('bloom-found')}
									<Check class="h-3 w-3" />
								{:else}
									<Copy class="h-3 w-3" />
								{/if}
							</Button>
						</div>
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Key</TableHead>
									<TableHead class="w-[100px]">Type</TableHead>
									<TableHead class="w-[80px]">Found</TableHead>
									<TableHead class="w-[100px]">Candidates</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each foundBloom as bk}
									<TableRow class="bg-green-50 dark:bg-green-950/20">
										<TableCell class="font-mono text-xs break-all">{bk.key}</TableCell>
										<TableCell>
											<Badge variant="outline">{bk.type}</Badge>
										</TableCell>
										<TableCell>
											<span class="text-green-600 font-medium">YES</span>
										</TableCell>
										<TableCell>{bk.candidates_count}</TableCell>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					{:else}
						<p class="text-sm text-muted-foreground">No bloom keys found in DB</p>
					{/if}

					{#if notFoundBloom.length > 0}
						<div class="border-t pt-3 mt-3">
							<div class="flex items-center justify-between">
								<button
									class="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
									onclick={() => showNotFoundBloom = !showNotFoundBloom}
								>
									{#if showNotFoundBloom}
										<ChevronDown class="h-4 w-4" />
									{:else}
										<ChevronRight class="h-4 w-4" />
									{/if}
									{notFoundBloom.length} not found
								</button>
								<Button
									variant="outline"
									size="sm"
									onclick={() => copyToClipboard(notFoundBloom, 'Not found bloom keys', 'bloom-notfound')}
								>
									{#if copiedKeys.has('bloom-notfound')}
										<Check class="h-3 w-3" />
									{:else}
										<Copy class="h-3 w-3" />
									{/if}
								</Button>
							</div>
							{#if showNotFoundBloom}
								<Table class="mt-2">
									<TableHeader>
										<TableRow>
											<TableHead>Key</TableHead>
											<TableHead class="w-[100px]">Type</TableHead>
											<TableHead class="w-[80px]">Found</TableHead>
											<TableHead class="w-[100px]">Candidates</TableHead>
										</TableRow>
									</TableHeader>
									<TableBody>
										{#each notFoundBloom as bk}
											<TableRow>
												<TableCell class="font-mono text-xs break-all">{bk.key}</TableCell>
												<TableCell>
													<Badge variant="outline">{bk.type}</Badge>
												</TableCell>
												<TableCell>
													<span class="text-muted-foreground">no</span>
												</TableCell>
												<TableCell>0</TableCell>
											</TableRow>
										{/each}
									</TableBody>
								</Table>
							{/if}
						</div>
					{/if}
				{/if}
			</CardContent>
		</Card>

		<!-- 3. Search Keys (Level 2) -->
		{@const matchedKeys = result.query_keys.filter(sk => sk.matched)}
		{@const notMatchedKeys = result.query_keys.filter(sk => !sk.matched)}
		<Card>
			<CardHeader class="flex flex-row items-center justify-between pb-2">
				<CardTitle class="text-lg flex items-center gap-2">
					<Badge variant="outline">3</Badge>
					Search Keys (Level 2)
					<Badge variant="secondary">MN={result.searchbug_mn || '-'}</Badge>
					<Badge variant="secondary">DOB_YEAR={result.searchbug_dob_year || '-'}</Badge>
					{#if matchedKeys.length > 0}
						<Badge class="bg-green-600">{matchedKeys.length} matched</Badge>
					{/if}
				</CardTitle>
				<Button
					variant="outline"
					size="sm"
					onclick={() => copyToClipboard(result.query_keys, 'Search keys', 'search')}
				>
					{#if copiedKeys.has('search')}
						<Check class="h-4 w-4" />
					{:else}
						<Copy class="h-4 w-4" />
					{/if}
				</Button>
			</CardHeader>
			<CardContent>
				{#if result.query_keys.length === 0}
					<p class="text-sm text-muted-foreground">No search keys generated</p>
				{:else}
					{#if matchedKeys.length > 0}
						<div class="flex items-center justify-between mb-2">
							<span class="text-sm text-muted-foreground">{matchedKeys.length} matched</span>
							<Button
								variant="outline"
								size="sm"
								onclick={() => copyToClipboard(matchedKeys, 'Matched search keys', 'search-matched')}
							>
								{#if copiedKeys.has('search-matched')}
									<Check class="h-3 w-3" />
								{:else}
									<Copy class="h-3 w-3" />
								{/if}
							</Button>
						</div>
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Key</TableHead>
									<TableHead class="w-[100px]">Method</TableHead>
									<TableHead class="w-[80px]">Matched</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{#each matchedKeys as sk}
									<TableRow class="bg-green-50 dark:bg-green-950/20">
										<TableCell class="font-mono text-xs break-all">{sk.key}</TableCell>
										<TableCell>
											<Badge variant="outline">{sk.key_type}</Badge>
										</TableCell>
										<TableCell>
											<span class="text-green-600 font-medium">YES</span>
										</TableCell>
									</TableRow>
								{/each}
							</TableBody>
						</Table>
					{:else}
						<p class="text-sm text-muted-foreground">No search keys matched</p>
					{/if}

					{#if notMatchedKeys.length > 0}
						<div class="border-t pt-3 mt-3">
							<div class="flex items-center justify-between">
								<button
									class="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
									onclick={() => showNotMatchedKeys = !showNotMatchedKeys}
								>
									{#if showNotMatchedKeys}
										<ChevronDown class="h-4 w-4" />
									{:else}
										<ChevronRight class="h-4 w-4" />
									{/if}
									{notMatchedKeys.length} not matched
								</button>
								<Button
									variant="outline"
									size="sm"
									onclick={() => copyToClipboard(notMatchedKeys, 'Not matched search keys', 'search-notmatched')}
								>
									{#if copiedKeys.has('search-notmatched')}
										<Check class="h-3 w-3" />
									{:else}
										<Copy class="h-3 w-3" />
									{/if}
								</Button>
							</div>
							{#if showNotMatchedKeys}
								<Table class="mt-2">
									<TableHeader>
										<TableRow>
											<TableHead>Key</TableHead>
											<TableHead class="w-[100px]">Method</TableHead>
											<TableHead class="w-[80px]">Matched</TableHead>
										</TableRow>
									</TableHeader>
									<TableBody>
										{#each notMatchedKeys as sk}
											<TableRow>
												<TableCell class="font-mono text-xs break-all">{sk.key}</TableCell>
												<TableCell>
													<Badge variant="outline">{sk.key_type}</Badge>
												</TableCell>
												<TableCell>
													<span class="text-muted-foreground">no</span>
												</TableCell>
											</TableRow>
										{/each}
									</TableBody>
								</Table>
							{/if}
						</div>
					{/if}
				{/if}
			</CardContent>
		</Card>

		<!-- 4. All Candidates (Expandable) -->
		{#if result.candidates_with_keys.length > 0}
			<Card>
				<CardHeader class="flex flex-row items-center justify-between pb-2">
					<button
						class="flex items-center gap-2"
						onclick={() => showAllCandidates = !showAllCandidates}
					>
						{#if showAllCandidates}
							<ChevronDown class="h-4 w-4" />
						{:else}
							<ChevronRight class="h-4 w-4" />
						{/if}
						<CardTitle class="text-lg flex items-center gap-2">
							<Badge variant="outline">3.5</Badge>
							All Candidates
							<Badge variant="secondary">{result.candidates_with_keys.length} total</Badge>
						</CardTitle>
					</button>
					<Button
						variant="outline"
						size="sm"
						onclick={() => copyToClipboard(result.candidates_with_keys, 'All candidates', 'candidates')}
					>
						{#if copiedKeys.has('candidates')}
							<Check class="h-4 w-4" />
						{:else}
							<Copy class="h-4 w-4" />
						{/if}
					</Button>
				</CardHeader>
				{#if showAllCandidates}
					<CardContent>
						<div class="overflow-x-auto">
							<Table>
								<TableHeader>
									<TableRow>
										<TableHead>SSN</TableHead>
										<TableHead>Name</TableHead>
										<TableHead>DOB</TableHead>
										<TableHead>Address</TableHead>
										<TableHead>Phone</TableHead>
										<TableHead>Source</TableHead>
										<TableHead>Matched Keys</TableHead>
									</TableRow>
								</TableHeader>
								<TableBody>
									{#each result.candidates_with_keys as c}
										<TableRow class={c.matched_keys.length > 0 ? 'bg-green-50 dark:bg-green-950/20' : ''}>
											<TableCell class="font-mono text-xs">{c.ssn}</TableCell>
											<TableCell class="text-xs">{c.firstname} {c.lastname}</TableCell>
											<TableCell class="text-xs">{c.dob || '-'}</TableCell>
											<TableCell class="text-xs max-w-[200px] truncate" title="{c.address}, {c.city}, {c.state}">
												{c.address || '-'}
											</TableCell>
											<TableCell class="font-mono text-xs">{c.phone || '-'}</TableCell>
											<TableCell class="text-xs">{c.source_table || '-'}</TableCell>
											<TableCell class="text-xs">
												{#if c.matched_keys.length > 0}
													<Badge variant="default" class="bg-green-600">{c.matched_keys.length}</Badge>
												{:else}
													<span class="text-muted-foreground">0</span>
												{/if}
											</TableCell>
										</TableRow>
									{/each}
								</TableBody>
							</Table>
						</div>
					</CardContent>
				{/if}
			</Card>
		{/if}

	{/if}
</div>
