<script lang="ts">
	import { dev } from '$app/environment';
	import { onMount } from 'svelte';
	import {
		getPhoneLookupServices,
		phoneLookupSearch,
		getPhoneRentals,
		type DaisySMSService,
		type PhoneLookupResponse,
		type PhoneRentalResponse,
		handleApiError
	} from '$lib/api/client';
	import { refreshUser } from '$lib/stores/auth';
	import { t } from '$lib/i18n';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Label } from '$lib/components/ui/label';
	import { Input } from '$lib/components/ui/input';
	import { toast } from 'svelte-sonner';
	import Search from '@lucide/svelte/icons/search';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Phone from '@lucide/svelte/icons/phone';
	import History from '@lucide/svelte/icons/history';
	import PhoneLookupResultModal from '$lib/components/PhoneLookupResultModal.svelte';
	import PhoneLookupHistoryModal from '$lib/components/PhoneLookupHistoryModal.svelte';

	// State
	let services = $state<DaisySMSService[]>([]);
	let selectedService = $state<string>('');
	let isLoadingServices = $state(true);
	let isSearching = $state(false);
	let errorMessage = $state('');
	let searchResponse = $state<PhoneLookupResponse | null>(null);
	let showResultModal = $state(false);
	let showHistoryModal = $state(false);
	let rentals = $state<PhoneRentalResponse[]>([]);
	let isLoadingRentals = $state(false);
	let searchQuery = $state('');
	let isDropdownOpen = $state(false);
	let dropdownContainerRef: HTMLDivElement | null = $state(null);

	// Handle click outside to close dropdown
	function handleClickOutside(event: MouseEvent) {
		if (dropdownContainerRef && !dropdownContainerRef.contains(event.target as Node)) {
			isDropdownOpen = false;
		}
	}

	// Filtered services based on search query
	const filteredServices = $derived(
		searchQuery
			? services.filter(
					(s) =>
						s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
						s.code.toLowerCase().includes(searchQuery.toLowerCase())
				)
			: services
	);

	async function loadServices() {
		try {
			isLoadingServices = true;
			const response = await getPhoneLookupServices();
			// Filter out potential metadata fields that shouldn't appear in the list
			const metadataFields = new Set(['count', 'total', 'status', 'error', 'message']);
			services = response.services.filter(
				(s) => s.code && s.name && !metadataFields.has(s.code.toLowerCase())
			);
			dev && console.log('[PHONE-LOOKUP] Loaded services:', services.length);
		} catch (error: any) {
			console.error('[PHONE-LOOKUP] Error loading services:', error);
			errorMessage = handleApiError(error);
		} finally {
			isLoadingServices = false;
		}
	}

	async function loadRentals() {
		try {
			isLoadingRentals = true;
			const response = await getPhoneRentals({ limit: 50 });
			rentals = response.rentals;
			dev && console.log('[PHONE-LOOKUP] Loaded rentals:', rentals.length);
		} catch (error: any) {
			console.error('[PHONE-LOOKUP] Error loading rentals:', error);
			toast.error(handleApiError(error));
		} finally {
			isLoadingRentals = false;
		}
	}

	async function handleSearch() {
		if (!selectedService) {
			errorMessage = $t('phone-lookup.selectService');
			return;
		}

		errorMessage = '';
		isSearching = true;
		searchResponse = null;

		try {
			const response = await phoneLookupSearch(selectedService);
			searchResponse = response;

			dev && console.log('[PHONE-LOOKUP] Search response:', response);

			// Update user balance if new_balance is provided
			if (response.new_balance !== undefined) {
				await refreshUser();
				dev && console.log('[PHONE-LOOKUP] Balance updated:', response.new_balance);
			}

			if (response.success) {
				showResultModal = true;
				// Reset selection after successful search
				selectedService = '';
				searchQuery = '';
			} else {
				// Show error
				errorMessage = response.message || $t('phone-lookup.errorNoMatches');
			}
		} catch (error: any) {
			console.error('[PHONE-LOOKUP] Search error:', error);
			errorMessage = handleApiError(error);
		} finally {
			isSearching = false;
		}
	}

	function openHistory() {
		loadRentals();
		showHistoryModal = true;
	}

	onMount(() => {
		loadServices();
	});
