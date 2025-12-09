<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Dialog,
		DialogContent,
		DialogHeader,
		DialogTitle,
		DialogFooter
	} from '$lib/components/ui/dialog';
	import { Button } from '$lib/components/ui/button';
	import { Label } from '$lib/components/ui/label';
	import { Badge } from '$lib/components/ui/badge';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import Phone from '@lucide/svelte/icons/phone';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import X from '@lucide/svelte/icons/x';
	import {
		type PhoneLookupResponse,
		checkPhoneRentalCode,
		finishPhoneRental,
		cancelPhoneRental
	} from '$lib/api/client';
	import { refreshUser } from '$lib/stores/auth';
	import { t } from '$lib/i18n';
	import { toast } from 'svelte-sonner';

	interface Props {
		open: boolean;
		response: PhoneLookupResponse | null;
		onClose: () => void;
	}

	let { open, response, onClose }: Props = $props();

	let copiedFields = $state(new Set<string>());
	let copiedAll = $state(false);

	// SMS Code state
	let smsCode = $state<string | null>(null);
	let smsStatus = $state<string>('pending');
	let isCheckingCode = $state(false);
	let isCancelling = $state(false);
	let isFinishing = $state(false);
	let pollingInterval: ReturnType<typeof setInterval> | null = null;
	let copiedSmsCode = $state(false);

	const result = $derived(response?.person_data);
	const rentalId = $derived(response?.rental_id);
	const hasPersonData = $derived(
		result?.firstname || result?.lastname || result?.address || result?.dob
	);

	function startPolling() {
		if (pollingInterval) return;
		pollingInterval = setInterval(handleCheckCode, 5000);
	}

	function stopPolling() {
		if (pollingInterval) {
			clearInterval(pollingInterval);
			pollingInterval = null;
		}
	}

	async function handleCheckCode() {
		if (!rentalId || smsCode) return;

		try {
			isCheckingCode = true;
			const codeResponse = await checkPhoneRentalCode(rentalId);

			if (codeResponse.status === 'code_received' && codeResponse.sms_code) {
				smsCode = codeResponse.sms_code;
				smsStatus = 'code_received';
				stopPolling();
				toast.success($t('phone-lookup.codeReceived'));
			} else if (codeResponse.status === 'cancelled' || codeResponse.status === 'expired' || codeResponse.status === 'finished') {
				smsStatus = codeResponse.status;
				stopPolling();
			}
		} catch (error) {
			console.error('[PhoneLookup] Check code error:', error);
		} finally {
			isCheckingCode = false;
		}
	}

	async function handleCancel() {
		if (!rentalId) return;

		try {
			isCancelling = true;
			const cancelResponse = await cancelPhoneRental(rentalId);

			if (cancelResponse.success) {
				await refreshUser();
				smsStatus = 'cancelled';
				stopPolling();
				toast.success($t('phone-lookup.cancelledRefund'));
			}
		} catch (error) {
			console.error('[PhoneLookup] Cancel error:', error);
			toast.error($t('phone-lookup.cancelError'));
		} finally {
			isCancelling = false;
		}
	}

	async function handleFinish() {
		if (!rentalId) return;

		try {
			isFinishing = true;
			await finishPhoneRental(rentalId);
			smsStatus = 'finished';
			stopPolling();
			toast.success($t('phone-lookup.finished'));
		} catch (error) {
			console.error('[PhoneLookup] Finish error:', error);
		} finally {
			isFinishing = false;
		}
	}

	async function copyToClipboard(text: string, fieldName: string) {
		try {
			await navigator.clipboard.writeText(text);
			copiedFields.add(fieldName);
			copiedFields = copiedFields;

			setTimeout(() => {
				copiedFields.delete(fieldName);
				copiedFields = copiedFields;
			}, 2000);
		} catch (error) {
			console.error('Failed to copy:', error);
		}
	}

	async function copySmsCode() {
		if (!smsCode) return;
		try {
			await navigator.clipboard.writeText(smsCode);
			copiedSmsCode = true;
			setTimeout(() => copiedSmsCode = false, 2000);
			toast.success($t('common.copied'));
		} catch (error) {
			console.error('Failed to copy SMS code:', error);
		}
	}

	async function copyAllData() {
		if (!result || !response) return;

		const phoneNumber = response.phone_number || 'N/A';
		const fullName = `${result.firstname || ''}${result.middlename ? ' ' + result.middlename : ''} ${result.lastname || ''}`;
		const addressLine = result.address || 'N/A';
		const cityState =
			result.city && result.state ? `${result.city}, ${result.state} ${result.zip_code || ''}` : 'N/A';
		const dob = result.dob || 'N/A';
		const ssn = result.ssn || 'N/A';
		const phone = result.phone || 'N/A';
		const email = result.email || 'N/A';
		const smsCodeText = smsCode || 'N/A';

		const text = `Phone: ${phoneNumber}
${fullName}
${addressLine}
${cityState}
DOB: ${dob}
SSN: ${ssn}
Contact Phone: ${phone}
Email: ${email}
SMS Code: ${smsCodeText}`;

		try {
			await navigator.clipboard.writeText(text);
			copiedAll = true;

			setTimeout(() => {
				copiedAll = false;
			}, 2000);
		} catch (error) {
			console.error('Failed to copy all data:', error);
		}
	}

	function handleClose() {
		stopPolling();
		copiedFields = new Set();
		copiedAll = false;
		smsCode = null;
		smsStatus = 'pending';
		copiedSmsCode = false;
		onClose();
	}

	// Start polling when modal opens with a rental
	$effect(() => {
		if (open && rentalId && !smsCode && smsStatus === 'pending') {
			startPolling();
		}
		return () => {
			stopPolling();
		};
	});
