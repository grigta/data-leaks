<script lang="ts">
	import { Table, TableHeader, TableHead, TableBody, TableRow, TableCell } from '$lib/components/ui/table';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import * as Select from '$lib/components/ui/select';
	import Search from '@lucide/svelte/icons/search';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Download from '@lucide/svelte/icons/download';
	import ChevronUp from '@lucide/svelte/icons/chevron-up';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import ChevronsUpDown from '@lucide/svelte/icons/chevrons-up-down';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Zap from '@lucide/svelte/icons/zap';
	import Home from '@lucide/svelte/icons/home';
	import Smartphone from '@lucide/svelte/icons/smartphone';
	import Server from '@lucide/svelte/icons/server';
	import { formatCurrency } from '$lib/utils';
	import type { ProxyDataItem } from '$lib/api/client';
	import { getCountryName } from '$lib/constants/countries';
	import {
		Pagination,
		PaginationContent,
		PaginationItem,
		PaginationPrevButton,
		PaginationNextButton
	} from '$lib/components/ui/pagination';

	let { data, loading = false, onRefresh }: {
		data: ProxyDataItem[];
		loading?: boolean;
		onRefresh?: () => void;
	} = $props();

	// State
	let searchQuery = $state('');
	let selectedCountry = $state<string | null>(null);
	let selectedState = $state<string | null>(null);
	let selectedCity = $state<string | null>(null);
	let selectedZip = $state<string | null>(null);
	let selectedType = $state<string | null>(null);
	let selectedSpeed = $state<string | null>(null);
	let sortColumn = $state<string | null>(null);
	let sortDirection = $state<'asc' | 'desc'>('asc');
	let currentPage = $state(0);
	let pageSize = $state(10);

	// Derived values
	let uniqueCountries = $derived.by(() => {
		const countries = new Set(data.map(item => item.country));
		return Array.from(countries).sort();
	});

	let uniqueStates = $derived.by(() => {
		let filtered = data;
		if (selectedCountry) {
			filtered = filtered.filter(item => item.country === selectedCountry);
		}
		const states = new Set(filtered.map(item => item.region));
		return Array.from(states).sort();
	});

	let uniqueCities = $derived.by(() => {
		let filtered = data;
		if (selectedCountry) {
			filtered = filtered.filter(item => item.country === selectedCountry);
		}
		if (selectedState) {
			filtered = filtered.filter(item => item.region === selectedState);
		}
		const cities = new Set(filtered.map(item => item.city));
		return Array.from(cities).sort();
	});

	let uniqueZips = $derived.by(() => {
		let filtered = data;
		if (selectedCountry) {
			filtered = filtered.filter(item => item.country === selectedCountry);
		}
		if (selectedState) {
			filtered = filtered.filter(item => item.region === selectedState);
		}
		if (selectedCity) {
			filtered = filtered.filter(item => item.city === selectedCity);
		}
		const zips = new Set(filtered.map(item => item.zip));
		return Array.from(zips).sort();
	});

	let filteredData = $derived.by(() => {
		let result = data;

		// Search filter
		if (searchQuery) {
			const query = searchQuery.toLowerCase();
			result = result.filter(item =>
				(item.proxy_ip || '').toLowerCase().includes(query) ||
				(item.city || '').toLowerCase().includes(query) ||
				(item.isp || '').toLowerCase().includes(query)
			);
		}

		// Country filter
		if (selectedCountry) {
			result = result.filter(item => item.country === selectedCountry);
		}

		// State filter
		if (selectedState) {
			result = result.filter(item => item.region === selectedState);
		}

		// City filter
		if (selectedCity) {
			result = result.filter(item => item.city === selectedCity);
		}

		// Zip filter
		if (selectedZip) {
			result = result.filter(item => item.zip === selectedZip);
		}

		// Type filter
		if (selectedType) {
			result = result.filter(item => item.type === selectedType);
		}

		// Speed filter
		if (selectedSpeed) {
			result = result.filter(item => item.speed === selectedSpeed);
		}

		return result;
	});

	let sortedData = $derived.by(() => {
		if (!sortColumn) return filteredData;

		return [...filteredData].sort((a, b) => {
			const aVal = a[sortColumn as keyof ProxyDataItem];
			const bVal = b[sortColumn as keyof ProxyDataItem];

			if (typeof aVal === 'string' && typeof bVal === 'string') {
				return sortDirection === 'asc'
					? aVal.localeCompare(bVal)
					: bVal.localeCompare(aVal);
			}

			if (typeof aVal === 'number' && typeof bVal === 'number') {
				return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
			}

			return 0;
		});
	});

	let paginatedData = $derived.by(() => {
		const start = currentPage * pageSize;
		const end = start + pageSize;
		return sortedData.slice(start, end);
	});

	let totalPages = $derived(Math.ceil(sortedData.length / pageSize));

	// Functions
	function handleSort(column: string) {
		if (sortColumn === column) {
			sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
		} else {
			sortColumn = column;
			sortDirection = 'asc';
		}
		currentPage = 0;
	}

	function getSortIcon(column: string) {
		if (sortColumn !== column) return ChevronsUpDown;
		return sortDirection === 'asc' ? ChevronUp : ChevronDown;
	}

	function handleRefresh() {
		if (onRefresh) onRefresh();
	}

	function escapeCSVValue(value: string | number): string {
		const str = String(value);
		// Экранируем двойные кавычки, заменяя " на ""
		const escaped = str.replace(/"/g, '""');
		// Оборачиваем значение в двойные кавычки
		return `"${escaped}"`;
	}

	function handleExport() {
		const headers = ['Proxy IP', 'Country', 'City', 'Region', 'ISP', 'Zip', 'Speed', 'Type', 'Price'];
		const rows = sortedData.map(item => [
			item.proxy_ip,
			item.country,
			item.city,
			item.region,
			item.isp,
			item.zip,
			item.speed,
			item.type,
			item.price.toString()
		]);

		const csv = [
			headers.map(h => escapeCSVValue(h)).join(','),
			...rows.map(row => row.map(val => escapeCSVValue(val)).join(','))
		].join('\n');

		const blob = new Blob([csv], { type: 'text/csv' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `proxy-data-${new Date().toISOString()}.csv`;
		a.click();
		URL.revokeObjectURL(url);
	}

	function clearFilters() {
		searchQuery = '';
		selectedCountry = null;
		selectedState = null;
		selectedCity = null;
		selectedZip = null;
		selectedType = null;
		selectedSpeed = null;
		currentPage = 0;
	}

	function goToPage(page: number) {
		if (page >= 0 && page < totalPages) {
			currentPage = page;
		}
	}
</script>

<div class="space-y-4">
	<!-- Filters Section -->
	<div class="flex flex-wrap gap-2">
		<!-- Search -->
		<div class="relative flex-1 min-w-[200px]">
			<Search class="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
			<Input
				type="text"
				placeholder="Search..."
				bind:value={searchQuery}
				class="pl-8"
			/>
		</div>

		<!-- Country Filter -->
		<Select.Root
			selected={selectedCountry ? { value: selectedCountry, label: getCountryName(selectedCountry) } : undefined}
			onSelectedChange={(v) => {
				selectedCountry = v?.value || null;
				selectedState = null;
				selectedCity = null;
				selectedZip = null;
			}}
		>
			<Select.Trigger class="w-[140px]">
				<Select.Value placeholder="Country" />
			</Select.Trigger>
			<Select.Content>
				{#each uniqueCountries as country}
					<Select.Item value={country}>{getCountryName(country)}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>

		<!-- State Filter -->
		<Select.Root
			selected={selectedState ? { value: selectedState, label: selectedState } : undefined}
			onSelectedChange={(v) => {
				selectedState = v?.value || null;
				selectedCity = null;
				selectedZip = null;
			}}
		>
			<Select.Trigger class="w-[140px]">
				<Select.Value placeholder="State" />
			</Select.Trigger>
			<Select.Content>
				{#each uniqueStates as state}
					<Select.Item value={state}>{state}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>

		<!-- City Filter -->
		<Select.Root
			selected={selectedCity ? { value: selectedCity, label: selectedCity } : undefined}
			onSelectedChange={(v) => {
				selectedCity = v?.value || null;
				selectedZip = null;
			}}
		>
			<Select.Trigger class="w-[140px]">
				<Select.Value placeholder="City" />
			</Select.Trigger>
			<Select.Content>
				{#each uniqueCities as city}
					<Select.Item value={city}>{city}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>

		<!-- ZIP Filter -->
		<Select.Root
			selected={selectedZip ? { value: selectedZip, label: selectedZip } : undefined}
			onSelectedChange={(v) => selectedZip = v?.value || null}
		>
			<Select.Trigger class="w-[120px]">
				<Select.Value placeholder="ZIP" />
			</Select.Trigger>
			<Select.Content>
				{#each uniqueZips as zip}
					<Select.Item value={zip}>{zip}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>

		<!-- Type Filter -->
		<Select.Root
			selected={selectedType ? { value: selectedType, label: selectedType } : undefined}
			onSelectedChange={(v) => selectedType = v?.value || null}
		>
			<Select.Trigger class="w-[140px]">
				<Select.Value placeholder="Type" />
			</Select.Trigger>
			<Select.Content>
				<Select.Item value="Residential">Residential</Select.Item>
				<Select.Item value="Mobile">Mobile</Select.Item>
				<Select.Item value="Hosting">Hosting</Select.Item>
			</Select.Content>
		</Select.Root>

		<!-- Speed Filter -->
		<Select.Root
			selected={selectedSpeed ? { value: selectedSpeed, label: selectedSpeed } : undefined}
			onSelectedChange={(v) => selectedSpeed = v?.value || null}
		>
			<Select.Trigger class="w-[130px]">
				<Select.Value placeholder="Speed" />
			</Select.Trigger>
			<Select.Content>
				<Select.Item value="Fast">Fast</Select.Item>
				<Select.Item value="Moderate">Moderate</Select.Item>
			</Select.Content>
		</Select.Root>

		<!-- Action Buttons -->
		<Button variant="outline" onclick={clearFilters}>
			Clear
		</Button>
		<Button variant="outline" onclick={handleRefresh}>
			<RefreshCw class="h-4 w-4" />
		</Button>
		<Button variant="outline" onclick={handleExport}>
			<Download class="h-4 w-4" />
		</Button>
	</div>

	<!-- Table -->
	<div class="rounded-md border">
		<Table>
			<TableHeader>
				<TableRow>
					<TableHead class="cursor-pointer" onclick={() => handleSort('proxy_ip')}>
						<div class="flex items-center gap-1">
							Proxy IP
							<svelte:component this={getSortIcon('proxy_ip')} class="h-4 w-4" />
						</div>
					</TableHead>
					<TableHead class="cursor-pointer" onclick={() => handleSort('country')}>
						<div class="flex items-center gap-1">
							Country
							<svelte:component this={getSortIcon('country')} class="h-4 w-4" />
						</div>
					</TableHead>
					<TableHead class="cursor-pointer" onclick={() => handleSort('city')}>
						<div class="flex items-center gap-1">
							City
							<svelte:component this={getSortIcon('city')} class="h-4 w-4" />
						</div>
					</TableHead>
					<TableHead class="cursor-pointer" onclick={() => handleSort('region')}>
						<div class="flex items-center gap-1">
							Region
							<svelte:component this={getSortIcon('region')} class="h-4 w-4" />
						</div>
					</TableHead>
					<TableHead class="cursor-pointer" onclick={() => handleSort('isp')}>
						<div class="flex items-center gap-1">
							ISP
							<svelte:component this={getSortIcon('isp')} class="h-4 w-4" />
						</div>
					</TableHead>
					<TableHead class="cursor-pointer" onclick={() => handleSort('zip')}>
						<div class="flex items-center gap-1">
							Zip
							<svelte:component this={getSortIcon('zip')} class="h-4 w-4" />
						</div>
					</TableHead>
					<TableHead class="cursor-pointer" onclick={() => handleSort('speed')}>
						<div class="flex items-center gap-1">
							Speed
							<svelte:component this={getSortIcon('speed')} class="h-4 w-4" />
						</div>
					</TableHead>
					<TableHead class="cursor-pointer" onclick={() => handleSort('type')}>
						<div class="flex items-center gap-1">
							Type
							<svelte:component this={getSortIcon('type')} class="h-4 w-4" />
						</div>
					</TableHead>
					<TableHead class="cursor-pointer" onclick={() => handleSort('price')}>
						<div class="flex items-center gap-1">
							Price
							<svelte:component this={getSortIcon('price')} class="h-4 w-4" />
						</div>
					</TableHead>
				</TableRow>
			</TableHeader>
			<TableBody>
				{#if loading}
					{#each Array(10) as _, i}
						<TableRow>
							{#each Array(9) as _}
								<TableCell>
									<Skeleton class="h-4 w-full" />
								</TableCell>
							{/each}
						</TableRow>
					{/each}
				{:else if paginatedData.length === 0}
					<TableRow>
						<TableCell colspan={9} class="h-24 text-center">
							No data found. Try adjusting filters.
						</TableCell>
					</TableRow>
				{:else}
					{#each paginatedData as item}
						<TableRow>
							<TableCell class="font-mono text-sm">{item.proxy_ip}</TableCell>
							<TableCell>{getCountryName(item.country)}</TableCell>
							<TableCell>{item.city}</TableCell>
							<TableCell>{item.region}</TableCell>
							<TableCell>{item.isp}</TableCell>
							<TableCell>{item.zip}</TableCell>
							<TableCell>
								{#if item.speed === 'Fast'}
									<Badge class="badge-success hover:bg-success/10">
										<Zap class="mr-1 h-3 w-3" />
										{item.speed}
									</Badge>
								{:else}
									<Badge class="badge-warning hover:bg-warning/10">
										{item.speed}
									</Badge>
								{/if}
							</TableCell>
							<TableCell>
								{#if item.type === 'Residential'}
									<Badge class="badge-info hover:bg-info/10">
										<Home class="mr-1 h-3 w-3" />
										{item.type}
									</Badge>
								{:else if item.type === 'Mobile'}
									<Badge class="bg-secondary/20 text-secondary-foreground hover:bg-secondary/20">
										<Smartphone class="mr-1 h-3 w-3" />
										{item.type}
									</Badge>
								{:else}
									<Badge variant="secondary">
										<Server class="mr-1 h-3 w-3" />
										{item.type}
									</Badge>
								{/if}
							</TableCell>
							<TableCell>{formatCurrency(item.price)}</TableCell>
						</TableRow>
					{/each}
				{/if}
			</TableBody>
		</Table>
	</div>

	<!-- Pagination -->
	{#if totalPages > 1 && !loading}
		<Pagination count={sortedData.length} perPage={pageSize}>
			<div class="flex items-center justify-between px-2 py-4">
				<div class="text-sm text-muted-foreground">
					Page {currentPage + 1} of {totalPages} ({sortedData.length} total items)
				</div>
				<PaginationContent>
					<PaginationItem>
						<PaginationPrevButton
							disabled={currentPage === 0}
							onclick={() => goToPage(currentPage - 1)}
						/>
					</PaginationItem>
					<PaginationItem>
						<PaginationNextButton
							disabled={currentPage >= totalPages - 1}
							onclick={() => goToPage(currentPage + 1)}
						/>
					</PaginationItem>
				</PaginationContent>
			</div>
		</Pagination>
	{/if}
</div>
