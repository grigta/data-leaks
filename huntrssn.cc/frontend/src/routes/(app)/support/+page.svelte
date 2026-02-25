<script lang="ts">
	import { onMount } from 'svelte';
	import { Send, MessageCircle, Loader2, Plus, Bug, Lightbulb, HelpCircle, Clock, Lock } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { t } from '$lib/i18n';
	import { user } from '$lib/stores/auth';
	import {
		createSupportThread,
		getSupportThreads,
		getThreadMessages,
		addThreadMessage,
		markThreadMessagesAsRead,
		type ThreadResponse,
		type MessageResponse
	} from '$lib/api/client';
	import { wsManager, THREAD_CREATED, THREAD_MESSAGE_ADDED, THREAD_STATUS_UPDATED } from '$lib/websocket/client';
	import { Button } from '$lib/components/ui/button';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import {
		Dialog,
		DialogContent,
		DialogHeader,
		DialogTitle,
		DialogDescription
	} from '$lib/components/ui/dialog';

	// State
	let threads = $state<ThreadResponse[]>([]);
	let selectedThread = $state<ThreadResponse | null>(null);
	let messages = $state<MessageResponse[]>([]);
	let newMessage = $state('');
	let newThreadSubject = $state('');
	let selectedMessageType = $state<'bug_report' | 'feature_request' | 'general_question'>('general_question');
	let isLoadingThreads = $state(false);
	let isLoadingMessages = $state(false);
	let isSending = $state(false);
	let showNewThreadDialog = $state(false);
	let showTicketDetailDialog = $state(false);
	let messagesContainer: HTMLDivElement;

	// Derived — kanban columns
	let pendingThreads = $derived(threads.filter(t => t.status === 'pending'));
	let answeredThreads = $derived(threads.filter(t => t.status === 'answered'));
	let closedThreads = $derived(threads.filter(t => t.status === 'closed'));

	// ── Data loading ──

	async function loadThreads() {
		isLoadingThreads = true;
		try {
			const response = await getSupportThreads({ limit: 100 });
			threads = response.threads;
		} catch (error) {
			toast.error($t('support.loadError'));
			console.error(error);
		} finally {
			isLoadingThreads = false;
		}
	}

	async function loadThreadMessages(threadId: string) {
		isLoadingMessages = true;
		try {
			const response = await getThreadMessages(threadId, { limit: 100 });
			messages = response.messages;
			setTimeout(scrollToBottom, 100);

			// Mark messages as read
			await markThreadMessagesAsRead(threadId);

			// Update unread count in local thread
			const threadIndex = threads.findIndex(t => t.id === threadId);
			if (threadIndex !== -1) {
				threads[threadIndex] = { ...threads[threadIndex], unread_count: 0 };
			}
		} catch (error) {
			toast.error($t('support.loadError'));
			console.error(error);
		} finally {
			isLoadingMessages = false;
		}
	}

	// ── Ticket actions ──

	async function openTicketDetail(thread: ThreadResponse) {
		selectedThread = thread;
		showTicketDetailDialog = true;
		await loadThreadMessages(thread.id);
	}

	function closeTicketDetail() {
		showTicketDetailDialog = false;
		selectedThread = null;
		messages = [];
		newMessage = '';
	}

	function openNewThreadDialog() {
		showNewThreadDialog = true;
		newMessage = '';
		newThreadSubject = '';
	}

	async function createNewThread() {
		if (!newMessage.trim() || isSending) return;

		isSending = true;
		try {
			const response = await createSupportThread({
				message: newMessage,
				message_type: selectedMessageType,
				subject: newThreadSubject.trim() || null
			});

			// Add new thread to the list
			threads = [response, ...threads];

			// Reset form & close dialog
			newMessage = '';
			newThreadSubject = '';
			showNewThreadDialog = false;

			toast.success($t('support.sendSuccess'));

			// Open the newly created thread
			await openTicketDetail(response);
		} catch (error) {
			toast.error($t('support.sendError'));
			console.error(error);
		} finally {
			isSending = false;
		}
	}

	async function sendMessage() {
		if (!newMessage.trim() || isSending || !selectedThread) return;

		isSending = true;
		try {
			const response = await addThreadMessage(selectedThread.id, { message: newMessage });
			messages = [...messages, response];
			newMessage = '';

			// Update thread last_message_at
			const threadIndex = threads.findIndex(t => t.id === selectedThread!.id);
			if (threadIndex !== -1) {
				threads[threadIndex] = {
					...threads[threadIndex],
					last_message_at: response.created_at,
					last_message_preview: response.message.substring(0, 100)
				};
			}

			toast.success($t('support.sendSuccess'));
			setTimeout(scrollToBottom, 100);
		} catch (error) {
			toast.error($t('support.sendError'));
			console.error(error);
		} finally {
			isSending = false;
		}
	}

	// ── Helpers ──

	function scrollToBottom() {
		if (messagesContainer) {
			messagesContainer.scrollTop = messagesContainer.scrollHeight;
		}
	}

	function handleKeyPress(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			if (showNewThreadDialog) {
				createNewThread();
			} else if (showTicketDetailDialog && selectedThread) {
				sendMessage();
			}
		}
	}

	function formatDate(dateString: string): string {
		const date = new Date(dateString);
		const now = new Date();
		const diff = now.getTime() - date.getTime();
		const minutes = Math.floor(diff / (1000 * 60));
		const hours = Math.floor(diff / (1000 * 60 * 60));
		const days = Math.floor(diff / (1000 * 60 * 60 * 24));

		if (minutes < 1) return $t('common.justNow');
		if (minutes < 60) return `${minutes} ${$t('common.minutesAgo')}`;
		if (hours < 24) return `${hours} ${$t('common.hoursAgo')}`;
		if (days === 1) return $t('common.yesterday');
		if (days < 7) return `${days} ${$t('common.daysAgo')}`;
		return date.toLocaleDateString();
	}

	function getMessageTypeLabel(type: string): string {
		switch (type) {
			case 'bug_report':
				return $t('support.bugReport');
			case 'feature_request':
				return $t('support.featureRequest');
			case 'general_question':
				return $t('support.generalQuestion');
			default:
				return type;
		}
	}

	function getMessageTypeIcon(type: string) {
		switch (type) {
			case 'bug_report':
				return Bug;
			case 'feature_request':
				return Lightbulb;
			case 'general_question':
				return HelpCircle;
			default:
				return MessageCircle;
		}
	}

	function getMessageTypeBadgeVariant(type: string): 'default' | 'secondary' | 'destructive' | 'outline' {
		switch (type) {
			case 'bug_report':
				return 'destructive';
			case 'feature_request':
				return 'default';
			case 'general_question':
				return 'secondary';
			default:
				return 'outline';
		}
	}

	function getStatusDotClass(status: string): string {
		switch (status) {
			case 'pending':
				return 'bg-warning';
			case 'answered':
				return 'bg-success';
			default:
				return 'bg-muted-foreground';
		}
	}

	function formatMessageTime(dateString: string): string {
		const date = new Date(dateString);
		return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	function formatMessageDate(dateString: string): string {
		const date = new Date(dateString);
		const now = new Date();
		const diff = now.getTime() - date.getTime();
		const days = Math.floor(diff / (1000 * 60 * 60 * 24));

		if (days === 0) return $t('support.today');
		if (days === 1) return $t('common.yesterday');
		return date.toLocaleDateString();
	}

	function shouldShowDateSeparator(messages: MessageResponse[], index: number): boolean {
		if (index === 0) return true;
		const currentDate = new Date(messages[index].created_at).toDateString();
		const prevDate = new Date(messages[index - 1].created_at).toDateString();
		return currentDate !== prevDate;
	}

	function getUserInitial(username?: string): string {
		if (!username) return 'U';
		return username.charAt(0).toUpperCase();
	}

	// ── Lifecycle & WebSocket ──

	onMount(() => {
		loadThreads();

		const unsubscribeThreadCreated = wsManager.on(THREAD_CREATED, () => {
			loadThreads();
		});

		const unsubscribeMessageAdded = wsManager.on(THREAD_MESSAGE_ADDED, (data: any) => {
			if (selectedThread && data.thread_id === selectedThread.id) {
				const newMsg: MessageResponse = {
					id: data.message_id,
					thread_id: data.thread_id,
					message: data.message,
					message_type: data.message_type,
					is_read: data.message_type === 'user',
					created_at: data.created_at,
					sender_username: data.sender_username
				};
				messages = [...messages, newMsg];
				setTimeout(scrollToBottom, 100);

				if (data.message_type === 'admin') {
					markThreadMessagesAsRead(selectedThread.id);
				}
			}

			const threadIndex = threads.findIndex(t => t.id === data.thread_id);
			if (threadIndex !== -1) {
				threads[threadIndex] = {
					...threads[threadIndex],
					last_message_at: data.created_at,
					last_message_preview: data.message.substring(0, 100),
					unread_count: data.message_type === 'admin' ? threads[threadIndex].unread_count + 1 : threads[threadIndex].unread_count
				};
			}
		});

		const unsubscribeStatusUpdated = wsManager.on(THREAD_STATUS_UPDATED, (data: any) => {
			const threadIndex = threads.findIndex(t => t.id === data.thread_id);
			if (threadIndex !== -1) {
				threads[threadIndex] = { ...threads[threadIndex], status: data.status };
			}

			if (selectedThread && selectedThread.id === data.thread_id) {
				selectedThread = { ...selectedThread, status: data.status };
			}
		});

		return () => {
			unsubscribeThreadCreated();
			unsubscribeMessageAdded();
			unsubscribeStatusUpdated();
		};
	});
</script>

<!-- ═══ Page Layout ═══ -->
<div class="container mx-auto max-w-7xl space-y-6 p-6">
	<!-- Top Bar -->
	<div class="flex items-center justify-between">
		<div class="flex items-center gap-4">
			<h1 class="text-3xl font-bold">{$t('support.title')}</h1>
			{#if !isLoadingThreads}
				<div class="flex items-center gap-4">
					<div class="flex items-center gap-1.5 text-sm text-muted-foreground">
						<div class="h-2.5 w-2.5 rounded-full bg-warning"></div>
						<span>{pendingThreads.length}</span>
					</div>
					<div class="flex items-center gap-1.5 text-sm text-muted-foreground">
						<div class="h-2.5 w-2.5 rounded-full bg-success"></div>
						<span>{answeredThreads.length}</span>
					</div>
					<div class="flex items-center gap-1.5 text-sm text-muted-foreground">
						<div class="h-2.5 w-2.5 rounded-full bg-muted-foreground"></div>
						<span>{closedThreads.length}</span>
					</div>
				</div>
			{/if}
		</div>
		<Button onclick={openNewThreadDialog}>
			<Plus class="h-4 w-4 mr-2" />
			{$t('support.newTicket')}
		</Button>
	</div>

	<!-- Kanban Board -->
	{#if isLoadingThreads}
		<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
			{#each Array(3) as _}
				<div class="border border-border rounded-lg p-4 space-y-3">
					<Skeleton class="h-6 w-32" />
					{#each Array(2) as _}
						<Skeleton class="h-28 w-full" />
					{/each}
				</div>
			{/each}
		</div>
	{:else}
		<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
			<!-- Pending Column -->
			{@render kanbanColumn(
				$t('support.pendingColumn'),
				'bg-warning',
				pendingThreads,
				false
			)}

			<!-- Answered Column -->
			{@render kanbanColumn(
				$t('support.answeredColumn'),
				'bg-success',
				answeredThreads,
				false
			)}

			<!-- Closed Column -->
			{@render kanbanColumn(
				$t('support.closedColumn'),
				'bg-muted-foreground',
				closedThreads,
				true
			)}
		</div>
	{/if}
</div>

<!-- ═══ Kanban Column Snippet ═══ -->
{#snippet kanbanColumn(title: string, dotClass: string, columnThreads: ThreadResponse[], dimmed: boolean)}
	<div class="border border-border rounded-lg flex flex-col min-h-[200px] max-h-[calc(100vh-14rem)]">
		<!-- Column header -->
		<div class="flex items-center justify-between px-4 py-3 border-b border-border">
			<div class="flex items-center gap-2">
				<div class="h-2.5 w-2.5 rounded-full {dotClass}"></div>
				<span class="text-sm font-semibold">{title}</span>
			</div>
			<Badge variant="outline" class="text-xs font-mono">{columnThreads.length}</Badge>
		</div>

		<!-- Column body -->
		<div class="flex-1 overflow-y-auto p-2 space-y-2">
			{#if columnThreads.length === 0}
				<div class="flex items-center justify-center py-8 text-muted-foreground">
					<p class="text-sm">{$t('support.noTicketsInColumn')}</p>
				</div>
			{:else}
				{#each columnThreads as thread (thread.id)}
					{@const Icon = getMessageTypeIcon(thread.message_type)}
					<button
						onclick={() => openTicketDetail(thread)}
						class="w-full text-left p-3 border border-border rounded-lg transition-colors hover:border-muted-foreground/50 hover:bg-accent/50 {dimmed ? 'opacity-60' : ''}"
					>
						<!-- Type badge + unread -->
						<div class="flex items-center justify-between mb-2">
							<Badge variant={getMessageTypeBadgeVariant(thread.message_type)} class="text-xs">
								<Icon class="h-3 w-3 mr-1" />
								{getMessageTypeLabel(thread.message_type)}
							</Badge>
							{#if thread.unread_count > 0}
								<Badge variant="destructive" class="text-xs">
									{thread.unread_count}
								</Badge>
							{/if}
						</div>

						<!-- Subject -->
						<p class="font-medium text-sm truncate mb-1">
							{thread.subject || $t('support.noSubject')}
						</p>

						<!-- Preview -->
						<p class="text-xs text-muted-foreground line-clamp-2 mb-2">
							{thread.last_message_preview || ''}
						</p>

						<!-- Date -->
						<div class="flex items-center justify-between">
							<span class="text-xs text-muted-foreground">
								{formatDate(thread.last_message_at)}
							</span>
						</div>
					</button>
				{/each}
			{/if}
		</div>
	</div>
{/snippet}

<!-- ═══ Ticket Detail Dialog (Chat) ═══ -->
<Dialog
	open={showTicketDetailDialog}
	onOpenChange={(val) => { if (!val) closeTicketDetail(); }}
>
	<DialogContent class="max-w-2xl max-h-[85vh] flex flex-col p-0 gap-0">
		{#if selectedThread}
			{@const Icon = getMessageTypeIcon(selectedThread.message_type)}

			<!-- Chat Header -->
			<div class="px-5 py-4 border-b border-border">
				<DialogHeader>
					<div class="flex items-center gap-3">
						<div class="flex items-center gap-2 flex-1 min-w-0">
							<div class="h-2.5 w-2.5 rounded-full flex-shrink-0 {getStatusDotClass(selectedThread.status)}"></div>
							<DialogTitle class="text-base truncate">{selectedThread.subject || $t('support.noSubject')}</DialogTitle>
						</div>
					</div>
					<DialogDescription>
						<div class="flex items-center gap-2 mt-2 flex-wrap">
							<Badge variant={getMessageTypeBadgeVariant(selectedThread.message_type)} class="text-xs">
								<Icon class="h-3 w-3 mr-1" />
								{getMessageTypeLabel(selectedThread.message_type)}
							</Badge>
							<Badge variant="outline" class="text-xs">
								{$t(`support.${selectedThread.status}`)}
							</Badge>
							<div class="flex items-center gap-1 text-xs text-muted-foreground ml-auto">
								<Clock class="h-3 w-3" />
								{formatDate(selectedThread.created_at)}
							</div>
						</div>
					</DialogDescription>
				</DialogHeader>
			</div>

			<!-- Chat Messages -->
			<div
				bind:this={messagesContainer}
				class="flex-1 overflow-y-auto px-5 py-4 space-y-1 min-h-[300px] bg-muted/20"
			>
				{#if isLoadingMessages}
					<div class="flex items-center justify-center h-32">
						<Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
					</div>
				{:else if messages.length === 0}
					<div class="flex flex-col items-center justify-center h-32 text-center text-muted-foreground gap-2">
						<MessageCircle class="h-8 w-8 opacity-40" />
						<p class="text-sm">{$t('support.noMessages')}</p>
					</div>
				{:else}
					{#each messages as message, i}
						<!-- Date separator -->
						{#if shouldShowDateSeparator(messages, i)}
							<div class="flex items-center gap-3 py-3">
								<div class="flex-1 h-px bg-border"></div>
								<span class="text-xs text-muted-foreground font-medium px-2">
									{formatMessageDate(message.created_at)}
								</span>
								<div class="flex-1 h-px bg-border"></div>
							</div>
						{/if}

						{#if message.message_type === 'user'}
							<!-- User message (right) -->
							<div class="flex items-end gap-2 justify-end group">
								<div class="max-w-[75%] space-y-0.5">
									<div class="bg-primary text-primary-foreground rounded-2xl rounded-br-md px-4 py-2.5">
										<p class="whitespace-pre-wrap break-words text-sm">{message.message}</p>
									</div>
									<div class="flex items-center gap-1 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
										<span class="text-[11px] text-muted-foreground">
											{formatMessageTime(message.created_at)}
										</span>
									</div>
								</div>
								<div class="flex-shrink-0 h-7 w-7 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-semibold">
									{getUserInitial($user?.username)}
								</div>
							</div>
						{:else}
							<!-- Admin message (left) -->
							<div class="flex items-end gap-2 group">
								<div class="flex-shrink-0 h-7 w-7 rounded-full bg-muted border border-border flex items-center justify-center text-xs font-semibold text-muted-foreground">
									S
								</div>
								<div class="max-w-[75%] space-y-0.5">
									<div class="bg-background border border-border rounded-2xl rounded-bl-md px-4 py-2.5">
										<p class="text-xs font-semibold text-muted-foreground mb-1">{message.sender_username || $t('support.supportTeam')}</p>
										<p class="whitespace-pre-wrap break-words text-sm">{message.message}</p>
									</div>
									<div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
										<span class="text-[11px] text-muted-foreground">
											{formatMessageTime(message.created_at)}
										</span>
									</div>
								</div>
							</div>
						{/if}
					{/each}
				{/if}
			</div>

			<!-- Chat Input -->
			<div class="px-5 py-4 border-t border-border bg-background">
				{#if selectedThread.status !== 'closed'}
					<div class="flex items-end gap-2">
						<Textarea
							bind:value={newMessage}
							onkeydown={handleKeyPress}
							placeholder={$t('support.replyPlaceholder')}
							class="resize-none min-h-[42px] rounded-xl"
							rows={1}
							disabled={isSending}
						/>
						<Button
							onclick={() => sendMessage()}
							disabled={!newMessage.trim() || isSending}
							size="icon"
							class="h-[42px] w-[42px] rounded-xl flex-shrink-0"
						>
							{#if isSending}
								<Loader2 class="h-4 w-4 animate-spin" />
							{:else}
								<Send class="h-4 w-4" />
							{/if}
						</Button>
					</div>
				{:else}
					<div class="flex items-center justify-center gap-2 text-muted-foreground p-3 border border-border bg-muted/30 rounded-xl text-sm">
						<Lock class="h-4 w-4" />
						{$t('support.threadClosed')}
					</div>
				{/if}
			</div>
		{/if}
	</DialogContent>
</Dialog>

<!-- ═══ New Thread Dialog ═══ -->
<Dialog
	open={showNewThreadDialog}
	onOpenChange={(val) => { if (!val) showNewThreadDialog = false; }}
>
	<DialogContent class="max-w-lg p-0 gap-0">
		<div class="px-6 pt-6 pb-4 border-b border-border">
			<DialogHeader>
				<DialogTitle class="flex items-center gap-2">
					<Plus class="h-5 w-5" />
					{$t('support.newTicket')}
				</DialogTitle>
				<DialogDescription>{$t('support.description')}</DialogDescription>
			</DialogHeader>
		</div>

		<div class="px-6 py-5 space-y-5">
			<!-- Subject -->
			<div>
				<label class="text-sm font-medium mb-1.5 block">{$t('support.subject')}</label>
				<Input
					bind:value={newThreadSubject}
					placeholder={$t('support.subjectPlaceholder')}
					disabled={isSending}
				/>
			</div>

			<!-- Message -->
			<div>
				<label class="text-sm font-medium mb-1.5 block">{$t('support.message')}</label>
				<Textarea
					bind:value={newMessage}
					onkeydown={handleKeyPress}
					placeholder={$t('support.messagePlaceholder')}
					class="resize-none"
					rows={5}
					disabled={isSending}
				/>
			</div>
		</div>

		<!-- Footer -->
		<div class="px-6 py-4 border-t border-border bg-muted/30">
			<Button
				onclick={() => createNewThread()}
				disabled={!newMessage.trim() || isSending}
				class="w-full"
			>
				{#if isSending}
					<Loader2 class="h-4 w-4 mr-2 animate-spin" />
				{:else}
					<Send class="h-4 w-4 mr-2" />
				{/if}
				{$t('support.createThread')}
			</Button>
		</div>
	</DialogContent>
</Dialog>