</script>

<Dialog
	{open}
	onOpenChange={(isOpen) => {
		if (!isOpen) handleClose();
	}}
>
	<DialogContent class="sm:max-w-lg">
		<DialogHeader class="relative">
			<DialogTitle class="flex items-center gap-2">
				<Phone class="h-5 w-5" />
				{result?.ssn_found ? 'SSN Found' : 'Phone Lookup Result'}
			</DialogTitle>

			<!-- Copy Fullz button - absolute top-right -->
			{#if hasPersonData}
				<Button
					variant="outline"
					size="sm"
					class="absolute right-0 top-0"
					onclick={copyAllData}
				>
					{#if copiedAll}
						<Check class="h-4 w-4 mr-1" />
						Copied!
					{:else}
						<Copy class="h-4 w-4 mr-1" />
						Copy Fullz
					{/if}
				</Button>
			{/if}
		</DialogHeader>

		{#if response && result}
			<div class="space-y-4">
				<!-- 1. Fullz Data Section -->
				{#if hasPersonData}
					<div class="border-b pb-3">
						<h3 class="text-2xl font-bold mb-2">
							{result.firstname || ''} {result.middlename ? result.middlename + ' ' : ''}{result.lastname || ''}
						</h3>
						<div class="text-sm space-y-1">
							<p>{result.address || 'N/A'}</p>
							<p>{result.city || ''}, {result.state || ''} {result.zip_code || ''}</p>
						</div>
					</div>

					<div class="grid grid-cols-2 gap-4 border-b pb-3">
						<!-- SSN -->
						<div class="space-y-2">
							<label class="text-sm text-muted-foreground">Social Security Number</label>
							<div class="flex items-center gap-2">
								{#if result.ssn_found && result.ssn}
									<span class="font-mono font-semibold text-lg text-green-600">{result.ssn}</span>
									<button
										type="button"
										onclick={() => copyToClipboard(result?.ssn || '', 'ssn')}
										class="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
									>
										{#if copiedFields.has('ssn')}
											<Check class="h-4 w-4 text-green-600" />
										{:else}
											<Copy class="h-4 w-4" />
										{/if}
									</button>
								{:else}
									<span class="font-mono text-muted-foreground">Not Found</span>
								{/if}
							</div>
						</div>

						<!-- DOB -->
						<div class="space-y-2">
							<label class="text-sm text-muted-foreground">Date of Birth</label>
							<div class="flex items-center gap-2">
								<span class="font-mono font-semibold text-lg">{result.dob || 'N/A'}</span>
								{#if result.dob}
									<button
										type="button"
										onclick={() => copyToClipboard(result?.dob || '', 'dob')}
										class="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
									>
										{#if copiedFields.has('dob')}
											<Check class="h-4 w-4 text-green-600" />
										{:else}
											<Copy class="h-4 w-4" />
										{/if}
									</button>
								{/if}
							</div>
						</div>
					</div>

					<!-- Email (optional) -->
					{#if result.email}
						<div class="flex items-center justify-between border-b pb-3">
							<label class="text-sm text-muted-foreground">Email</label>
							<div class="flex items-center gap-2">
								<span class="font-medium">{result.email}</span>
								<button
									type="button"
									onclick={() => copyToClipboard(result?.email || '', 'email')}
									class="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
								>
									{#if copiedFields.has('email')}
										<Check class="h-4 w-4 text-green-600" />
									{:else}
										<Copy class="h-4 w-4" />
									{/if}
								</button>
							</div>
						</div>
					{/if}
				{:else}
					<!-- No person data found -->
					<div class="bg-muted/50 rounded-lg p-4 text-center">
						<p class="text-muted-foreground">No owner information found for this phone number</p>
					</div>
				{/if}

				<!-- 2. Phone Number Section -->
				<div class="bg-primary/10 rounded-lg p-4">
					<label class="text-sm text-muted-foreground">Phone Number</label>
					<div class="flex items-center gap-2 mt-1">
						<span class="font-mono font-bold text-xl">{response.phone_number || 'N/A'}</span>
						<button
							type="button"
							onclick={() => copyToClipboard(response?.phone_number || '', 'phone_number')}
							class="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
							disabled={!response.phone_number}
						>
							{#if copiedFields.has('phone_number')}
								<Check class="h-4 w-4 text-green-600" />
							{:else}
								<Copy class="h-4 w-4" />
							{/if}
						</button>
					</div>
				</div>

				<!-- 3. SMS Code Section -->
				{#if rentalId}
					<div class="bg-muted/50 rounded-lg p-4 space-y-3">
						<div class="flex items-center justify-between">
							<Label class="text-sm font-medium">{$t('phone-lookup.smsCode')}</Label>
							<Badge variant={smsCode ? 'secondary' : 'default'}>
								{smsCode ? $t('phone-lookup.codeReceived') : $t('phone-lookup.waitingForSms')}
							</Badge>
						</div>

						{#if smsCode}
							<div class="flex items-center gap-2">
								<div class="flex-1 bg-green-100 dark:bg-green-900/30 rounded-md p-3 font-mono text-2xl text-center font-bold text-green-700 dark:text-green-400">
									{smsCode}
								</div>
								<Button
									variant="outline"
									size="icon"
									onclick={copySmsCode}
								>
									{#if copiedSmsCode}
										<Check class="h-4 w-4 text-green-500" />
									{:else}
										<Copy class="h-4 w-4" />
									{/if}
								</Button>
							</div>
						{:else if smsStatus === 'pending'}
							<div class="flex items-center gap-2">
								<div class="flex-1 bg-background rounded-md p-3 text-center text-muted-foreground">
									<div class="flex items-center justify-center gap-2">
										<Loader2 class="h-4 w-4 animate-spin" />
										{$t('phone-lookup.waitingForSms')}
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
						{:else}
							<div class="text-center text-muted-foreground py-2">
								{smsStatus === 'cancelled' ? $t('phone-lookup.cancelled') :
								 smsStatus === 'expired' ? $t('phone-lookup.expired') :
								 $t('phone-lookup.finished')}
							</div>
						{/if}

						<!-- SMS Actions -->
						{#if smsStatus === 'pending' && !smsCode}
							<div class="flex gap-2 pt-2">
								<Button
									variant="destructive"
									size="sm"
									class="flex-1"
									disabled={isCancelling}
									onclick={handleCancel}
								>
									{#if isCancelling}
										<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									{:else}
										<X class="mr-2 h-4 w-4" />
									{/if}
									{$t('phone-lookup.cancelRefund')}
								</Button>
							</div>
						{:else if smsCode && smsStatus !== 'finished'}
							<div class="flex gap-2 pt-2">
								<Button
									size="sm"
									class="flex-1"
									disabled={isFinishing}
									onclick={handleFinish}
								>
									{#if isFinishing}
										<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									{/if}
									{$t('phone-lookup.finish')}
								</Button>
							</div>
						{/if}
					</div>
				{/if}

				<!-- 4. Charge Info Section -->
				{#if response.charged_amount}
					<div class="bg-muted/50 rounded-lg p-3 text-sm">
						<span class="text-muted-foreground">Charged:</span>
						<span class="font-semibold ml-1">${response.charged_amount.toFixed(2)}</span>
					</div>
				{:else if !result.ssn_found}
					<div class="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-3 text-sm text-orange-700 dark:text-orange-400">
						SSN not found - no charge applied
					</div>
				{/if}
			</div>

			<DialogFooter>
				<Button onclick={handleClose}>Done</Button>
			</DialogFooter>
		{:else if response && !response.success}
			<div class="py-8 text-center">
				<p class="text-muted-foreground">{response.message || 'Search failed'}</p>
			</div>
			<DialogFooter>
				<Button onclick={handleClose}>Close</Button>
			</DialogFooter>
		{/if}
	</DialogContent>
</Dialog>
