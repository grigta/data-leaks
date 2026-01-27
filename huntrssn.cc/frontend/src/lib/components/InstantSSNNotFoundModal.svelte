<script lang="ts">
	import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '$lib/components/ui/dialog';
	import { Button } from '$lib/components/ui/button';
	import XCircle from '@lucide/svelte/icons/x-circle';
	import Send from '@lucide/svelte/icons/send';
	import Loader2 from '@lucide/svelte/icons/loader-2';

	interface Props {
		open: boolean;
		searchData: { firstname: string; lastname: string; address: string };
		onClose: () => void;
		onSendToManual: () => Promise<void>;
	}

	let { open, searchData, onClose, onSendToManual }: Props = $props();

	let isSending = $state(false);

	async function handleSendToManual() {
		isSending = true;
		try {
			await onSendToManual();
		} catch (error) {
			console.error('Error sending to manual search:', error);
		} finally {
			isSending = false;
		}
	}

	function handleClose() {
		isSending = false;
		onClose();
	}
</script>

<Dialog {open} onOpenChange={(isOpen) => { if (!isOpen) handleClose(); }}>
	<DialogContent class="sm:max-w-md">
		<DialogHeader>
			<DialogTitle>No Results Found</DialogTitle>
			<DialogDescription>
				We couldn't find any SSN records matching your search. You can send this request to our manual search team for further investigation.
			</DialogDescription>
		</DialogHeader>

		<div class="flex flex-col items-center gap-4 py-4">
			<!-- Icon -->
			<div class="rounded-full bg-orange-100 p-4 flex items-center justify-center">
				<XCircle class="h-12 w-12 text-orange-600" />
			</div>

			<!-- Search parameters display -->
			<div class="w-full bg-muted/50 rounded-md p-3 space-y-1 text-sm">
				<div class="flex justify-between">
					<span class="text-muted-foreground">First Name:</span>
					<span class="font-medium">{searchData.firstname || 'N/A'}</span>
				</div>
				<div class="flex justify-between">
					<span class="text-muted-foreground">Last Name:</span>
					<span class="font-medium">{searchData.lastname || 'N/A'}</span>
				</div>
				<div class="flex justify-between">
					<span class="text-muted-foreground">Address:</span>
					<span class="font-medium">{searchData.address || 'N/A'}</span>
				</div>
			</div>
		</div>

		<DialogFooter class="sm:flex-row sm:justify-end">
			<div class="flex gap-3 w-full sm:w-auto">
				<Button
					variant="outline"
					onclick={handleClose}
					disabled={isSending}
					class="flex-1 min-w-[120px]"
				>
					Done
				</Button>
				<Button
					onclick={handleSendToManual}
					disabled={isSending}
					class="flex-1 min-w-[120px] gap-2"
				>
					{#if isSending}
						<Loader2 class="h-4 w-4 animate-spin" />
						Sending...
					{:else}
						<Send class="h-4 w-4" />
						Send to Manual Search
					{/if}
				</Button>
			</div>
		</DialogFooter>
	</DialogContent>
</Dialog>
