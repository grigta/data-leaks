<script lang="ts">
	import { dev } from '$app/environment';
	import { onMount, onDestroy } from 'svelte';
	import {
		getSMSServices,
		getSMSNumber,
		checkSMSCode,
		cancelSMSRental,
		finishSMSRental,
		getSMSRentals,
		type SMSService,
		type SMSGetNumberResponse,
		type SMSRentalHistoryItem,
		handleApiError
	} from '$lib/api/client';
	import { refreshUser } from '$lib/stores/auth';
	import { t } from '$lib/i18n';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Label } from '$lib/components/ui/label';
	import { Input } from '$lib/components/ui/input';
	import { Badge } from '$lib/components/ui/badge';
	import { toast } from 'svelte-sonner';
	import MessageSquare from '@lucide/svelte/icons/message-square';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Phone from '@lucide/svelte/icons/phone';
	import History from '@lucide/svelte/icons/history';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import X from '@lucide/svelte/icons/x';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';

	// State
	let services = $state<SMSService[]>([]);
	let selectedService = $state<string>('');
	let selectedServiceData = $state<SMSService | null>(null);
	let isLoadingServices = $state(true);
	let isGettingNumber = $state(false);
	let errorMessage = $state('');
	let searchQuery = $state('');
	let isDropdownOpen = $state(false);
	let dropdownContainerRef: HTMLDivElement | null = $state(null);

	// Active rental state
	let activeRental = $state<{
		rental_id: string;
		phone_number: string;
		service_name: string;
		user_price: number;
		expires_at: string;
		sms_code?: string;
		status: string;
	} | null>(null);
	let isCheckingCode = $state(false);
	let isCancelling = $state(false);
	let isFinishing = $state(false);
	let pollingInterval: ReturnType<typeof setInterval> | null = null;

	// History state
	let showHistory = $state(false);
	let rentals = $state<SMSRentalHistoryItem[]>([]);
	let isLoadingRentals = $state(false);

	// Copy state
	let copiedPhone = $state(false);
	let copiedCode = $state(false);

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
			const response = await getSMSServices();
			services = response.services;
			dev && console.log('[SMS] Loaded services:', services.length);
		} catch (error: any) {
			console.error('[SMS] Error loading services:', error);
			errorMessage = handleApiError(error);
		} finally {
			isLoadingServices = false;
		}
	}

	async function loadRentals() {
		try {
			isLoadingRentals = true;
			const response = await getSMSRentals({ limit: 50 });
			rentals = response.rentals;
			dev && console.log('[SMS] Loaded rentals:', rentals.length);
		} catch (error: any) {
			console.error('[SMS] Error loading rentals:', error);
			toast.error(handleApiError(error));
		} finally {
			isLoadingRentals = false;
		}
	}

	async function handleGetNumber() {
		if (!selectedService) {
			errorMessage = $t('sms.selectService');
			return;
		}

		errorMessage = '';
		isGettingNumber = true;

		try {
			const response = await getSMSNumber(selectedService);

			dev && console.log('[SMS] Get number response:', response);

			// Update user balance if provided
			if (response.new_balance !== undefined) {
				await refreshUser();
			}

			if (response.success && response.rental_id && response.phone_number) {
				activeRental = {
					rental_id: response.rental_id,
					phone_number: response.phone_number,
					service_name: response.service_name || selectedServiceData?.name || '',
					user_price: response.user_price || 0,
					expires_at: response.expires_at || '',
					status: 'pending'
				};

				// Reset selection
				selectedService = '';
				selectedServiceData = null;
				searchQuery = '';

				// Start polling for SMS code
				startPolling();

				toast.success($t('sms.numberObtained'));
			} else {
				errorMessage = response.message || response.error || $t('sms.errorGettingNumber');
			}
		} catch (error: any) {
			console.error('[SMS] Get number error:', error);
			errorMessage = handleApiError(error);
		} finally {
			isGettingNumber = false;
		}
	}

	function startPolling() {
		stopPolling();
		pollingInterval = setInterval(handleCheckCode, 5000);
	}

	function stopPolling() {
		if (pollingInterval) {
			clearInterval(pollingInterval);
			pollingInterval = null;
		}
	}

	async function handleCheckCode() {
		if (!activeRental || activeRental.sms_code) return;

		try {
			isCheckingCode = true;
			const response = await checkSMSCode(activeRental.rental_id);

			dev && console.log('[SMS] Check code response:', response);

			if (response.status === 'code_received' && response.sms_code) {
				activeRental = {
					...activeRental,
					sms_code: response.sms_code,
					status: 'code_received'
				};
				stopPolling();
				toast.success($t('sms.codeReceived'));
			} else if (response.status === 'cancelled' || response.status === 'expired' || response.status === 'finished') {
				activeRental = {
					...activeRental,
					status: response.status
				};
				stopPolling();
			}
		} catch (error: any) {
			console.error('[SMS] Check code error:', error);
		} finally {
			isCheckingCode = false;
		}
	}

	async function handleCancel() {
		if (!activeRental) return;

		try {
			isCancelling = true;
			const response = await cancelSMSRental(activeRental.rental_id);

			dev && console.log('[SMS] Cancel response:', response);

			if (response.new_balance !== undefined) {
				await refreshUser();
			}

			if (response.refunded) {
				toast.success($t('sms.cancelledWithRefund', { amount: response.refund_amount?.toFixed(2) }));
			} else {
				toast.info($t('sms.cancelledNoRefund'));
			}

			stopPolling();
			activeRental = null;
		} catch (error: any) {
			console.error('[SMS] Cancel error:', error);
			toast.error(handleApiError(error));
		} finally {
			isCancelling = false;
		}
	}

	async function handleFinish() {
		if (!activeRental) return;

		try {
			isFinishing = true;
			await finishSMSRental(activeRental.rental_id);

			toast.success($t('sms.finished'));
			stopPolling();
			activeRental = null;
		} catch (error: any) {
			console.error('[SMS] Finish error:', error);
			toast.error(handleApiError(error));
		} finally {
			isFinishing = false;
		}
	}

	async function copyToClipboard(text: string, type: 'phone' | 'code') {
		try {
			await navigator.clipboard.writeText(text);
			if (type === 'phone') {
				copiedPhone = true;
				setTimeout(() => copiedPhone = false, 2000);
			} else {
				copiedCode = true;
				setTimeout(() => copiedCode = false, 2000);
			}
			toast.success($t('common.copied'));
		} catch (error) {
			toast.error($t('common.copyFailed'));
		}
	}

	function formatPrice(price: number): string {
		return `$${price.toFixed(2)}`;
	}

	function getStatusBadgeVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
		switch (status) {
			case 'active':
			case 'pending':
				return 'default';
			case 'code_received':
				return 'secondary';
			case 'cancelled':
			case 'expired':
				return 'destructive';
			case 'finished':
				return 'outline';
			default:
				return 'default';
		}
	}

	onMount(() => {
		loadServices();
	});

	onDestroy(() => {
		stopPolling();
	});
