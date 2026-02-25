<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import {
		Dialog,
		DialogContent,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import FileText from '@lucide/svelte/icons/file-text';
	import Eye from '@lucide/svelte/icons/eye';
	import UserCheck from '@lucide/svelte/icons/user-check';
	import Clock from '@lucide/svelte/icons/clock';
	import CheckCircle from '@lucide/svelte/icons/check-circle';
	import XCircle from '@lucide/svelte/icons/x-circle';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Send from '@lucide/svelte/icons/send';
	import Ban from '@lucide/svelte/icons/ban';
	import {
		getTickets,
		getTicket,
		updateTicket,
		assignTicket,
		getUserTable,
		handleApiError,
		type TicketResponse,
		type WorkerResponse
	} from '$lib/api/client';
	import { formatDate, formatDateTime, truncate } from '$lib/utils';
	import { toast } from 'svelte-sonner';
	import { wsManager, TICKET_CREATED, TICKET_UPDATED } from '$lib/websocket/manager';
	import { t } from '$lib/i18n';

	// State
	let tickets = $state<TicketResponse[]>([]);
	let workers = $state<WorkerResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let statusFilter = $state<string | null>(null);
	let selectedTicket = $state<TicketResponse | null>(null);
	let showDetailsDialog = $state(false);
	let showAssignDialog = $state(false);
	let showRespondDialog = $state(false);
	let selectedWorkerId = $state<string>('');
	let isAssigning = $state(false);
	let isResponding = $state(false);
	let currentPage = $state(1);
	let pageSize = $state(50);
	let totalCount = $state(0);

	// Response form fields
	let responseSSN = $state('');
	let responseDOB = $state('');
	let responseFirstname = $state('');
	let responseLastname = $state('');
	let responseMiddlename = $state('');
	let responseAddress = $state('');
	let responseCity = $state('');
	let responseState = $state('');
	let responseZip = $state('');
	let responseEmail = $state('');
	let responsePhone = $state('');

	// AbortController
	let abortController: AbortController | null = null;

	// Computed
	let totalPages = $derived(Math.ceil(totalCount / pageSize));
	let startIndex = $derived((currentPage - 1) * pageSize + 1);
	let endIndex = $derived(Math.min(currentPage * pageSize, totalCount));

	async function loadTickets() {
		if (abortController) abortController.abort();
		abortController = new AbortController();
		const currentController = abortController;

		isLoading = true;
		error = '';

		try {
			const offset = (currentPage - 1) * pageSize;
			const response = await getTickets({
				status_filter: statusFilter || undefined,
				limit: pageSize,
				offset
			});
			if (!currentController.signal.aborted) {
				tickets = response.tickets;
				totalCount = response.total_count;
			}
		} catch (err: any) {
			if (!currentController.signal.aborted) {
				error = handleApiError(err);
				toast.error($t('tickets.loadError'));
			}
		} finally {
			if (!currentController.signal.aborted) {
				isLoading = false;
			}
		}
	}

	async function loadWorkers() {
		try {
			const response = await getUserTable();
			workers = response.users.filter((user: any) => user.worker_role === true) as WorkerResponse[];
		} catch (err: any) {
			console.error('Failed to load workers:', err);
		}
	}

	function handleViewDetails(ticket: TicketResponse) {
		selectedTicket = ticket;
		showDetailsDialog = true;
	}

	function handleAssign(ticket: TicketResponse) {
		selectedTicket = ticket;
		selectedWorkerId = '';
		if (workers.length === 0) loadWorkers();
		showAssignDialog = true;
	}

	function handleRespond(ticket: TicketResponse) {
		selectedTicket = ticket;
		// Pre-fill from ticket data
		responseFirstname = ticket.firstname || '';
		responseLastname = ticket.lastname || '';
		responseAddress = ticket.address || '';
		responseMiddlename = '';
		responseSSN = '';
		responseDOB = '';
		responseCity = '';
		responseState = '';
		responseZip = '';
		responseEmail = '';
		responsePhone = '';

		// If there's existing response_data, pre-fill
		if (ticket.response_data) {
			responseSSN = ticket.response_data.ssn || '';
			responseDOB = ticket.response_data.dob || '';
			responseMiddlename = ticket.response_data.middlename || '';
			responseCity = ticket.response_data.city || '';
			responseState = ticket.response_data.state || '';
			responseZip = ticket.response_data.zip || '';
			responseEmail = ticket.response_data.email || '';
			responsePhone = ticket.response_data.phone || '';
			if (ticket.response_data.firstname) responseFirstname = ticket.response_data.firstname;
			if (ticket.response_data.lastname) responseLastname = ticket.response_data.lastname;
			if (ticket.response_data.address) responseAddress = ticket.response_data.address;
		}

		showRespondDialog = true;
	}

	async function confirmAssign() {
		if (!selectedTicket || !selectedWorkerId) {
			toast.error($t('tickets.assign.selectError'));
			return;
		}
		isAssigning = true;
		try {
			await assignTicket(selectedTicket.id, selectedWorkerId);
			toast.success($t('tickets.messages.assigned'));
			showAssignDialog = false;
			selectedTicket = null;
			selectedWorkerId = '';
			loadTickets();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isAssigning = false;
		}
	}

	async function submitResponse(action: 'completed' | 'rejected') {
		if (!selectedTicket) return;

		if (action === 'completed' && !responseSSN.trim()) {
			toast.error($t('tickets.messages.ssnRequired'));
			return;
		}

		isResponding = true;
		try {
			const responseData: Record<string, string> = {};
			if (responseSSN.trim()) responseData.ssn = responseSSN.trim();
			if (responseDOB.trim()) responseData.dob = responseDOB.trim();
			if (responseFirstname.trim()) responseData.firstname = responseFirstname.trim();
			if (responseLastname.trim()) responseData.lastname = responseLastname.trim();
			if (responseMiddlename.trim()) responseData.middlename = responseMiddlename.trim();
			if (responseAddress.trim()) responseData.address = responseAddress.trim();
			if (responseCity.trim()) responseData.city = responseCity.trim();
			if (responseState.trim()) responseData.state = responseState.trim();
			if (responseZip.trim()) responseData.zip = responseZip.trim();
			if (responseEmail.trim()) responseData.email = responseEmail.trim();
			if (responsePhone.trim()) responseData.phone = responsePhone.trim();

			await updateTicket(selectedTicket.id, {
				status: action,
				response_data: Object.keys(responseData).length > 0 ? responseData : undefined
			});

			toast.success(action === 'completed' ? $t('tickets.messages.completed') : $t('tickets.messages.rejected'));
			showRespondDialog = false;
			selectedTicket = null;
			loadTickets();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isResponding = false;
		}
	}

	function getStatusBadgeVariant(status: string): 'default' | 'secondary' | 'destructive' {
		if (status === 'completed') return 'default';
		if (status === 'rejected') return 'destructive';
		if (status === 'processing') return 'default';
		return 'secondary';
	}

	function getStatusLabel(status: string): string {
		return $t('tickets.statuses.' + status) || status;
	}

	function getStatusIcon(status: string) {
		if (status === 'pending') return Clock;
		if (status === 'processing') return Loader2;
		if (status === 'completed') return CheckCircle;
		if (status === 'rejected') return XCircle;
		return Clock;
	}

	function goToPage(page: number) {
		if (page >= 1 && page <= totalPages) {
			currentPage = page;
			loadTickets();
		}
	}

	function getPageNumbers(): number[] {
		const pages: number[] = [];
		const maxPages = 5;
		let startPage = Math.max(1, currentPage - Math.floor(maxPages / 2));
		let endPage = Math.min(totalPages, startPage + maxPages - 1);
		if (endPage - startPage + 1 < maxPages) {
			startPage = Math.max(1, endPage - maxPages + 1);
		}
		for (let i = startPage; i <= endPage; i++) pages.push(i);
		return pages;
	}

	// WebSocket
	let unsubscribeCreated: (() => void) | null = null;
	let unsubscribeUpdated: (() => void) | null = null;

	function setupWebSocket() {
		unsubscribeCreated = wsManager.on(TICKET_CREATED, () => loadTickets());
		unsubscribeUpdated = wsManager.on(TICKET_UPDATED, () => loadTickets());
	}

	function cleanupWebSocket() {
		unsubscribeCreated?.();
		unsubscribeUpdated?.();
		unsubscribeCreated = null;
		unsubscribeUpdated = null;
	}

	onMount(() => {
		loadTickets();
		setupWebSocket();
	});

	onDestroy(() => {
		abortController?.abort();
		cleanupWebSocket();
	});
</script>

<div class="space-y-6">
	<div>
		<h2 class="text-2xl font-bold tracking-tight">{$t('tickets.title')}</h2>
		<p class="text-muted-foreground">{$t('tickets.description')}</p>
	</div>

	<!-- Filter buttons -->
	<div class="flex gap-2 flex-wrap">
		<Button
			variant={statusFilter === null ? 'default' : 'outline'}
			size="sm"
			onclick={() => { statusFilter = null; currentPage = 1; loadTickets(); }}
		>
			{$t('tickets.filters.all')}
		</Button>
		<Button
			variant={statusFilter === 'pending' ? 'default' : 'outline'}
			size="sm"
			onclick={() => { statusFilter = 'pending'; currentPage = 1; loadTickets(); }}
		>
			<Clock class="mr-1 h-3 w-3" />
			{$t('tickets.filters.pending')}
		</Button>
		<Button
			variant={statusFilter === 'processing' ? 'default' : 'outline'}
			size="sm"
			onclick={() => { statusFilter = 'processing'; currentPage = 1; loadTickets(); }}
		>
			<Loader2 class="mr-1 h-3 w-3" />
			{$t('tickets.filters.inProgress')}
		</Button>
		<Button
			variant={statusFilter === 'completed' ? 'default' : 'outline'}
			size="sm"
			onclick={() => { statusFilter = 'completed'; currentPage = 1; loadTickets(); }}
		>
			<CheckCircle class="mr-1 h-3 w-3" />
			{$t('tickets.filters.completed')}
		</Button>
		<Button
			variant={statusFilter === 'rejected' ? 'default' : 'outline'}
			size="sm"
			onclick={() => { statusFilter = 'rejected'; currentPage = 1; loadTickets(); }}
		>
			<XCircle class="mr-1 h-3 w-3" />
			{$t('tickets.filters.rejected')}
		</Button>
	</div>

	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<Card>
		<CardHeader>
			<div class="flex items-center justify-between">
				<CardTitle>{$t('tickets.title')}</CardTitle>
				{#if totalCount > 0}
					<p class="text-sm text-muted-foreground">
						{$t('common.pagination.showing', { start: startIndex, end: endIndex, total: totalCount })}
					</p>
				{/if}
			</div>
		</CardHeader>
		<CardContent>
			{#if isLoading}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-8 w-8 animate-spin text-primary" />
				</div>
			{:else if tickets.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<FileText class="h-12 w-12 text-muted-foreground mb-3" />
					<p class="text-muted-foreground">
						{statusFilter ? $t('tickets.emptyWithStatus', { status: getStatusLabel(statusFilter) }) : $t('tickets.empty')}
					</p>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>{$t('tickets.table.id')}</TableHead>
								<TableHead>{$t('tickets.table.client')}</TableHead>
								<TableHead>{$t('tickets.table.request')}</TableHead>
								<TableHead>{$t('tickets.table.status')}</TableHead>
								<TableHead>{$t('tickets.table.worker')}</TableHead>
								<TableHead>{$t('tickets.table.date')}</TableHead>
								<TableHead>{$t('tickets.table.actions')}</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each tickets as ticket}
								{@const StatusIcon = getStatusIcon(ticket.status)}
								<TableRow>
									<TableCell class="font-mono text-xs">
										{truncate(ticket.id, 8)}
									</TableCell>
									<TableCell class="font-medium">{ticket.username}</TableCell>
									<TableCell>
										<div class="text-sm">
											<span class="font-medium">{ticket.firstname} {ticket.lastname}</span>
											<br />
											<span class="text-muted-foreground text-xs">{truncate(ticket.address, 40)}</span>
										</div>
									</TableCell>
									<TableCell>
										<Badge variant={getStatusBadgeVariant(ticket.status)}>
											<StatusIcon class="mr-1 h-3 w-3" />
											{getStatusLabel(ticket.status)}
										</Badge>
									</TableCell>
									<TableCell>
										{#if ticket.worker_username}
											<span class="font-medium">{ticket.worker_username}</span>
										{:else}
											<span class="text-muted-foreground">-</span>
										{/if}
									</TableCell>
									<TableCell class="text-sm">{formatDateTime(ticket.created_at)}</TableCell>
									<TableCell>
										<div class="flex justify-end gap-1">
											<Button variant="ghost" size="sm" onclick={() => handleViewDetails(ticket)}>
												<Eye class="h-4 w-4" />
											</Button>
											{#if ticket.status === 'pending' || ticket.status === 'processing'}
												<Button variant="ghost" size="sm" onclick={() => handleRespond(ticket)}>
													<Send class="h-4 w-4" />
												</Button>
											{/if}
											{#if (ticket.status === 'pending' || ticket.status === 'processing') && !ticket.worker_id}
												<Button variant="ghost" size="sm" onclick={() => handleAssign(ticket)}>
													<UserCheck class="h-4 w-4" />
												</Button>
											{/if}
										</div>
									</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				</div>

				{#if totalPages > 1}
					<div class="mt-4 flex items-center justify-between border-t pt-4">
						<div class="text-sm text-muted-foreground">{$t('common.pagination.page', { current: currentPage, total: totalPages })}</div>
						<div class="flex items-center gap-2">
							<Button variant="outline" size="sm" onclick={() => goToPage(currentPage - 1)} disabled={currentPage === 1}>
								<ChevronLeft class="h-4 w-4" />
							</Button>
							<div class="flex gap-1">
								{#each getPageNumbers() as pageNum}
									<Button
										variant={currentPage === pageNum ? 'default' : 'outline'}
										size="sm"
										class="w-10"
										onclick={() => goToPage(pageNum)}
									>
										{pageNum}
									</Button>
								{/each}
							</div>
							<Button variant="outline" size="sm" onclick={() => goToPage(currentPage + 1)} disabled={currentPage === totalPages}>
								<ChevronRight class="h-4 w-4" />
							</Button>
						</div>
					</div>
				{/if}
			{/if}
		</CardContent>
	</Card>
</div>

<!-- Details Dialog -->
<Dialog bind:open={showDetailsDialog}>
	<DialogContent class="max-w-2xl">
		<DialogHeader>
			<DialogTitle>{$t('tickets.detail.title')}</DialogTitle>
		</DialogHeader>
		{#if selectedTicket}
			<div class="space-y-4 py-4">
				<div class="grid grid-cols-2 gap-4">
					<div>
						<Label class="text-muted-foreground">{$t('tickets.detail.id')}</Label>
						<p class="font-mono text-sm">{selectedTicket.id}</p>
					</div>
					<div>
						<Label class="text-muted-foreground">{$t('tickets.detail.status')}</Label>
						<div class="mt-1">
							<Badge variant={getStatusBadgeVariant(selectedTicket.status)}>
								{getStatusLabel(selectedTicket.status)}
							</Badge>
						</div>
					</div>
					<div>
						<Label class="text-muted-foreground">{$t('tickets.detail.client')}</Label>
						<p class="text-sm">{selectedTicket.username}</p>
					</div>
					<div>
						<Label class="text-muted-foreground">{$t('tickets.detail.worker')}</Label>
						<p class="text-sm">{selectedTicket.worker_username || '-'}</p>
					</div>
					<div>
						<Label class="text-muted-foreground">{$t('tickets.detail.name')}</Label>
						<p class="text-sm">{selectedTicket.firstname} {selectedTicket.lastname}</p>
					</div>
					<div class="col-span-2">
						<Label class="text-muted-foreground">{$t('tickets.detail.address')}</Label>
						<p class="text-sm">{selectedTicket.address}</p>
					</div>
					{#if selectedTicket.response_data}
						<div class="col-span-2">
							<Label class="text-muted-foreground">{$t('tickets.detail.response')}</Label>
							<div class="mt-2 rounded-md bg-muted p-3 text-sm space-y-1">
								{#if selectedTicket.response_data.ssn}
									<p><span class="text-muted-foreground">SSN:</span> {selectedTicket.response_data.ssn}</p>
								{/if}
								{#if selectedTicket.response_data.dob}
									<p><span class="text-muted-foreground">DOB:</span> {selectedTicket.response_data.dob}</p>
								{/if}
								{#if selectedTicket.response_data.email}
									<p><span class="text-muted-foreground">Email:</span> {selectedTicket.response_data.email}</p>
								{/if}
								{#if selectedTicket.response_data.phone}
									<p><span class="text-muted-foreground">Phone:</span> {selectedTicket.response_data.phone}</p>
								{/if}
							</div>
						</div>
					{/if}
					<div>
						<Label class="text-muted-foreground">{$t('tickets.detail.created')}</Label>
						<p class="text-sm">{formatDateTime(selectedTicket.created_at)}</p>
					</div>
					<div>
						<Label class="text-muted-foreground">{$t('tickets.detail.updated')}</Label>
						<p class="text-sm">{formatDateTime(selectedTicket.updated_at)}</p>
					</div>
				</div>
				<div class="flex justify-end">
					<Button variant="outline" onclick={() => { showDetailsDialog = false; selectedTicket = null; }}>
						{$t('common.close')}
					</Button>
				</div>
			</div>
		{/if}
	</DialogContent>
</Dialog>

<!-- Respond Dialog -->
<Dialog bind:open={showRespondDialog}>
	<DialogContent class="max-w-2xl max-h-[90vh] overflow-y-auto">
		<DialogHeader>
			<DialogTitle>{$t('tickets.reply.title')}</DialogTitle>
		</DialogHeader>
		{#if selectedTicket}
			<div class="space-y-4 py-2">
				<!-- Ticket info -->
				<div class="rounded-md bg-muted p-3 text-sm space-y-1">
					<p><span class="text-muted-foreground">{$t('tickets.reply.client')}</span> {selectedTicket.username}</p>
					<p><span class="text-muted-foreground">{$t('tickets.reply.request')}</span> {selectedTicket.firstname} {selectedTicket.lastname}</p>
					<p><span class="text-muted-foreground">{$t('tickets.reply.address')}</span> {selectedTicket.address}</p>
				</div>

				<!-- Response form -->
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1.5">
						<Label for="r-firstname">First Name</Label>
						<Input id="r-firstname" bind:value={responseFirstname} />
					</div>
					<div class="space-y-1.5">
						<Label for="r-lastname">Last Name</Label>
						<Input id="r-lastname" bind:value={responseLastname} />
					</div>
					<div class="space-y-1.5">
						<Label for="r-middlename">Middle Name</Label>
						<Input id="r-middlename" bind:value={responseMiddlename} />
					</div>
					<div class="space-y-1.5">
						<Label for="r-ssn">SSN *</Label>
						<Input id="r-ssn" bind:value={responseSSN} placeholder="123-45-6789" />
					</div>
					<div class="space-y-1.5">
						<Label for="r-dob">DOB</Label>
						<Input id="r-dob" bind:value={responseDOB} placeholder="YYYYMMDD" />
					</div>
					<div class="space-y-1.5">
						<Label for="r-email">Email</Label>
						<Input id="r-email" bind:value={responseEmail} />
					</div>
					<div class="space-y-1.5">
						<Label for="r-phone">Phone</Label>
						<Input id="r-phone" bind:value={responsePhone} />
					</div>
					<div class="space-y-1.5 col-span-2">
						<Label for="r-address">Address</Label>
						<Input id="r-address" bind:value={responseAddress} />
					</div>
					<div class="space-y-1.5">
						<Label for="r-city">City</Label>
						<Input id="r-city" bind:value={responseCity} />
					</div>
					<div class="space-y-1.5">
						<Label for="r-state">State</Label>
						<Input id="r-state" bind:value={responseState} placeholder="CA" />
					</div>
					<div class="space-y-1.5">
						<Label for="r-zip">ZIP</Label>
						<Input id="r-zip" bind:value={responseZip} />
					</div>
				</div>

				<div class="flex gap-2 pt-2">
					<Button
						class="flex-1"
						onclick={() => submitResponse('completed')}
						disabled={isResponding}
					>
						{#if isResponding}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						{:else}
							<CheckCircle class="mr-2 h-4 w-4" />
						{/if}
						{$t('tickets.reply.complete')}
					</Button>
					<Button
						variant="destructive"
						class="flex-1"
						onclick={() => submitResponse('rejected')}
						disabled={isResponding}
					>
						<Ban class="mr-2 h-4 w-4" />
						{$t('tickets.reply.reject')}
					</Button>
					<Button
						variant="outline"
						onclick={() => { showRespondDialog = false; selectedTicket = null; }}
						disabled={isResponding}
					>
						{$t('common.cancel')}
					</Button>
				</div>
			</div>
		{/if}
	</DialogContent>
</Dialog>

<!-- Assignment Dialog -->
<Dialog bind:open={showAssignDialog}>
	<DialogContent>
		<DialogHeader>
			<DialogTitle>{$t('tickets.assign.title')}</DialogTitle>
		</DialogHeader>
		{#if selectedTicket}
			<div class="space-y-4 py-4">
				<div class="rounded-md bg-muted p-3 text-sm space-y-1">
					<p><span class="text-muted-foreground">{$t('tickets.assign.client')}</span> {selectedTicket.username}</p>
					<p><span class="text-muted-foreground">{$t('tickets.assign.request')}</span> {selectedTicket.firstname} {selectedTicket.lastname}</p>
				</div>

				<div class="space-y-2">
					<Label for="worker-select">{$t('tickets.assign.selectWorker')}</Label>
					<select
						id="worker-select"
						bind:value={selectedWorkerId}
						class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
					>
						<option value="">{$t('tickets.assign.selectPlaceholder')}</option>
						{#each workers as worker}
							<option value={worker.id}>
								{worker.username} ({worker.email})
							</option>
						{/each}
					</select>
				</div>

				<div class="flex gap-2">
					<Button class="flex-1" onclick={confirmAssign} disabled={isAssigning || !selectedWorkerId}>
						{#if isAssigning}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						{/if}
						{$t('tickets.assign.assignButton')}
					</Button>
					<Button
						variant="outline"
						class="flex-1"
						onclick={() => { showAssignDialog = false; selectedTicket = null; selectedWorkerId = ''; }}
						disabled={isAssigning}
					>
						{$t('common.cancel')}
					</Button>
				</div>
			</div>
		{/if}
	</DialogContent>
</Dialog>
