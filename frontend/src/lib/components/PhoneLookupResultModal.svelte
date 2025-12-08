<script lang="ts">
	import {
		Dialog,
		DialogContent,
		DialogHeader,
		DialogTitle,
		DialogFooter
	} from '$lib/components/ui/dialog';
	import { Button } from '$lib/components/ui/button';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import Phone from '@lucide/svelte/icons/phone';
	import type { PhoneLookupResponse } from '$lib/api/client';

	interface Props {
		open: boolean;
		response: PhoneLookupResponse | null;
		onClose: () => void;
	}

	let { open, response, onClose }: Props = $props();

	let copiedFields = $state(new Set<string>());
	let copiedAll = $state(false);

	const result = $derived(response?.person_data);

	async function copyToClipboard(text: string, fieldName: string) {
		try {
			await navigator.clipboard.writeText(text);
			copiedFields.add(fieldName);
			copiedFields = copiedFields; // Trigger reactivity

			setTimeout(() => {
				copiedFields.delete(fieldName);
				copiedFields = copiedFields;
			}, 2000);
		} catch (error) {
			console.error('Failed to copy:', error);
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

		const text = `Phone: ${phoneNumber}
${fullName}
${addressLine}
${cityState}
DOB: ${dob}
SSN: ${ssn}
Contact Phone: ${phone}
Email: ${email}`;

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
		copiedFields = new Set();
		copiedAll = false;
		onClose();
	}
</script>

<Dialog
	{open}
	onOpenChange={(isOpen) => {
		if (!isOpen) handleClose();
	}}
>
	<DialogContent class="sm:max-w-lg">
		<DialogHeader>
			<DialogTitle class="flex items-center gap-2">
				<Phone class="h-5 w-5" />
				{result?.ssn_found ? 'SSN Found' : 'Phone Lookup Result'}
			</DialogTitle>
		</DialogHeader>

		{#if response && result}
			<div class="space-y-4">
				<!-- Phone Number -->
				<div class="bg-primary/10 rounded-lg p-4">
					<label class="text-sm text-muted-foreground">Phone Number</label>
					<div class="flex items-center gap-2 mt-1">
						<span class="font-mono font-bold text-xl">{response.phone_number || 'N/A'}</span>
						<button
							type="button"
							onclick={() => copyToClipboard(response?.phone_number || '', 'phone_number')}
							class="p-1 hover:bg-gray-100 rounded transition-colors"
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

				<!-- Top section: Full name and address -->
				<div class="border-b pb-3">
					<h3 class="text-2xl font-bold mb-2">
						{result.firstname || ''} {result.middlename ? result.middlename + ' ' : ''}{result.lastname || ''}
					</h3>
					<div class="text-sm space-y-1">
						<p>{result.address || 'N/A'}</p>
						<p>{result.city || ''}, {result.state || ''} {result.zip_code || ''}</p>
					</div>
				</div>

				<!-- Middle section: SSN and DOB with copy buttons -->
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
									class="p-1 hover:bg-gray-100 rounded transition-colors"
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
									class="p-1 hover:bg-gray-100 rounded transition-colors"
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

				<!-- Bottom section: Phone and Email (optional) -->
				{#if result.phone || result.email}
					<div class="space-y-2">
						{#if result.phone}
							<div class="flex items-center justify-between">
								<label class="text-sm text-muted-foreground">Contact Phone</label>
								<div class="flex items-center gap-2">
									<span class="font-medium">{result.phone}</span>
									<button
										type="button"
										onclick={() => copyToClipboard(result?.phone || '', 'contact_phone')}
										class="p-1 hover:bg-gray-100 rounded transition-colors"
									>
										{#if copiedFields.has('contact_phone')}
											<Check class="h-4 w-4 text-green-600" />
										{:else}
											<Copy class="h-4 w-4" />
										{/if}
									</button>
								</div>
							</div>
						{/if}
						{#if result.email}
							<div class="flex items-center justify-between">
								<label class="text-sm text-muted-foreground">Email</label>
								<div class="flex items-center gap-2">
									<span class="font-medium">{result.email}</span>
									<button
										type="button"
										onclick={() => copyToClipboard(result?.email || '', 'email')}
										class="p-1 hover:bg-gray-100 rounded transition-colors"
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
					</div>
				{/if}

				<!-- Charge info -->
				{#if response.charged_amount}
					<div class="bg-muted/50 rounded-lg p-3 text-sm">
						<span class="text-muted-foreground">Charged:</span>
						<span class="font-semibold ml-1">${response.charged_amount.toFixed(2)}</span>
					</div>
				{:else if !result.ssn_found}
					<div class="bg-orange-50 rounded-lg p-3 text-sm text-orange-700">
						SSN not found - no charge applied
					</div>
				{/if}
			</div>

			<DialogFooter class="sm:flex-row sm:justify-end">
				<div class="flex gap-3 w-full sm:w-auto">
					<Button
						variant="outline"
						onclick={copyAllData}
						class="flex-1 min-w-[120px] {copiedAll
							? 'bg-green-600 hover:bg-green-700 text-white'
							: ''}"
					>
						{#if copiedAll}
							<Check class="h-4 w-4 mr-2" />
							Copied!
						{:else}
							<Copy class="h-4 w-4 mr-2" />
							Copy All
						{/if}
					</Button>
					<Button onclick={handleClose} class="flex-1 min-w-[120px]">Done</Button>
				</div>
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