</script>

<svelte:head>
	<title>{$t('sms.title')}</title>
</svelte:head>

<svelte:window onclick={handleClickOutside} />

<div class="mx-auto py-8 px-4 max-w-[1400px] w-full">
	{#if isLoadingServices}
		<div class="flex justify-center items-center py-12">
			<Loader2 class="h-8 w-8 animate-spin" />
		</div>
	{:else}
		<Card>
			<CardHeader class="text-center">
				<CardTitle class="text-2xl flex items-center justify-center gap-2">
					<MessageSquare class="h-6 w-6" />
					{$t('sms.title')}
				</CardTitle>
			</CardHeader>
			<CardContent>
				{#if errorMessage}
					<Alert variant="destructive" class="mb-6">
						<AlertCircle class="h-4 w-4" />
						<AlertDescription>{errorMessage}</AlertDescription>
					</Alert>
				{/if}

				{#if activeRental}
					<!-- Active Rental Block -->
					<div class="space-y-6">
						<div class="bg-muted/50 rounded-lg p-6 space-y-4">
							<div class="flex items-center justify-between">
								<h3 class="text-lg font-semibold">{$t('sms.activeRental')}</h3>
								<Badge variant={getStatusBadgeVariant(activeRental.status)}>
									{activeRental.status === 'pending' ? $t('sms.waitingForSms') : activeRental.status}
								</Badge>
							</div>

							<!-- Phone Number -->
							<div class="space-y-2">
								<Label class="text-sm text-muted-foreground">{$t('sms.phoneNumber')}</Label>
								<div class="flex items-center gap-2">
									<div class="flex-1 bg-background rounded-md p-3 font-mono text-lg">
										{activeRental.phone_number}
									</div>
									<Button
										variant="outline"
										size="icon"
										onclick={() => copyToClipboard(activeRental!.phone_number, 'phone')}
									>
										{#if copiedPhone}
											<Check class="h-4 w-4 text-green-500" />
										{:else}
											<Copy class="h-4 w-4" />
										{/if}
									</Button>
								</div>
							</div>

							<!-- Service Info -->
							<div class="grid grid-cols-2 gap-4 text-sm">
								<div>
									<span class="text-muted-foreground">{$t('sms.service')}:</span>
									<span class="ml-2 font-medium">{activeRental.service_name}</span>
								</div>
								<div>
									<span class="text-muted-foreground">{$t('sms.price')}:</span>
									<span class="ml-2 font-medium">{formatPrice(activeRental.user_price)}</span>
								</div>
							</div>

							<!-- SMS Code -->
							{#if activeRental.sms_code}
								<div class="space-y-2">
									<Label class="text-sm text-muted-foreground">{$t('sms.smsCode')}</Label>
									<div class="flex items-center gap-2">
										<div class="flex-1 bg-green-100 dark:bg-green-900/30 rounded-md p-3 font-mono text-2xl text-center font-bold text-green-700 dark:text-green-400">
											{activeRental.sms_code}
										</div>
										<Button
											variant="outline"
											size="icon"
											onclick={() => copyToClipboard(activeRental!.sms_code!, 'code')}
										>
											{#if copiedCode}
												<Check class="h-4 w-4 text-green-500" />
											{:else}
												<Copy class="h-4 w-4" />
											{/if}
										</Button>
									</div>
								</div>
							{:else if activeRental.status === 'pending'}
								<div class="space-y-2">
									<Label class="text-sm text-muted-foreground">{$t('sms.smsCode')}</Label>
									<div class="flex items-center gap-2">
										<div class="flex-1 bg-background rounded-md p-3 text-center text-muted-foreground">
											<div class="flex items-center justify-center gap-2">
												<Loader2 class="h-4 w-4 animate-spin" />
												{$t('sms.waitingForSms')}
											</div>
										</div>
										<Button
											variant="outline"
											size="icon"
											disabled={isCheckingCode}
											onclick={handleCheckCode}
										>
											<RefreshCw class="h-4 w-4 {isCheckingCode ? 'animate-spin' : ''}" />
										</Button>
									</div>
								</div>
							{/if}

							<!-- Actions -->
							<div class="flex gap-4 pt-4">
								{#if activeRental.sms_code}
									<Button
										class="flex-1"
										disabled={isFinishing}
										onclick={handleFinish}
									>
										{#if isFinishing}
											<Loader2 class="mr-2 h-4 w-4 animate-spin" />
										{/if}
										{$t('sms.finish')}
									</Button>
								{:else}
									<Button
										variant="destructive"
										class="flex-1"
										disabled={isCancelling}
										onclick={handleCancel}
									>
										{#if isCancelling}
											<Loader2 class="mr-2 h-4 w-4 animate-spin" />
										{:else}
											<X class="mr-2 h-4 w-4" />
										{/if}
										{$t('sms.cancelRefund')}
									</Button>
								{/if}
							</div>
						</div>
					</div>
				{:else}
					<!-- Service Selection -->
					<div class="space-y-6">
						<div class="space-y-2" bind:this={dropdownContainerRef}>
							<Label for="service-search" class="text-sm font-medium">{$t('sms.selectService')} *</Label>
							<div class="relative">
								<Input
									id="service-search"
									type="text"
									bind:value={searchQuery}
									placeholder={$t('sms.searchServices')}
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
												selectedServiceData = service;
												searchQuery = service.name;
												isDropdownOpen = false;
											}}
										>
											<span class="font-medium">{service.name}</span>
											<span class="text-sm font-semibold text-green-600 dark:text-green-400">{formatPrice(service.user_price)}</span>
										</button>
									{:else}
										<div class="px-4 py-3 text-center text-muted-foreground bg-background">{$t('sms.noServicesFound')}</div>
									{/each}
								</div>
							{/if}
						</div>

						<!-- Selected Service Info -->
						{#if selectedServiceData}
							<div class="bg-muted/50 rounded-lg p-4 space-y-2">
								<p class="text-sm">
									<strong>{$t('sms.selectedService')}:</strong> {selectedServiceData.name}
								</p>
								<p class="text-sm">
									<strong>{$t('sms.price')}:</strong> <span class="text-green-600 dark:text-green-400 font-semibold">{formatPrice(selectedServiceData.user_price)}</span>
								</p>
								<p class="text-xs text-muted-foreground">
									{$t('sms.priceHint')}
								</p>
							</div>
						{/if}

						<!-- Actions -->
						<div class="flex flex-col sm:flex-row gap-4 justify-center">
							<Button
								size="lg"
								class="min-w-[200px]"
								disabled={isGettingNumber || !selectedService}
								onclick={handleGetNumber}
							>
								{#if isGettingNumber}
									<Loader2 class="mr-2 h-5 w-5 animate-spin" />
									{$t('sms.gettingNumber')}
								{:else}
									<Phone class="mr-2 h-5 w-5" />
									{$t('sms.getNumber')}
								{/if}
							</Button>

							<Button
								variant="outline"
								size="lg"
								class="min-w-[200px]"
								onclick={() => {
									showHistory = !showHistory;
									if (showHistory) loadRentals();
								}}
							>
								<History class="mr-2 h-5 w-5" />
								{$t('sms.viewHistory')}
							</Button>
						</div>
					</div>
				{/if}

				<!-- History Section -->
				{#if showHistory}
					<div class="mt-8 space-y-4">
						<h3 class="text-lg font-semibold">{$t('sms.rentalHistory')}</h3>

						{#if isLoadingRentals}
							<div class="flex justify-center py-8">
								<Loader2 class="h-6 w-6 animate-spin" />
							</div>
						{:else if rentals.length === 0}
							<div class="text-center py-8 text-muted-foreground">
								{$t('sms.noHistory')}
							</div>
						{:else}
							<div class="space-y-2">
								{#each rentals as rental}
									<div class="flex items-center justify-between p-4 bg-muted/30 rounded-lg">
										<div class="space-y-1">
											<div class="font-medium">{rental.service_name}</div>
											<div class="text-sm text-muted-foreground font-mono">{rental.phone_number}</div>
											{#if rental.sms_code}
												<div class="text-sm font-mono text-green-600 dark:text-green-400">
													{$t('sms.code')}: {rental.sms_code}
												</div>
											{/if}
										</div>
										<div class="text-right space-y-1">
											<Badge variant={getStatusBadgeVariant(rental.status)}>{rental.status}</Badge>
											<div class="text-sm">{formatPrice(rental.user_price)}</div>
											<div class="text-xs text-muted-foreground">
												{new Date(rental.created_at).toLocaleString()}
											</div>
										</div>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{/if}
			</CardContent>
		</Card>
	{/if}
</div>
