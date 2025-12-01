<script lang="ts">
	import { onMount } from 'svelte';
	import { MessageCircle, Loader2, Send, CheckCheck, X } from 'lucide-svelte';
	import { toast } from 'svelte-sonner';
	import {
		getSupportThreads,
		getThreadMessages,
		replyToThread,
		updateThreadStatus,
		markThreadMessagesAsRead,
		type ThreadResponse,
		type MessageResponse
	} from '$lib/api/client';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Badge } from '$lib/components/ui/badge';
	import { wsManager, THREAD_CREATED, THREAD_MESSAGE_ADDED, THREAD_STATUS_UPDATED } from '$lib/websocket/manager';

	let threads = $state<ThreadResponse[]>([]);
	let selectedThread = $state<ThreadResponse | null>(null);
	let messages = $state<MessageResponse[]>([]);
	let isLoadingThreads = $state(false);
	let isLoadingMessages = $state(false);
	let isSending = $state(false);
	let statusFilter = $state<string | null>(null);
	let unreadOnly = $state(false);
	let responseText = $state('');
	let messagesContainer: HTMLDivElement;

	async function loadThreads() {
		isLoadingThreads = true;
		try {
			const params: any = { limit: 100 };
			if (statusFilter) params.status_filter = statusFilter;
			if (unreadOnly) params.unread_only = true;

			const response = await getSupportThreads(params);
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
			const response = await getThreadMessages(threadId, { limit: 100 });
			messages = response.messages;
			setTimeout(scrollToBottom, 100);

			// Mark user messages as read
			await markThreadMessagesAsRead(threadId);

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

	async function selectThread(thread: ThreadResponse) {
		selectedThread = thread;
		responseText = '';
		await loadThreadMessages(thread.id);
	}

	async function sendResponse() {
		if (!responseText.trim() || isSending || !selectedThread) return;

		isSending = true;
		try {
			const response = await replyToThread(selectedThread.id, {
				message: responseText
			});

			messages = [...messages, response];
			responseText = '';

			// Update thread last_message_at
			const threadIndex = threads.findIndex((t) => t.id === selectedThread!.id);
			if (threadIndex !== -1) {
				threads[threadIndex] = {
					...threads[threadIndex],
					last_message_at: response.created_at,
					last_message_preview: response.message.substring(0, 100),
					status: 'answered'
				};
			}

			// Update selected thread status
			if (selectedThread.status !== 'answered') {
				selectedThread = { ...selectedThread, status: 'answered' };
			}

			toast.success('Response sent successfully');
			setTimeout(scrollToBottom, 100);
		} catch (error) {
			toast.error('Failed to send response');
			console.error(error);
		} finally {
			isSending = false;
		}
	}

	async function changeThreadStatus(status: string) {
		if (!selectedThread) return;

		try {
			const updated = await updateThreadStatus(selectedThread.id, { status });
			selectedThread = { ...selectedThread, status: updated.status };

			// Update thread in list
			const threadIndex = threads.findIndex((t) => t.id === selectedThread!.id);
			if (threadIndex !== -1) {
				threads[threadIndex] = { ...threads[threadIndex], status: updated.status };
			}

			toast.success('Thread status updated');
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
			return `${days}d ago`;
		} else {
			return date.toLocaleDateString();
		}
	}

	onMount(() => {
		loadThreads();

		// Subscribe to WebSocket events
		const unsubscribeThreadCreated = wsManager.on(THREAD_CREATED, (data) => {
			toast.info('New support thread created');
			loadThreads();
		});

		const unsubscribeMessageAdded = wsManager.on(THREAD_MESSAGE_ADDED, (data) => {
			// If message is for current thread, add it to messages
			if (selectedThread && data.thread_id === selectedThread.id) {
				const newMsg: MessageResponse = {
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

				// Mark user messages as read
				if (data.message_type === 'user') {
					markThreadMessagesAsRead(selectedThread.id);
				}
			}

			// Update thread in list
			const threadIndex = threads.findIndex((t) => t.id === data.thread_id);
			if (threadIndex !== -1) {
				threads[threadIndex] = {
					...threads[threadIndex],
					last_message_at: data.created_at,
					last_message_preview: data.message.substring(0, 100),
					unread_count:
						data.message_type === 'user'
							? threads[threadIndex].unread_count + 1
							: threads[threadIndex].unread_count
				};

				// Move thread to top
				const [thread] = threads.splice(threadIndex, 1);
				threads = [thread, ...threads];
			}
		});

		const unsubscribeStatusUpdated = wsManager.on(THREAD_STATUS_UPDATED, (data) => {
			// Update thread status in list
			const threadIndex = threads.findIndex((t) => t.id === data.thread_id);
			if (threadIndex !== -1) {
				threads[threadIndex] = { ...threads[threadIndex], status: data.status };
			}

			// Update selected thread status
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

<div class="container mx-auto p-6">
	<Card class="h-[calc(100vh-8rem)]">
		<CardHeader>
			<CardTitle class="flex items-center gap-2">
				<MessageCircle class="h-6 w-6" />
				Support Threads
			</CardTitle>
		</CardHeader>
		<CardContent class="flex gap-4 h-[calc(100%-5rem)]">
			<!-- Threads List (Left Panel) -->
			<div class="w-96 border-r pr-4 flex flex-col">
				<!-- Filters -->
				<div class="mb-4 space-y-2">
					<div class="flex gap-2">
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
					<Button
						variant={unreadOnly ? 'default' : 'outline'}
						size="sm"
						class="w-full"
						onclick={() => {
							unreadOnly = !unreadOnly;
							loadThreads();
						}}
					>
						{unreadOnly ? 'Show All' : 'Unread Only'}
					</Button>
				</div>

				<!-- Thread List -->
				<div class="flex-1 overflow-y-auto">
					{#if isLoadingThreads}
						<div class="flex items-center justify-center h-32">
							<Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
						</div>
					{:else if threads.length === 0}
						<div class="text-center text-muted-foreground py-8">
							<p>No threads found</p>
						</div>
					{:else}
						<div class="space-y-2">
							{#each threads as thread}
								<button
									onclick={() => selectThread(thread)}
									class="w-full text-left p-3 rounded-lg border transition-colors {selectedThread?.id ===
									thread.id
										? 'bg-primary/10 border-primary'
										: 'hover:bg-muted border-transparent'}"
								>
									<div class="flex items-start justify-between mb-1">
										<div class="flex-1 min-w-0">
											<p class="font-medium text-sm truncate">
												{thread.username}
											</p>
											<p class="text-xs text-muted-foreground truncate">
												{thread.subject || 'No subject'}
											</p>
										</div>
										{#if thread.unread_count > 0}
											<Badge variant="destructive" class="ml-2 text-xs shrink-0">
												{thread.unread_count}
											</Badge>
										{/if}
									</div>
									<p class="text-xs text-muted-foreground truncate mb-1">
										{thread.last_message_preview || ''}
									</p>
									<div class="flex items-center justify-between">
										<span class="text-xs text-muted-foreground">
											{formatDate(thread.last_message_at)}
										</span>
										<Badge
											variant={thread.status === 'pending'
												? 'secondary'
												: thread.status === 'answered'
													? 'default'
													: 'outline'}
											class="text-xs"
										>
											{thread.status}
										</Badge>
									</div>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<!-- Thread Messages (Right Panel) -->
			<div class="flex-1 flex flex-col">
				{#if selectedThread}
					<div class="flex-1 flex flex-col">
						<!-- Thread Header -->
						<div class="mb-4 pb-3 border-b flex items-center justify-between">
							<div>
								<h3 class="font-semibold">
									{selectedThread.username} - {selectedThread.subject || 'No subject'}
								</h3>
								<div class="flex items-center gap-2 mt-1">
									<Badge
										variant={selectedThread.status === 'pending'
											? 'secondary'
											: selectedThread.status === 'answered'
												? 'default'
												: 'outline'}
									>
										{selectedThread.status}
									</Badge>
									<span class="text-xs text-muted-foreground">
										Created {formatDate(selectedThread.created_at)}
									</span>
								</div>
							</div>
							<div class="flex gap-2">
								{#if selectedThread.status !== 'closed'}
									<Button
										variant="outline"
										size="sm"
										onclick={() => changeThreadStatus('closed')}
									>
										<X class="h-4 w-4 mr-1" />
										Close
									</Button>
								{/if}
								{#if selectedThread.status === 'closed'}
									<Button
										variant="outline"
										size="sm"
										onclick={() => changeThreadStatus('pending')}
									>
										Reopen
									</Button>
								{/if}
							</div>
						</div>

						<!-- Messages -->
						<div
							bind:this={messagesContainer}
							class="flex-1 overflow-y-auto space-y-4 p-4 bg-muted/30 rounded-lg mb-4"
						>
							{#if isLoadingMessages}
								<div class="flex items-center justify-center h-full">
									<Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
								</div>
							{:else if messages.length === 0}
								<div class="flex items-center justify-center h-full text-center text-muted-foreground">
									<p>No messages</p>
								</div>
							{:else}
								{#each messages as message}
									{#if message.message_type === 'user'}
										<!-- User Message -->
										<div class="flex justify-start">
											<div class="max-w-[70%] space-y-1">
												<div class="bg-muted rounded-lg p-3">
													<p class="text-sm font-semibold mb-1">{message.sender_username}</p>
													<p class="whitespace-pre-wrap break-words">{message.message}</p>
												</div>
												<span class="text-xs text-muted-foreground">
													{new Date(message.created_at).toLocaleString()}
												</span>
											</div>
										</div>
									{:else}
										<!-- Admin Message -->
										<div class="flex justify-end">
											<div class="max-w-[70%] space-y-1">
												<div class="bg-primary text-primary-foreground rounded-lg p-3">
													<p class="text-sm font-semibold mb-1">{message.sender_username}</p>
													<p class="whitespace-pre-wrap break-words">{message.message}</p>
												</div>
												<div class="flex items-center gap-2 justify-end">
													<span class="text-xs text-muted-foreground">
														{new Date(message.created_at).toLocaleString()}
													</span>
													{#if message.is_read}
														<CheckCheck class="h-3 w-3 text-muted-foreground" />
													{/if}
												</div>
											</div>
										</div>
									{/if}
								{/each}
							{/if}
						</div>

						<!-- Reply Input -->
						{#if selectedThread.status !== 'closed'}
							<div class="flex gap-2">
								<Textarea
									bind:value={responseText}
									onkeydown={handleKeyPress}
									placeholder="Type your response..."
									class="resize-none"
									rows={3}
									disabled={isSending}
								/>
								<Button
									onclick={sendResponse}
									disabled={!responseText.trim() || isSending}
									size="icon"
									class="h-full aspect-square"
								>
									{#if isSending}
										<Loader2 class="h-5 w-5 animate-spin" />
									{:else}
										<Send class="h-5 w-5" />
									{/if}
								</Button>
							</div>
						{:else}
							<div class="text-center text-muted-foreground p-4 bg-muted/30 rounded-lg">
								Thread is closed. Reopen to continue conversation.
							</div>
						{/if}
					</div>
				{:else}
					<!-- No Thread Selected -->
					<div class="flex-1 flex items-center justify-center text-center text-muted-foreground">
						<div>
							<MessageCircle class="h-16 w-16 mx-auto mb-4 opacity-50" />
							<p>Select a thread to view messages</p>
						</div>
					</div>
				{/if}
			</div>
		</CardContent>
	</Card>
</div>
