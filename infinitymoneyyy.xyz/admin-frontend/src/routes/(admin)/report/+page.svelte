<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
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
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Eye from '@lucide/svelte/icons/eye';
	import Send from '@lucide/svelte/icons/send';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import {
		getSupportThreads,
		getThreadMessages,
		replyToThread,
		updateThreadStatus,
		markThreadMessagesAsRead,
		handleApiError,
		type ThreadResponse,
		type MessageResponse
	} from '$lib/api/client';
	import { formatDateTime } from '$lib/utils';
	import { toast } from 'svelte-sonner';
	import { t } from '$lib/i18n';
	import { wsManager, THREAD_CREATED, THREAD_MESSAGE_ADDED, THREAD_STATUS_UPDATED } from '$lib/websocket/manager';

	// State
	let threads = $state<ThreadResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let totalCount = $state(0);
	let statusFilter = $state<string | null>(null);

	// Thread detail dialog
	let showThreadDialog = $state(false);
	let selectedThread = $state<ThreadResponse | null>(null);
	let messages = $state<MessageResponse[]>([]);
	let isLoadingMessages = $state(false);
	let replyText = $state('');
	let isSending = $state(false);

	const statusFilters = [
		{ value: null, labelKey: 'report.filters.all' },
		{ value: 'pending', labelKey: 'report.filters.pending' },
		{ value: 'answered', labelKey: 'report.filters.answered' },
		{ value: 'closed', labelKey: 'report.filters.closed' }
	];

	function getStatusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
		switch (status) {
			case 'pending':
				return 'destructive';
			case 'answered':
				return 'secondary';
			case 'closed':
				return 'outline';
			default:
				return 'default';
		}
	}

	async function loadThreads() {
		isLoading = true;
		error = '';
		try {
			const params: Record<string, any> = { limit: 50 };
			if (statusFilter) params.status_filter = statusFilter;
			const data = await getSupportThreads(params);
			threads = data.threads;
			totalCount = data.total_count;
		} catch (err: any) {
			error = handleApiError(err);
		} finally {
			isLoading = false;
		}
	}

	async function openThread(thread: ThreadResponse) {
		selectedThread = thread;
		showThreadDialog = true;
		isLoadingMessages = true;
		messages = [];
		replyText = '';

		try {
			const data = await getThreadMessages(thread.id, { limit: 100 });
			messages = data.messages;
			// Mark as read
			if (thread.unread_count > 0) {
				await markThreadMessagesAsRead(thread.id);
				thread.unread_count = 0;
			}
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isLoadingMessages = false;
		}
	}

	async function sendReply() {
		if (!selectedThread || !replyText.trim()) return;
		isSending = true;
		try {
			await replyToThread(selectedThread.id, { message: replyText.trim() });
			replyText = '';
			toast.success($t('report.replySent'));
			// Message will appear via WebSocket handler (no direct add to avoid duplication)
			await loadThreads();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isSending = false;
		}
	}

	async function closeThread(thread: ThreadResponse) {
		try {
			await updateThreadStatus(thread.id, { status: 'closed' });
			toast.success($t('report.threadClosed'));
			showThreadDialog = false;
			await loadThreads();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// WebSocket subscriptions for real-time updates
	let unsubscribers: (() => void)[] = [];

	onMount(() => {
		loadThreads();

		// New thread created by user
		unsubscribers.push(wsManager.on(THREAD_CREATED, (data: any) => {
			loadThreads();
		}));

		// New message added to a thread
		unsubscribers.push(wsManager.on(THREAD_MESSAGE_ADDED, (data: any) => {
			// If thread dialog is open and it's the same thread, add message (skip if already added by sendReply)
			if (showThreadDialog && selectedThread && data.thread_id === selectedThread.id) {
				const alreadyExists = messages.some(m => m.id === data.message_id);
				if (!alreadyExists) {
					const newMsg: MessageResponse = {
						id: data.message_id,
						thread_id: data.thread_id,
						message: data.message,
						message_type: data.message_type,
						is_read: true,
						created_at: data.created_at,
						sender_username: data.sender_username
					};
					messages = [...messages, newMsg];
				}
			}
			// Reload thread list to update previews
			loadThreads();
		}));

		// Thread status updated
		unsubscribers.push(wsManager.on(THREAD_STATUS_UPDATED, (data: any) => {
			// Update selected thread status if dialog is open
			if (showThreadDialog && selectedThread && data.thread_id === selectedThread.id) {
				selectedThread = { ...selectedThread, status: data.status };
			}
			loadThreads();
		}));
	});

	onDestroy(() => {
		unsubscribers.forEach(fn => fn());
	});
</script>

<div class="space-y-6">
	<div class="flex items-center justify-end">
		<Button variant="outline" onclick={loadThreads}>
			<RefreshCw class="mr-2 h-4 w-4" />
			{$t('common.refresh')}
		</Button>
	</div>

	<!-- Status filters -->
	<div class="flex gap-2">
		{#each statusFilters as filter}
			<Button
				variant={statusFilter === filter.value ? 'default' : 'outline'}
				size="sm"
				onclick={() => {
					statusFilter = filter.value;
					loadThreads();
				}}
			>
				{$t(filter.labelKey)}
			</Button>
		{/each}
	</div>

	<!-- Error -->
	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- Threads table -->
	<Card>
		<CardHeader>
			<CardTitle class="flex items-center justify-between">
				<span>{$t('report.title')}</span>
				<span class="text-sm font-normal text-muted-foreground">{$t('report.total', { values: { count: totalCount } })}</span>
			</CardTitle>
		</CardHeader>
		<CardContent>
			{#if isLoading}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
				</div>
			{:else if threads.length === 0}
				<p class="py-8 text-center text-muted-foreground">{$t('report.noThreads')}</p>
			{:else}
				<Table>
					<TableHeader>
						<TableRow class="hover:bg-transparent">
							<TableHead class="text-foreground font-semibold"></TableHead>
							<TableHead class="text-foreground font-semibold">{$t('report.table.user')}</TableHead>
							<TableHead class="text-foreground font-semibold">{$t('report.table.subject')}</TableHead>
							<TableHead class="text-foreground font-semibold">{$t('report.table.status')}</TableHead>
							<TableHead class="text-foreground font-semibold">{$t('report.table.unread')}</TableHead>
							<TableHead class="text-foreground font-semibold">{$t('report.table.lastMessage')}</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each threads as thread}
							<TableRow class={thread.unread_count > 0 ? 'bg-primary/5' : ''}>
								<TableCell>
									<Button
										variant="ghost"
										size="icon"
										onclick={() => openThread(thread)}
										title={$t('report.viewThread')}
									>
										<Eye class="h-4 w-4" />
									</Button>
								</TableCell>
								<TableCell class="font-medium">{thread.username}</TableCell>
								<TableCell>
									<p class="text-sm font-medium">{thread.subject || $t('report.noSubject')}</p>
									{#if thread.last_message_preview}
										<p class="text-xs text-muted-foreground">
											{thread.last_message_preview}
										</p>
									{/if}
								</TableCell>
								<TableCell>
									<Badge variant={getStatusVariant(thread.status)}>
										{thread.status}
									</Badge>
								</TableCell>
								<TableCell>
									{#if thread.unread_count > 0}
										<Badge variant="destructive">{thread.unread_count}</Badge>
									{:else}
										<span class="text-muted-foreground">0</span>
									{/if}
								</TableCell>
								<TableCell class="text-sm text-muted-foreground">
									{formatDateTime(thread.last_message_at)}
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
			{/if}
		</CardContent>
	</Card>
</div>

<!-- Thread Detail Dialog -->
<Dialog bind:open={showThreadDialog}>
	<DialogContent class="sm:max-w-2xl max-h-[80vh] flex flex-col">
		<DialogHeader>
			<DialogTitle class="flex items-center justify-between">
				<span>{selectedThread?.subject || 'Thread'}</span>
				{#if selectedThread}
					<div class="flex items-center gap-2 mr-8">
						<Badge variant={getStatusVariant(selectedThread.status)}>
							{selectedThread.status}
						</Badge>
						{#if selectedThread.status !== 'closed'}
							<Button
								variant="outline"
								size="sm"
								onclick={() => selectedThread && closeThread(selectedThread)}
							>
								{$t('common.close')}
							</Button>
						{/if}
					</div>
				{/if}
			</DialogTitle>
			{#if selectedThread}
				<p class="text-sm text-muted-foreground">
					{$t('report.from', { values: { username: selectedThread.username } })}
				</p>
			{/if}
		</DialogHeader>

		<!-- Messages -->
		<div class="flex-1 overflow-y-auto space-y-3 py-4 min-h-[200px] max-h-[400px]">
			{#if isLoadingMessages}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
				</div>
			{:else}
				{#each messages as msg}
					<div
						class="rounded-lg px-4 py-3 text-sm {msg.message_type === 'admin'
							? 'ml-8 bg-primary/10 border border-primary/20'
							: 'mr-8 bg-muted'}"
					>
						<div class="mb-1 flex items-center justify-between">
							<span class="font-medium text-xs">
								{msg.message_type === 'admin' ? msg.sender_username || 'Admin' : msg.sender_username || 'User'}
							</span>
							<span class="text-xs text-muted-foreground">
								{formatDateTime(msg.created_at)}
							</span>
						</div>
						<p class="whitespace-pre-wrap">{msg.message}</p>
					</div>
				{/each}

				{#if messages.length === 0}
					<p class="py-4 text-center text-sm text-muted-foreground">{$t('report.noMessages')}</p>
				{/if}
			{/if}
		</div>

		<!-- Reply form -->
		{#if selectedThread && selectedThread.status !== 'closed'}
			<div class="flex gap-2 border-t pt-4">
				<textarea
					bind:value={replyText}
					placeholder={$t('report.replyPlaceholder')}
					rows="2"
					class="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
				></textarea>
				<Button
					onclick={sendReply}
					disabled={isSending || !replyText.trim()}
					class="self-end"
				>
					{#if isSending}
						<Loader2 class="h-4 w-4 animate-spin" />
					{:else}
						<Send class="h-4 w-4" />
					{/if}
				</Button>
			</div>
		{/if}
	</DialogContent>
</Dialog>