</script>

<svelte:head>
	<title>{$t('phone-lookup.title')}</title>
</svelte:head>

<svelte:window onclick={handleClickOutside} />

<PhoneLookupResultModal
	open={showResultModal}
	response={searchResponse}
	onClose={() => {
		showResultModal = false;
		searchResponse = null;
	}}
/>

<PhoneLookupHistoryModal
	open={showHistoryModal}
	{rentals}
	isLoading={isLoadingRentals}
	onClose={() => {
		showHistoryModal = false;
	}}
	onRefresh={loadRentals}
/>

<div class="mx-auto py-8 px-4 max-w-[1400px] w-full">
	{#if isLoadingServices}
		<div class="flex justify-center items-center py-12">
			<Loader2 class="h-8 w-8 animate-spin" />
		</div>
	{:else}
		<Card>
			<CardHeader class="text-center">
				<CardTitle class="text-2xl flex items-center justify-center gap-2">
					<Phone class="h-6 w-6" />
					{$t('phone-lookup.title')}
				</CardTitle>
			</CardHeader>
			<CardContent>
				{#if errorMessage}
					<Alert variant="destructive" class="mb-6">
						<AlertCircle class="h-4 w-4" />
						<AlertDescription>{errorMessage}</AlertDescription>
					</Alert>
				{/if}

				<div class="space-y-6">
					<!-- Service Selection -->
					<div class="space-y-2" bind:this={dropdownContainerRef}>
						<Label for="service-search" class="text-sm font-medium">{$t('phone-lookup.selectService')} *</Label>
						<div class="relative">
							<Input
								id="service-search"
								type="text"
								bind:value={searchQuery}
								placeholder={$t('phone-lookup.searchServices')}
								onfocus={() => isDropdownOpen = true}
							/>
						</div>

						{#if isDropdownOpen || selectedService}
							<div class="border border-border rounded-md max-h-64 overflow-y-auto bg-popover">
								{#each filteredServices as service}
									<button
										type="button"
										class="w-full px-4 py-3 text-left transition-colors flex items-center justify-between border-b last:border-b-0 bg-background hover:bg-accent hover:text-accent-foreground {selectedService === service.code ? 'bg-accent text-accent-foreground' : 'text-foreground'}"
										onpointerdown={() => {
											selectedService = service.code;
											searchQuery = service.name;
											isDropdownOpen = false;
										}}
									>
										<span class="font-medium">{service.name}</span>
										<span class="text-xs text-muted-foreground">{service.code}</span>
									</button>
								{:else}
									<div class="px-4 py-3 text-center text-muted-foreground bg-background">{$t('phone-lookup.noServicesFound')}</div>
								{/each}
							</div>
						{:else}
							<p class="text-sm text-muted-foreground">
								{$t('phone-lookup.typeToSearch')}
							</p>
						{/if}
					</div>

					<!-- Info -->
					<div class="bg-muted/50 rounded-lg p-4 space-y-2">
						<p class="text-sm">
							<strong>{$t('phone-lookup.cost')}:</strong> {$t('phone-lookup.costDescription')}
						</p>
						<p class="text-xs text-muted-foreground">
							{$t('phone-lookup.costHint')}
						</p>
					</div>

					<!-- Actions -->
					<div class="flex flex-col sm:flex-row gap-4 justify-center">
						<Button
							size="lg"
							class="min-w-[200px]"
							disabled={isSearching || !selectedService}
							onclick={handleSearch}
						>
							{#if isSearching}
								<Loader2 class="mr-2 h-5 w-5 animate-spin" />
								{$t('phone-lookup.searching')}
							{:else}
								<Search class="mr-2 h-5 w-5" />
								{$t('phone-lookup.search')}
							{/if}
						</Button>

						<Button variant="outline" size="lg" class="min-w-[200px]" onclick={openHistory}>
							<History class="mr-2 h-5 w-5" />
							{$t('phone-lookup.viewHistory')}
						</Button>
					</div>
				</div>
			</CardContent>
		</Card>
	{/if}
</div>
