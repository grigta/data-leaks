<script lang="ts">
	import { dev } from '$app/environment';
	import { z } from 'zod';
	import { instantSSNSearch, type InstantSSNResult, type InstantSSNResponse, handleApiError, getCurrentUser, acceptInstantSSNRules, createManualSSNTicket, getMaintenanceStatus } from '$lib/api/client';
	import { parseFullName } from '$lib/utils';
	import { refreshUser } from '$lib/stores/auth';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Label } from '$lib/components/ui/label';
	import { t } from '$lib/i18n';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import Search from '@lucide/svelte/icons/search';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import CheckCircle from '@lucide/svelte/icons/check-circle';
	import XCircle from '@lucide/svelte/icons/x-circle';
	import Send from '@lucide/svelte/icons/send';
	import Eye from '@lucide/svelte/icons/eye';
	import Wrench from '@lucide/svelte/icons/wrench';
	import InstantSSNRulesModal from '$lib/components/InstantSSNRulesModal.svelte';
	import InstantSSNResultModal from '$lib/components/InstantSSNResultModal.svelte';
	import InstantSSNFoundModal from '$lib/components/InstantSSNFoundModal.svelte';
	import InstantSSNNotFoundModal from '$lib/components/InstantSSNNotFoundModal.svelte';
	import { loadUnviewedTicketsCount } from '$lib/stores/tickets';
	import { onMount } from 'svelte';

	const lookupSchema = z.object({
		fullname: z.string().min(1, 'Full name is required'),
		address: z.string().min(1, 'Address is required')
	});

	let searchResults = $state<InstantSSNResult[]>([]);
	let isSearching = $state(false);
	let errorMessage = $state('');
	let hasSearched = $state(false);
	let responseMessage = $state('');
	let showRulesModal = $state(false);
	let currentUser = $state<any>(null);
	let isCheckingRules = $state(true);
	let banErrorMessage = $state('');
	let selectedResult = $state<InstantSSNResult | null>(null);
	let showResultModal = $state(false);
	let isSendingToManual = $state(false);
	let isMaintenanceMode = $state(false);
	let maintenanceMessage = $state<string | null>(null);
	let isCheckingMaintenance = $state(true);
	let showFoundModal = $state(false);
	let showNotFoundModal = $state(false);
	let currentSearchData = $state<{ firstname: string; lastname: string; address: string } | null>(null);

	const form = $state({
		fullname: '',
		address: ''
	});

	const errors = $state<{
		fullname?: string[];
		address?: string[];
	}>({});

	function clearForm() {
		form.fullname = '';
		form.address = '';
		errors.fullname = undefined;
		errors.address = undefined;
		errorMessage = '';
		responseMessage = '';
	}

	async function checkMaintenanceMode() {
		try {
			const status = await getMaintenanceStatus('instant_ssn');
			isMaintenanceMode = status.is_active;
			maintenanceMessage = status.message || null;
			isCheckingMaintenance = false;
		} catch (error: any) {
			console.error('[INSTANT-SSN] Error checking maintenance mode:', error);
			// On error, assume not in maintenance
			isMaintenanceMode = false;
			isCheckingMaintenance = false;
		}
	}

	async function checkFirstVisit() {
		try {
			const user = await getCurrentUser();
			currentUser = user;

			// Check if user is banned
			if (user.is_banned) {
				banErrorMessage = 'Your account has been banned for abuse. You cannot use Instant SSN Search.';
				isCheckingRules = false;
				return;
			}

			// Check if rules accepted
			if (!user.instant_ssn_rules_accepted) {
				showRulesModal = true;
			}

			isCheckingRules = false;
		} catch (error: any) {
			console.error('[INSTANT-SSN] Error checking user:', error);
			errorMessage = handleApiError(error);
			isCheckingRules = false;
		}
	}

	async function handleAcceptRules() {
		try {
			await acceptInstantSSNRules();
			showRulesModal = false;
			if (currentUser) {
				currentUser.instant_ssn_rules_accepted = true;
			}
		} catch (error: any) {
			console.error('[INSTANT-SSN] Error accepting rules:', error);
			errorMessage = handleApiError(error);
		}
	}

	async function handleSubmit(e: Event) {
		e.preventDefault();

		// Check if rules are accepted before submitting
		if (!currentUser?.instant_ssn_rules_accepted) {
			errorMessage = 'Please accept the Instant SSN Rules before searching.';
			showRulesModal = true;
			return;
		}

		// Clear previous errors
		errors.fullname = undefined;
		errors.address = undefined;

		// Validate
		const result = lookupSchema.safeParse(form);
		if (!result.success) {
			const fieldErrors = result.error.flatten().fieldErrors;
			errors.fullname = fieldErrors.fullname;
			errors.address = fieldErrors.address;
			return;
		}

		// Parse full name into firstname and lastname
		const { firstname, lastname } = parseFullName(form.fullname);

		// Validate that we got both firstname and lastname
		if (!firstname || !lastname) {
			errors.fullname = ['Please enter both first and last name (e.g., "John Doe")'];
			return;
		}

		// Execute search immediately
		errorMessage = '';
		responseMessage = '';
		isSearching = true;
		searchResults = [];
		hasSearched = false;

		try {
			const response: InstantSSNResponse = await instantSSNSearch({
				firstname: firstname,
				lastname: lastname,
				address: form.address
			});

			searchResults = response.results;
			hasSearched = true;
			responseMessage = response.message || '';

			// Store search parameters for modals
			currentSearchData = { firstname, lastname, address: form.address };

			// Update user balance if new_balance is provided
			if (response.new_balance !== undefined) {
				await refreshUser();
				dev && console.log('[INSTANT-SSN] Balance updated:', response.new_balance);
			}

			// Auto-open appropriate modal based on results
			// Проверяем, найден ли SSN (не просто есть ли результаты)
			const hasSSN = response.results.length > 0 && response.results[0].ssn_found;

			if (hasSSN) {
				selectedResult = response.results[0];
				showFoundModal = true;
				clearForm();
			} else {
				// SSN не найден - показать модалку с предложением отправить на ручной пробив
				showNotFoundModal = true;
				clearForm();
			}

			dev && console.log('[INSTANT-SSN] Response:', response);
			dev && console.log('[INSTANT-SSN] Parsed name:', { firstname, lastname });
			dev && console.log('[INSTANT-SSN] New balance:', response.new_balance);
		} catch (error: any) {
			console.error('[INSTANT-SSN] Search error');

			// Check for 403 ban error
			if (error.response?.status === 403) {
				banErrorMessage = error.response?.data?.detail || 'Your account has been banned for abuse.';
				if (currentUser) {
					currentUser.is_banned = true;
				}
			}

			errorMessage = handleApiError(error);
		} finally {
			isSearching = false;
		}
	}

	onMount(() => {
		checkMaintenanceMode();
		checkFirstVisit();
	});

	async function handleSendToManualSearch() {
		// Validate form data
		if (!form.fullname || !form.address) {
			toast.error('Please enter both full name and address before sending to manual search.');
			return;
		}

		// Parse full name
		const { firstname, lastname } = parseFullName(form.fullname);

		if (!firstname || !lastname) {
			toast.error('Please enter both first and last name (e.g., "John Doe")');
			return;
		}

		// Update currentSearchData to ensure consistency
		currentSearchData = { firstname, lastname, address: form.address };

		isSendingToManual = true;

		try {
			const response = await createManualSSNTicket({
				firstname: firstname,
				lastname: lastname,
				address: form.address
			});

			toast.success('Успешно отправлено на ручной пробив');

			// Ask if user wants to navigate to manual SSN page
			setTimeout(() => {
				const navigate = confirm('Would you like to go to the Manual SSN page to track your request?');
				if (navigate) {
					goto('/manual-ssn');
				}
			}, 1000);
		} catch (error: any) {
			console.error('[MANUAL-SSN] Error creating ticket:', error);
			toast.error(handleApiError(error));
		} finally {
			isSendingToManual = false;
		}
	}

	function handleViewDetails(result: InstantSSNResult) {
		selectedResult = result;
		showResultModal = true;
	}

	async function handleSendToManualFromModal() {
		if (!currentSearchData) {
			toast.error('No search data available.');
			return;
		}

		try {
			const response = await createManualSSNTicket({
				firstname: currentSearchData.firstname,
				lastname: currentSearchData.lastname,
				address: currentSearchData.address
			});

			toast.success('Успешно отправлено на ручной пробив');
			showNotFoundModal = false;

			// Reload unviewed tickets count
			await loadUnviewedTicketsCount();
		} catch (error: any) {
			console.error('[MANUAL-SSN] Error creating ticket:', error);
			toast.error(handleApiError(error));
			throw error; // Re-throw to keep modal open
		}
	}
