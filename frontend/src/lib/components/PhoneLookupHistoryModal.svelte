<script lang="ts">
	import {
		Dialog,
		DialogContent,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Phone from '@lucide/svelte/icons/phone';
	import Copy from '@lucide/svelte/icons/copy';
	import Check from '@lucide/svelte/icons/check';
	import CheckCircle from '@lucide/svelte/icons/check-circle';
	import XCircle from '@lucide/svelte/icons/x-circle';
	import { renewPhoneRental, type PhoneRentalResponse, handleApiError } from '$lib/api/client';
	import { toast } from 'svelte-sonner';

	interface Props {
		open: boolean;
		rentals: PhoneRentalResponse[];
		isLoading: boolean;
		onClose: () => void;
		onRefresh: () => void;
	}

	let { open, rentals, isLoading, onClose, onRefresh }: Props = $props();

	let renewingId = $state<string | null>(null);
	let copiedFields = $state(new Set<string>());

	async function handleRenew(rentalId: string) {
		renewingId = rentalId;
		try {
			const response = await renewPhoneRental(rentalId);
			toast.success(response.message || 'Rental renewed successfully');
			onRefresh();
		} catch (error: any) {
			console.error('[PHONE-LOOKUP] Error renewing rental:', error);
			toast.error(handleApiError(error));
		} finally {
			renewingId = null;
		}
	}

	async function copyToClipboard(text: string, fieldId: string) {
		try {
			await navigator.clipboard.writeText(text);
			copiedFields.add(fieldId);
			copiedFields = copiedFields;

			setTimeout(() => {
				copiedFields.delete(fieldId);
				copiedFields = copiedFields;
			}, 2000);
		} catch (error) {
			console.error('Failed to copy:', error);
		}
	}

	function formatDate(dateStr: string): string {
		return new Date(dateStr).toLocaleString();
	}

	function getStatusBadge(status: string) {
		switch (status) {
			case 'active':
				return { variant: 'default' as const, label: 'Active' };
			case 'expired':
				return { variant: 'secondary' as const, label: 'Expired' };
			case 'cancelled':
				return { variant: 'destructive' as const, label: 'Cancelled' };
			case 'finished':
				return { variant: 'outline' as const, label: 'Finished' };
			default:
				return { variant: 'outline' as const, label: status };
		}
	}

	function handleClose() {
		copiedFields = new Set();
		onClose();
	}
</script>

<Dialog
	{open}
	onOpenChange={(isOpen) => {
		if (!isOpen) handleClose();
	}}
>
	<DialogContent class="sm:max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
		<DialogHeader class="flex-shrink-0">
			<div class="flex items-center justify-between">
				<DialogTitle class="flex items-center gap-2">
					<Phone class="h-5 w-5" />
					Rental History
				</DialogTitle>
				<Button variant="ghost" size="sm" onclick={onRefresh} disabled={isLoading}>
					<RefreshCw class="h-4 w-4 {isLoading ? 'animate-spin' : ''}" />
				</Button>
			</div>
		</DialogHeader>

		<div class="flex-1 overflow-y-auto">
			{#if isLoading}
				<div class="flex justify-center items-center py-12">
					<Loader2 class="h-8 w-8 animate-spin" />
				</div>
			{:else if rentals.length === 0}
				<div class="text-center py-12 text-muted-foreground">
					<Phone class="h-12 w-12 mx-auto mb-4 opacity-50" />
					<p>No rental history yet</p>
				</div>
			{:else}
				<div class="space-y-4">
					{#each rentals as rental}
						{@const statusBadge = getStatusBadge(rental.status)}
						<div class="border rounded-lg p-4 space-y-3">
							<!-- Header -->
							<div class="flex items-start justify-between">
								<div>
									<div class="flex items-center gap-2">
										<span class="font-mono font-bold text-lg">{rental.phone_number}</span>
										<button
											type="button"
											onclick={() => copyToClipboard(rental.phone_number, `phone-${rental.id}`)}
											class="p-1 hover:bg-gray-100 rounded transition-colors"
										>
											{#if copiedFields.has(`phone-${rental.id}`)}
												<Check class="h-3 w-3 text-green-600" />
											{:else}
												<Copy class="h-3 w-3" />
											{/if}
										</button>
									</div>
									<p class="text-sm text-muted-foreground">{rental.service_name}</p>
								</div>
								<div class="flex items-center gap-2">
									{#if rental.ssn_found}
										<div class="flex items-center gap-1 text-green-600">
											<CheckCircle class="h-4 w-4" />
											<span class="text-xs">SSN Found</span>
										</div>
									{:else}
										<div class="flex items-center gap-1 text-muted-foreground">
											<XCircle class="h-4 w-4" />
											<span class="text-xs">No SSN</span>
										</div>
									{/if}
									<Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
								</div>
							</div>

							<!-- Person Data (if available) -->
							{#if rental.person_data && rental.ssn_found}
								<div class="bg-muted/50 rounded p-3 space-y-1 text-sm">
									<p class="font-semibold">
										{rental.person_data.firstname || ''} {rental.person_data.lastname || ''}
									</p>
									{#if rental.person_data.ssn}
										<div class="flex items-center gap-2">
											<span class="text-muted-foreground">SSN:</span>
											<span class="font-mono">{rental.person_data.ssn}</span>
											<button
												type="button"
												onclick={() =>
													copyToClipboard(rental.person_data?.ssn || '', `ssn-${rental.id}`)}
												class="p-1 hover:bg-gray-200 rounded transition-colors"
											>
												{#if copiedFields.has(`ssn-${rental.id}`)}
													<Check class="h-3 w-3 text-green-600" />
												{:else}
													<Copy class="h-3 w-3" />
												{/if}
											</button>
										</div>
									{/if}
									{#if rental.person_data.dob}
										<p>
											<span class="text-muted-foreground">DOB:</span>
											{rental.person_data.dob}
										</p>
									{/if}
									{#if rental.person_data.address}
										<p>
											<span class="text-muted-foreground">Address:</span>
											{rental.person_data.address}, {rental.person_data.city || ''}, {rental
												.person_data.state || ''} {rental.person_data.zip_code || ''}
										</p>
									{/if}
								</div>
							{/if}

							<!-- Footer -->
							<div class="flex items-center justify-between text-xs text-muted-foreground">
								<span>Created: {formatDate(rental.created_at)}</span>
								{#if rental.status === 'expired'}
									<Button
										variant="outline"
										size="sm"
										disabled={renewingId === rental.id}
										onclick={() => handleRenew(rental.id)}
									>
										{#if renewingId === rental.id}
											<Loader2 class="h-4 w-4 animate-spin mr-1" />
										{/if}
										Renew
									</Button>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</DialogContent>
</Dialog>
