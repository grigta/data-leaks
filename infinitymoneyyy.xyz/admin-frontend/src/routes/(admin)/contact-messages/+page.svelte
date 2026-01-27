<script lang="ts">
	import { onMount } from 'svelte';
	import { Send, MessageCircle, Loader2, Bug, Lightbulb, X } from 'lucide-svelte';
	import { toast } from 'svelte-sonner';
	import {
		getContactThreads,
		getContactThreadMessages,
		replyToContactThread,
		updateContactThreadStatus,
		markContactThreadMessagesAsRead,
		type ContactThreadResponse,
		type ContactMessageResponse
	} from '$lib/api/client';
	import {
		wsManager,
		CONTACT_THREAD_CREATED,
		CONTACT_THREAD_MESSAGE_ADDED,
		CONTACT_THREAD_STATUS_UPDATED
	} from '$lib/websocket/manager';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Badge } from '$lib/components/ui/badge';
	import { ScrollArea } from '$lib/components/ui/scroll-area';

	let threads = $state<ContactThreadResponse[]>([]);
	let selectedThread = $state<ContactThreadResponse | null>(null);
	let messages = $state<ContactMessageResponse[]>([]);
	let responseText = $state('');
	let isLoadingThreads = $state(false);
	let isLoadingMessages = $state(false);
	let isSending = $state(false);
	let statusFilter = $state<string | null>(null);
	let messageTypeFilter = $state<string | null>(null);
	let unreadOnly = $state(false);
	let messagesContainer: HTMLDivElement;

	async function loadThreads() {
		isLoadingThreads = true;
		try {
			const params: any = { limit: 100 };
			if (statusFilter) params.status_filter = statusFilter;
			if (messageTypeFilter) params.message_type_filter = messageTypeFilter;
			if (unreadOnly) params.unread_only = true;

			const response = await getContactThreads(params);
			threads = response.threads;
		} catch (error) {
			toast.error('Failed to load threads');
			console.error(error);
		} finally {
			isLoadingThreads = false;
		}
	}

	async function loadThreadMessages(threadId: string) {
		isLoadingMessages = true;
		try {
			const response = await getContactThreadMessages(threadId, { limit: 100 });
			messages = response.messages;
			setTimeout(scrollToBottom, 100);

			// Mark messages as read
			await markContactThreadMessagesAsRead(threadId);

			// Update unread count in local thread
			const threadIndex = threads.findIndex((t) => t.id === threadId);
			if (threadIndex !== -1) {
				threads[threadIndex] = { ...threads[threadIndex], unread_count: 0 };
			}
		} catch (error) {
			toast.error('Failed to load messages');
			console.error(error);
		} finally {
			isLoadingMessages = false;
		}
	}

	async function selectThread(thread: ContactThreadResponse) {
		selectedThread = thread;
		responseText = '';
		await loadThreadMessages(thread.id);
	}

	async function sendResponse() {
		if (!responseText.trim() || isSending || !selectedThread) return;

		isSending = true;
		try {
			const response = await replyToContactThread(selectedThread.id, { message: responseText });
			messages = [...messages, response];
			responseText = '';

			// Update thread last_message_at and status
			const threadIndex = threads.findIndex((t) => t.id === selectedThread!.id);
			if (threadIndex !== -1) {
				threads[threadIndex] = {
					...threads[threadIndex],
					last_message_at: response.created_at,
					last_message_preview: response.message.substring(0, 100),
					status: 'answered',
					unread_count: 0
				};
			}

			toast.success('Response sent');
			setTimeout(scrollToBottom, 100);
		} catch (error) {
			toast.error('Failed to send response');
			console.error(error);
		} finally {
			isSending = false;
		}
	}

	async function changeThreadStatus(status: 'pending' | 'answered' | 'closed') {
		if (!selectedThread) return;

		try {
			await updateContactThreadStatus(selectedThread.id, { status });

			// Update thread in list
			const threadIndex = threads.findIndex((t) => t.id === selectedThread!.id);
			if (threadIndex !== -1) {
				threads[threadIndex] = { ...threads[threadIndex], status };
			}

			// Update selected thread
			selectedThread = { ...selectedThread, status };

			toast.success(`Thread ${status}`);
		} catch (error) {
			toast.error('Failed to update thread status');
			console.error(error);
		}
	}

	function scrollToBottom() {
		if (messagesContainer) {
			messagesContainer.scrollTop = messagesContainer.scrollHeight;
		}
	}

	function handleKeyPress(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			sendResponse();
		}
	}

	function formatDate(dateString: string): string {
		const date = new Date(dateString);
		const now = new Date();
		const diff = now.getTime() - date.getTime();
		const days = Math.floor(diff / (1000 * 60 * 60 * 24));

		if (days === 0) {
			return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
		} else if (days === 1) {
			return 'Yesterday';
		} else if (days < 7) {
			return `${days} days ago`;
		} else {
			return date.toLocaleDateString();
		}
	}

	function getStatusBadgeVariant(status: string): 'default' | 'secondary' | 'destructive' {
		switch (status) {
			case 'pending':
				return 'secondary';
			case 'answered':
				return 'default';
			case 'closed':
				return 'destructive';
			default:
				return 'secondary';
		}
	}

	onMount(() => {
		loadThreads();

		// Subscribe to WebSocket events
		const unsubscribeThreadCreated = wsManager.on(CONTACT_THREAD_CREATED, (data) => {
			toast.info('New contact thread created');
			loadThreads();
		});

		const unsubscribeMessageAdded = wsManager.on(CONTACT_THREAD_MESSAGE_ADDED, (data) => {
			// If message is for current thread, add it to messages
			if (selectedThread && data.thread_id === selectedThread.id) {
				const newMsg: ContactMessageResponse = {
					id: data.message_id,
					thread_id: data.thread_id,
					message: data.message,
					message_type: data.message_type,
					is_read: data.message_type === 'admin',
					created_at: data.created_at,
					sender_username: data.sender_username
				};
				messages = [...messages, newMsg];
				setTimeout(scrollToBottom, 100);

				// Mark as read if it's a user message
				if (data.message_type === 'user') {
					markContactThreadMessagesAsRead(selectedThread.id);
				}
			}

			// Update thread in list
			const threadIndex = threads.findIndex((t) => t.id === data.thread_id);
			if (threadIndex !== -1) {
				const updatedThread = {
					...threads[threadIndex],
					last_message_at: data.created_at,
					last_message_preview: data.message.substring(0, 100)
				};

				// Increment unread count if it's a user message and not current thread
				if (data.message_type === 'user' && (!selectedThread || selectedThread.id !== data.thread_id)) {
					updatedThread.unread_count = (updatedThread.unread_count || 0) + 1;
				}

				threads[threadIndex] = updatedThread;

				// Move thread to top
				threads = [updatedThread, ...threads.filter((t) => t.id !== data.thread_id)];
			}
		});

		const unsubscribeStatusUpdated = wsManager.on(CONTACT_THREAD_STATUS_UPDATED, (data) => {
			// Update thread status
			const threadIndex = threads.findIndex((t) => t.id === data.thread_id);
			if (threadIndex !== -1) {
				threads[threadIndex] = {
					...threads[threadIndex],
					status: data.status
				};
			}

			// Update selected thread
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

<div class="container mx-auto max-w-full p-4 h-[calc(100vh-8rem)]">
	<Card class="h-full flex flex-col">
		<CardHeader>
			<CardTitle class="flex items-center gap-2">
				<MessageCircle class="h-6 w-6" />
				Contact Messages
			</CardTitle>
		</CardHeader>
		<CardContent class="flex-1 flex gap-4 p-4 min-h-0">
			<!-- Threads List (Left Panel) -->
			<div class="w-96 flex flex-col gap-4 border-r pr-4">
				<!-- Filters -->
				<div class="space-y-3">
					<div>
						<p class="text-sm font-semibold mb-2">Status</p>
						<div class="flex flex-wrap gap-2">
							<Button
								variant={statusFilter === null ? 'default' : 'outline'}
								size="sm"
								onclick={() => {
									statusFilter = null;
									loadThreads();
								}}
							>
								All
							</Button>
							<Button
								variant={statusFilter === 'pending' ? 'default' : 'outline'}
								size="sm"
								onclick={() => {
									statusFilter = 'pending';
									loadThreads();
								}}
							>
								Pending
							</Button>
							<Button
								variant={statusFilter === 'answered' ? 'default' : 'outline'}
								size="sm"
								onclick={() => {
									statusFilter = 'answered';
									loadThreads();
								}}
							>
								Answered
							</Button>
							<Button
								variant={statusFilter === 'closed' ? 'default' : 'outline'}
								size="sm"
								onclick={() => {
									statusFilter = 'closed';
									loadThreads();
								}}
							>
								Closed
							</Button>
						</div>
					</div>

					<div>
						<p class="text-sm font-semibold mb-2">Type</p>
						<div class="flex flex-wrap gap-2">
							<Button
								variant={messageTypeFilter === null ? 'default' : 'outline'}
								size="sm"
								onclick={() => {
									messageTypeFilter = null;
									loadThreads();
								}}
							>
								All
							</Button>
							<Button
								variant={messageTypeFilter === 'bug_report' ? 'default' : 'outline'}
								size="sm"
								onclick={() => {
									messageTypeFilter = 'bug_report';
									loadThreads();
								}}
							>
								Bug Reports
							</Button>
							<Button
								variant={messageTypeFilter === 'feature_request' ? 'default' : 'outline'}
								size="sm"
								onclick={() => {
									messageTypeFilter = 'feature_request';
									loadThreads();
								}}
							>
								Features
							</Button>
						</div>
					</div>

					<div class="flex items-center gap-2">
						<input
							type="checkbox"
							id="unread-only"
							bind:checked={unreadOnly}
							onchange={() => loadThreads()}
							class="rounded"
						/>
						<label for="unread-only" class="text-sm font-medium cursor-pointer">Unread Only</label>
					</div>
				</div>

				<ScrollArea class="flex-1">
					{#if isLoadingThreads}
						<div class="flex justify-center py-8">
							<Loader2 class="h-8 w-8 animate-spin" />
						</div>
					{:else if threads.length === 0}
						<p class="text-center text-muted-foreground py-8 text-sm">No threads found</p>
					{:else}
						<div class="space-y-2">
							{#each threads as thread}
								<button
									class="w-full text-left p-3 rounded-lg border {selectedThread?.id === thread.id
										? 'bg-primary/10 border-primary'
										: 'hover:bg-muted'}"
									onclick={() => selectThread(thread)}
								>
									<div class="flex items-center gap-2 mb-2">
										<span class="text-sm font-semibold truncate">{thread.username}</span>
										{#if thread.unread_count > 0}
											<Badge variant="default" class="text-xs ml-auto">{thread.unread_count}</Badge>
										{/if}
									</div>
									<div class="flex items-center gap-2 mb-1">
										{#if thread.message_type === 'bug_report'}
											<Badge variant="destructive" class="text-xs">Bug</Badge>
										{:else}
											<Badge class="text-xs bg-yellow-500">Feature</Badge>
										{/if}
										<Badge variant={getStatusBadgeVariant(thread.status)} class="text-xs">
											{thread.status}
										</Badge>
									</div>
									{#if thread.last_message_preview}
										<p class="text-xs line-clamp-2 mb-1 text-muted-foreground">
											{thread.last_message_preview}
										</p>
									{/if}
									<p class="text-xs text-muted-foreground">{formatDate(thread.last_message_at)}</p>
								</button>
							{/each}
						</div>
					{/if}
				</ScrollArea>
			</div>

			<!-- Messages Area (Right Panel) -->
			<div class="flex-1 flex flex-col min-w-0">
				{#if selectedThread}
					<div class="flex-1 flex flex-col min-h-0">
						<!-- Thread Header -->
						<div class="flex items-center justify-between pb-4 border-b">
							<div class="flex items-center gap-2">
								<span class="font-semibold">{selectedThread.username}</span>
								{#if selectedThread.message_type === 'bug_report'}
									<Badge variant="destructive">Bug Report</Badge>
								{:else}
									<Badge class="bg-yellow-500">Feature Request</Badge>
								{/if}
								<Badge variant={getStatusBadgeVariant(selectedThread.status)}>
									{selectedThread.status}
								</Badge>
							</div>
							<div class="flex gap-2">
								{#if selectedThread.status === 'closed'}
									<Button
										variant="outline"
										size="sm"
										onclick={() => changeThreadStatus('answered')}
									>
										Reopen
									</Button>
								{:else}
									<Button
										variant="outline"
										size="sm"
										onclick={() => changeThreadStatus('closed')}
									>
										<X class="h-4 w-4 mr-1" />
										Close
									</Button>
								{/if}
							</div>
						</div>

						<!-- Messages Container -->
						<div bind:this={messagesContainer} class="flex-1 overflow-y-auto py-4 space-y-4">
							{#if isLoadingMessages}
								<div class="flex justify-center py-8">
									<Loader2 class="h-8 w-8 animate-spin" />
								</div>
							{:else if messages.length === 0}
								<p class="text-center text-muted-foreground py-8">No messages yet</p>
							{:else}
								{#each messages as message}
									<div
										class="flex {message.message_type === 'admin' ? 'justify-end' : 'justify-start'}"
									>
										<div
											class="max-w-[70%] rounded-lg p-3 {message.message_type === 'admin'
												? 'bg-primary text-primary-foreground'
												: 'bg-muted'}"
										>
											<div class="flex items-center gap-2 mb-1">
												<span class="text-xs font-semibold">{message.sender_username}</span>
												<span class="text-xs opacity-70">{formatDate(message.created_at)}</span>
												{#if message.is_read}
													<span class="text-xs opacity-70">✓ Read</span>
												{/if}
											</div>
											<p class="text-sm whitespace-pre-wrap">{message.message}</p>
										</div>
									</div>
								{/each}
							{/if}
						</div>

						<!-- Reply Input -->
						{#if selectedThread.status === 'closed'}
							<div class="pt-4 border-t">
								<p class="text-center text-sm text-muted-foreground">
									This thread is closed. Reopen it to reply.
								</p>
							</div>
						{:else}
							<div class="pt-4 border-t flex gap-2">
								<Textarea
									bind:value={responseText}
									placeholder="Type your response..."
									rows={2}
									maxlength={2000}
									onkeydown={handleKeyPress}
									class="flex-1"
								/>
								<Button onclick={sendResponse} disabled={!responseText.trim() || isSending} size="icon">
									{#if isSending}
										<Loader2 class="h-4 w-4 animate-spin" />
									{:else}
										<Send class="h-4 w-4" />
									{/if}
								</Button>
							</div>
						{/if}
					</div>
				{:else}
					<!-- No Thread Selected -->
					<div class="flex-1 flex items-center justify-center">
						<div class="text-center space-y-4">
							<MessageCircle class="h-16 w-16 mx-auto text-muted-foreground" />
							<div>
								<h3 class="text-lg font-semibold">No thread selected</h3>
								<p class="text-sm text-muted-foreground">Select a thread to view messages</p>
							</div>
						</div>
					</div>
				{/if}
			</div>
		</CardContent>
	</Card>
</div>
