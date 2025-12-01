<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Send, MessageCircle, Loader2, Plus, ChevronLeft, Bug, Lightbulb, HelpCircle } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import { t } from '$lib/i18n';
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
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';

	let threads = $state<ThreadResponse[]>([]);
	let selectedThread = $state<ThreadResponse | null>(null);
	let messages = $state<MessageResponse[]>([]);
	let newMessage = $state('');
	let newThreadSubject = $state('');
	let selectedMessageType = $state<'bug_report' | 'feature_request' | 'general_question' | null>(null);
	let isLoadingThreads = $state(false);
	let isLoadingMessages = $state(false);
	let isSending = $state(false);
	let showNewThreadForm = $state(false);
	let messagesContainer: HTMLDivElement;

	async function loadThreads() {
		isLoadingThreads = true;
		try {
			const response = await getSupportThreads({ limit: 100 });
			threads = response.threads;
		} catch (error) {
			toast.error(t('support.loadError'));
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
			toast.error(t('support.loadError'));
			console.error(error);
		} finally {
			isLoadingMessages = false;
		}
	}

	async function selectThread(thread: ThreadResponse) {
		selectedThread = thread;
		showNewThreadForm = false;
		await loadThreadMessages(thread.id);
	}

	async function createNewThread() {
		if (!newMessage.trim() || isSending || !selectedMessageType) {
			if (!selectedMessageType) {
				toast.error(t('support.messageTypeRequired'));
			}
			return;
		}

		isSending = true;
		try {
			const response = await createSupportThread({
				message: newMessage,
				message_type: selectedMessageType,
				subject: newThreadSubject.trim() || null
			});

			// Add new thread to the list
			threads = [response, ...threads];

			// Select the new thread
			await selectThread(response);

			// Reset form
			newMessage = '';
			newThreadSubject = '';
			selectedMessageType = null;
			showNewThreadForm = false;

			toast.success(t('support.sendSuccess'));
		} catch (error) {
			toast.error(t('support.sendError'));
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

			toast.success(t('support.sendSuccess'));
			setTimeout(scrollToBottom, 100);
		} catch (error) {
			toast.error(t('support.sendError'));
			console.error(error);
		} finally {
			isSending = false;
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
			if (showNewThreadForm) {
				createNewThread();
			} else {
				sendMessage();
			}
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
			return t('common.yesterday');
		} else if (days < 7) {
			return `${days} ${t('common.daysAgo')}`;
		} else {
			return date.toLocaleDateString();
		}
	}

	function getMessageTypeLabel(type: string): string {
		switch (type) {
			case 'bug_report':
				return t('support.bugReport');
			case 'feature_request':
				return t('support.featureRequest');
			case 'general_question':
				return t('support.generalQuestion');
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

	onMount(() => {
		loadThreads();

		// Subscribe to WebSocket events
		const unsubscribeThreadCreated = wsManager.on(THREAD_CREATED, (data) => {
			// Reload threads to get the new one
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
					is_read: data.message_type === 'user',
					created_at: data.created_at,
					sender_username: data.sender_username
				};
				messages = [...messages, newMsg];
				setTimeout(scrollToBottom, 100);

				// Mark as read if it's an admin message
				if (data.message_type === 'admin') {
					markThreadMessagesAsRead(selectedThread.id);
				}
			}

			// Update thread in list
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

		const unsubscribeStatusUpdated = wsManager.on(THREAD_STATUS_UPDATED, (data) => {
			// Update thread status in list
			const threadIndex = threads.findIndex(t => t.id === data.thread_id);
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

<div class="container mx-auto max-w-6xl p-4">
	<Card class="h-[calc(100vh-8rem)]">
		<CardHeader>
			<CardTitle class="flex items-center gap-2">
				<MessageCircle class="h-6 w-6" />
				{$t('support.title')}
			</CardTitle>
			<p class="text-sm text-muted-foreground">{$t('support.description')}</p>
		</CardHeader>
		<CardContent class="flex gap-4 h-[calc(100%-8rem)]">
			<!-- Threads List (Left Panel) -->
			<div class="w-80 border-r pr-4 flex flex-col">
				<div class="mb-4">
					<Button
						onclick={() => { showNewThreadForm = true; selectedThread = null; messages = []; }}
						class="w-full"
						variant="default"
					>
						<Plus class="h-4 w-4 mr-2" />
						{$t('support.newThread')}
					</Button>
				</div>

				<div class="flex-1 overflow-y-auto">
					{#if isLoadingThreads}
						<div class="flex items-center justify-center h-32">
							<Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
						</div>
					{:else if threads.length === 0}
						<div class="text-center text-muted-foreground py-8">
							<p>{$t('support.noThreads')}</p>
						</div>
					{:else}
						<div class="space-y-2">
							{#each threads as thread}
								{@const Icon = getMessageTypeIcon(thread.message_type)}
								<button
									onclick={() => selectThread(thread)}
									class="w-full text-left p-3 rounded-lg border transition-colors {selectedThread?.id === thread.id ? 'bg-primary/10 border-primary' : 'hover:bg-muted border-transparent'}"
								>
									<div class="flex items-start justify-between mb-1 gap-2">
										<div class="flex items-center gap-2 flex-1 min-w-0">
											<Icon class="h-4 w-4 flex-shrink-0" />
											<p class="font-medium text-sm truncate">
												{thread.subject || $t('support.noSubject')}
											</p>
										</div>
										{#if thread.unread_count > 0}
											<Badge variant="destructive" class="text-xs flex-shrink-0">
												{thread.unread_count}
											</Badge>
										{/if}
									</div>
									<div class="flex items-center gap-2 mb-1">
										<Badge variant={getMessageTypeBadgeVariant(thread.message_type)} class="text-xs">
											{getMessageTypeLabel(thread.message_type)}
										</Badge>
									</div>
									<p class="text-xs text-muted-foreground truncate mb-1">
										{thread.last_message_preview || ''}
									</p>
									<div class="flex items-center justify-between">
										<span class="text-xs text-muted-foreground">
											{formatDate(thread.last_message_at)}
										</span>
										<Badge variant={thread.status === 'pending' ? 'secondary' : thread.status === 'answered' ? 'default' : 'outline'} class="text-xs">
											{$t(`support.${thread.status}`)}
										</Badge>
									</div>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<!-- Messages / New Thread Form (Right Panel) -->
			<div class="flex-1 flex flex-col">
				{#if showNewThreadForm}
					<!-- New Thread Form -->
					<div class="flex-1 flex flex-col gap-4">
						<div>
							<Button
								onclick={() => { showNewThreadForm = false; selectedMessageType = null; }}
								variant="ghost"
								size="sm"
							>
								<ChevronLeft class="h-4 w-4 mr-1" />
								{$t('common.back')}
							</Button>
						</div>

						<div class="space-y-4">
							<div>
								<label class="text-sm font-medium mb-2 block">{$t('support.messageType')}</label>
								<div class="grid grid-cols-3 gap-3">
									<button
										type="button"
										onclick={() => { selectedMessageType = 'bug_report'; }}
										class="flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all {selectedMessageType === 'bug_report' ? 'border-destructive bg-destructive/10' : 'border-border hover:border-destructive/50'}"
										disabled={isSending}
									>
										<Bug class="h-6 w-6 {selectedMessageType === 'bug_report' ? 'text-destructive' : 'text-muted-foreground'}" />
										<span class="text-xs font-medium text-center">{$t('support.bugReport')}</span>
									</button>
									<button
										type="button"
										onclick={() => { selectedMessageType = 'feature_request'; }}
										class="flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all {selectedMessageType === 'feature_request' ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/50'}"
										disabled={isSending}
									>
										<Lightbulb class="h-6 w-6 {selectedMessageType === 'feature_request' ? 'text-primary' : 'text-muted-foreground'}" />
										<span class="text-xs font-medium text-center">{$t('support.featureRequest')}</span>
									</button>
									<button
										type="button"
										onclick={() => { selectedMessageType = 'general_question'; }}
										class="flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all {selectedMessageType === 'general_question' ? 'border-secondary bg-secondary/10' : 'border-border hover:border-secondary/50'}"
										disabled={isSending}
									>
										<HelpCircle class="h-6 w-6 {selectedMessageType === 'general_question' ? 'text-secondary' : 'text-muted-foreground'}" />
										<span class="text-xs font-medium text-center">{$t('support.generalQuestion')}</span>
									</button>
								</div>
							</div>

							<div>
								<label class="text-sm font-medium">{$t('support.subject')}</label>
								<Input
									bind:value={newThreadSubject}
									placeholder={$t('support.subjectPlaceholder')}
									disabled={isSending}
								/>
							</div>

							<div>
								<label class="text-sm font-medium">{$t('support.message')}</label>
								<Textarea
									bind:value={newMessage}
									onkeydown={handleKeyPress}
									placeholder={$t('support.messagePlaceholder')}
									class="resize-none"
									rows={10}
									disabled={isSending}
								/>
							</div>

							<Button
								onclick={() => createNewThread()}
								disabled={!newMessage.trim() || isSending || !selectedMessageType}
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
					</div>
				{:else if selectedThread}
					{@const Icon = getMessageTypeIcon(selectedThread.message_type)}
					<!-- Thread Messages -->
					<div class="flex-1 flex flex-col">
						<div class="mb-4 pb-3 border-b">
							<h3 class="font-semibold">{selectedThread.subject || $t('support.noSubject')}</h3>
							<div class="flex items-center gap-2 mt-1 flex-wrap">
								<Badge variant={getMessageTypeBadgeVariant(selectedThread.message_type)}>
									<Icon class="h-3 w-3 mr-1" />
									{getMessageTypeLabel(selectedThread.message_type)}
								</Badge>
								<Badge variant={selectedThread.status === 'pending' ? 'secondary' : selectedThread.status === 'answered' ? 'default' : 'outline'}>
									{$t(`support.${selectedThread.status}`)}
								</Badge>
								<span class="text-xs text-muted-foreground">
									{$t('support.created')} {formatDate(selectedThread.created_at)}
								</span>
							</div>
						</div>

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
									<p>{$t('support.noMessages')}</p>
								</div>
							{:else}
								{#each messages as message}
									{#if message.message_type === 'user'}
										<!-- User Message -->
										<div class="flex justify-end">
											<div class="max-w-[70%] space-y-1">
												<div class="bg-primary text-primary-foreground rounded-lg p-3">
													<p class="whitespace-pre-wrap break-words">{message.message}</p>
												</div>
												<div class="flex items-center gap-2 justify-end">
													<span class="text-xs text-muted-foreground">
														{new Date(message.created_at).toLocaleString()}
													</span>
												</div>
											</div>
										</div>
									{:else}
										<!-- Admin Message -->
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
									{/if}
								{/each}
							{/if}
						</div>

						<!-- Input Form -->
						{#if selectedThread.status !== 'closed'}
							<div class="flex gap-2">
								<Textarea
									bind:value={newMessage}
									onkeydown={handleKeyPress}
									placeholder={$t('support.messagePlaceholder')}
									class="resize-none"
									rows={3}
									disabled={isSending}
								/>
								<Button
									onclick={() => sendMessage()}
									disabled={!newMessage.trim() || isSending}
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
								{$t('support.threadClosed')}
							</div>
						{/if}
					</div>
				{:else}
					<!-- No Thread Selected -->
					<div class="flex-1 flex items-center justify-center text-center text-muted-foreground">
						<div>
							<MessageCircle class="h-16 w-16 mx-auto mb-4 opacity-50" />
							<p>{$t('support.selectThread')}</p>
						</div>
					</div>
				{/if}
			</div>
		</CardContent>
	</Card>
</div>