</script>

<InstantSSNRulesModal
	open={showRulesModal}
	onAccept={handleAcceptRules}
/>

<InstantSSNResultModal
	open={showResultModal}
	result={selectedResult}
	onClose={() => { showResultModal = false; selectedResult = null; }}
/>

<InstantSSNFoundModal
	open={showFoundModal}
	result={selectedResult}
	onClose={() => { showFoundModal = false; selectedResult = null; }}
/>

<InstantSSNNotFoundModal
	open={showNotFoundModal}
	searchData={currentSearchData || { firstname: '', lastname: '', address: '' }}
	onClose={() => { showNotFoundModal = false; }}
	onSendToManual={handleSendToManualFromModal}
/>

<div class="mx-auto py-8 px-4 max-w-[1400px] w-full">
	{#if isCheckingMaintenance || isCheckingRules}
		<div class="flex justify-center items-center py-12">
			<Loader2 class="h-8 w-8 animate-spin" />
		</div>
	{:else if isMaintenanceMode}
		<Card>
			<CardHeader class="text-center">
				<CardTitle class="text-2xl">Instant SSN Search</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="flex flex-col items-center justify-center py-12 gap-6">
					<div class="rounded-full bg-orange-100 p-6">
						<Wrench class="h-16 w-16 text-orange-600" />
					</div>
					<div class="text-center space-y-3 max-w-md">
						<h3 class="text-2xl font-semibold">Технические работы</h3>
						<p class="text-lg text-muted-foreground">
							{maintenanceMessage || 'Сервис временно недоступен из-за проведения технических работ. Пожалуйста, попробуйте позже.'}
						</p>
					</div>
				</div>
			</CardContent>
		</Card>
	{:else}
		<Card>
			<CardHeader class="text-center">
				<CardTitle class="text-2xl">Instant SSN Search</CardTitle>
			</CardHeader>
			<CardContent>
				{#if banErrorMessage}
					<Alert variant="destructive" class="mb-6">
						<AlertCircle class="h-4 w-4" />
						<AlertDescription>{banErrorMessage}</AlertDescription>
					</Alert>
				{/if}

				<form onsubmit={handleSubmit} class="space-y-6">
					{#if errorMessage}
						<Alert variant="destructive">
							<AlertCircle class="h-4 w-4" />
						<AlertDescription>{errorMessage}</AlertDescription>
					</Alert>
				{/if}

				{#if responseMessage && hasSearched}
					<Alert variant="default">
						<AlertDescription>{responseMessage}</AlertDescription>
					</Alert>
				{/if}

				<div class="flex items-start gap-4">
					<div class="flex-1 grid gap-4" style="grid-template-columns: repeat(2, minmax(0, 1fr));">
						<!-- Full Name -->
						<div class="space-y-2">
							<Label for="fullname" class="text-sm font-medium">Full Name *</Label>
							<Input
								id="fullname"
								name="fullname"
								bind:value={form.fullname}
								placeholder="John Doe"
								class="text-base h-11"
								autocomplete="name"
								disabled={currentUser?.is_banned}
							/>
							{#if errors.fullname}
								<p class="text-xs text-red-500">{errors.fullname[0]}</p>
							{/if}
						</div>

						<!-- Address -->
						<div class="space-y-2">
							<Label for="address" class="text-sm font-medium">Address *</Label>
							<Input
								id="address"
								name="address"
								bind:value={form.address}
								placeholder="123 Main St"
								class="text-base h-11"
								autocomplete="street-address"
								disabled={currentUser?.is_banned}
							/>
							{#if errors.address}
								<p class="text-xs text-red-500">{errors.address[0]}</p>
							{/if}
						</div>
					</div>

					<!-- Clear Button -->
					<Button
						type="button"
						variant="ghost"
						size="icon"
						class="h-11 w-11 shrink-0 mt-[30px]"
						onclick={clearForm}
						title="Clear form"
					>
						<Trash2 class="h-5 w-5" />
					</Button>
				</div>

				<div class="space-y-1">
					<p class="text-sm text-muted-foreground">* Required fields.</p>
					<p class="text-xs text-muted-foreground">Enter first and last name (middle name will be ignored)</p>
				</div>

				<!-- Search Button -->
				<div class="mt-6 flex justify-center">
					<Button type="submit" size="lg" class="min-w-[200px]" disabled={isSearching || showRulesModal || currentUser?.is_banned}>
						{#if isSearching}
							<Loader2 class="mr-2 h-5 w-5 animate-spin" />
							Searching...
						{:else}
							<Search class="mr-2 h-5 w-5" />
							Search
						{/if}
					</Button>
				</div>
			</form>
		</CardContent>
	</Card>

	{#if hasSearched && searchResults.length > 0}
		<div class="mt-8 space-y-4">
			{#each searchResults as result, index}
				<Card class="hover:shadow-md transition-shadow cursor-pointer">
					<CardContent class="p-6">
						<div class="flex items-center justify-between">
							<div class="flex items-center gap-4 flex-1">
								<div class="flex-1">
									<h3 class="text-lg font-semibold">
										{result.firstname} {result.lastname}
									</h3>
									<p class="text-sm text-muted-foreground mt-1">
										{result.address || 'No address'}
									</p>
								</div>
								<div class="flex items-center gap-2">
									{#if result.ssn_found}
										<div class="flex items-center gap-2 text-green-600 bg-green-50 px-3 py-1 rounded-full">
											<CheckCircle class="h-4 w-4" />
											<span class="text-sm font-semibold">SSN Found</span>
										</div>
									{:else}
										<div class="flex items-center gap-2 text-orange-600 bg-orange-50 px-3 py-1 rounded-full">
											<XCircle class="h-4 w-4" />
											<span class="text-sm font-semibold">Not Found</span>
										</div>
									{/if}
								</div>
							</div>
							<Button
								variant="outline"
								size="sm"
								onclick={() => handleViewDetails(result)}
								class="ml-4 gap-2"
							>
								<Eye class="h-4 w-4" />
								View Details
							</Button>
						</div>
					</CardContent>
				</Card>
			{/each}
		</div>
	{:else if hasSearched && searchResults.length === 0}
		<div class="mt-8">
			<Card>
				<CardContent class="p-8 text-center">
					<div class="flex flex-col items-center gap-4">
						<div class="rounded-full bg-orange-100 p-4">
							<XCircle class="h-12 w-12 text-orange-600" />
						</div>
						<div class="space-y-2">
							<h3 class="text-xl font-semibold">No Results Found</h3>
							<p class="text-muted-foreground max-w-md">
								We couldn't find any results for your search. You can send this request to our manual search team for a more thorough investigation.
							</p>
						</div>
						<Button
							onclick={handleSendToManualSearch}
							disabled={isSendingToManual}
							class="mt-2 gap-2"
							size="lg"
						>
							{#if isSendingToManual}
								<Loader2 class="h-5 w-5 animate-spin" />
								Sending...
							{:else}
								<Send class="h-5 w-5" />
								Send to Manual Search
							{/if}
						</Button>
					</div>
				</CardContent>
			</Card>
		</div>
	{/if}
	{/if}
</div>
