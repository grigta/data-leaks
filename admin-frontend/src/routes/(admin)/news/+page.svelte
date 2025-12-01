<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
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
		DialogTitle,
		DialogTrigger
	} from '$lib/components/ui/dialog';
	import { Textarea } from '$lib/components/ui/textarea';
	import {
		getNews,
		createNews,
		updateNews,
		deleteNews,
		type NewsResponse,
		type CreateNewsRequest,
		type UpdateNewsRequest,
		handleApiError
	} from '$lib/api/client';
	import { formatDate } from '$lib/utils';
	import { Plus, Edit, Trash2, Loader2 } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';

	// State
	let news = $state<NewsResponse[]>([]);
	let isLoading = $state(true);
	let error = $state('');
	let showCreateDialog = $state(false);
	let showEditDialog = $state(false);
	let selectedNews = $state<NewsResponse | null>(null);
	let isCreating = $state(false);
	let isUpdating = $state(false);

	// AbortController for canceling requests
	let abortController: AbortController | null = null;

	// Form data
	let formData = $state<CreateNewsRequest>({
		title: '',
		content: ''
	});

	// Load news
	async function loadNews() {
		// Cancel previous request if exists
		if (abortController) {
			abortController.abort();
		}

		abortController = new AbortController();
		const currentController = abortController;

		isLoading = true;
		error = '';

		try {
			const response = await getNews();

			// Only update state if not aborted
			if (!currentController.signal.aborted) {
				news = response?.news ?? [];
			}
		} catch (err: any) {
			if (!currentController.signal.aborted) {
				console.error('Failed to load news:', err);
				error = handleApiError(err);
				news = [];
			}
		} finally {
			if (!currentController.signal.aborted) {
				isLoading = false;
			}
		}
	}

	// Handle create news
	async function handleCreateNews() {
		if (isCreating) return;

		if (!formData.title || formData.title.trim().length < 3) {
			toast.error('Заголовок должен быть не менее 3 символов');
			return;
		}

		if (!formData.content || formData.content.trim().length < 10) {
			toast.error('Содержание должно быть не менее 10 символов');
			return;
		}

		isCreating = true;

		try {
			await createNews({
				title: formData.title.trim(),
				content: formData.content.trim()
			});

			toast.success('Новость успешно создана');
			showCreateDialog = false;
			resetForm();
			loadNews();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isCreating = false;
		}
	}

	// Handle update news
	async function handleUpdateNews() {
		if (!selectedNews || isUpdating) return;

		if (!formData.title || formData.title.trim().length < 3) {
			toast.error('Заголовок должен быть не менее 3 символов');
			return;
		}

		if (!formData.content || formData.content.trim().length < 10) {
			toast.error('Содержание должно быть не менее 10 символов');
			return;
		}

		isUpdating = true;

		try {
			await updateNews(selectedNews.id, {
				title: formData.title.trim(),
				content: formData.content.trim()
			});

			toast.success('Новость успешно обновлена');
			showEditDialog = false;
			selectedNews = null;
			resetForm();
			loadNews();
		} catch (err: any) {
			toast.error(handleApiError(err));
		} finally {
			isUpdating = false;
		}
	}

	// Handle delete news
	async function handleDeleteNews(newsItem: NewsResponse) {
		const confirmed = confirm('Уверены, что хотите удалить эту статью?');
		if (!confirmed) return;

		try {
			await deleteNews(newsItem.id);
			toast.success('Новость удалена');
			loadNews();
		} catch (err: any) {
			toast.error(handleApiError(err));
		}
	}

	// Open edit dialog
	function openEditDialog(newsItem: NewsResponse) {
		selectedNews = newsItem;
		formData = {
			title: newsItem.title,
			content: newsItem.content
		};
		showEditDialog = true;
	}

	// Reset form
	function resetForm() {
		formData = {
			title: '',
			content: ''
		};
	}

	onMount(() => {
		loadNews();

		return () => {
			// Cancel any pending requests
			if (abortController) {
				abortController.abort();
			}
		};
	});
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">Управление новостями</h2>
			<p class="text-muted-foreground">Создание и управление статьями новостей для панели</p>
		</div>

		<Dialog bind:open={showCreateDialog}>
			<DialogTrigger>
				{#snippet child({ props })}
					<Button {...props}>
						<Plus class="mr-2 h-4 w-4" />
						Создать новость
					</Button>
				{/snippet}
			</DialogTrigger>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>Создать новую статью</DialogTitle>
				</DialogHeader>
				<div class="space-y-4 py-4">
					<div class="space-y-2">
						<Label for="title">Заголовок</Label>
						<Input
							id="title"
							placeholder="Введите заголовок новости"
							bind:value={formData.title}
						/>
					</div>

					<div class="space-y-2">
						<Label for="content">Содержание</Label>
						<Textarea
							id="content"
							placeholder="Введите содержание новости"
							rows="6"
							bind:value={formData.content}
						/>
					</div>

					<div class="flex gap-2">
						<Button class="flex-1" onclick={handleCreateNews} disabled={isCreating}>
							{#if isCreating}
								<Loader2 class="mr-2 h-4 w-4 animate-spin" />
								Создание...
							{:else}
								Создать
							{/if}
						</Button>
						<Button
							variant="outline"
							class="flex-1"
							disabled={isCreating}
							onclick={() => {
								showCreateDialog = false;
								resetForm();
								isCreating = false;
							}}>Отмена</Button
						>
					</div>
				</div>
			</DialogContent>
		</Dialog>
	</div>

	<!-- Error alert -->
	{#if error}
		<Alert variant="destructive">
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<!-- News table -->
	<Card>
		<CardHeader>
			<CardTitle>Статьи новостей</CardTitle>
		</CardHeader>
		<CardContent>
			{#if isLoading}
				<div class="flex items-center justify-center py-8">
					<Loader2 class="h-8 w-8 animate-spin text-primary" />
				</div>
			{:else if news.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<p class="text-muted-foreground">Статьи не найдены</p>
					<p class="text-sm text-muted-foreground">Создайте первую статью для начала</p>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>Заголовок</TableHead>
								<TableHead>Автор</TableHead>
								<TableHead>Создан</TableHead>
								<TableHead>Обновлён</TableHead>
								<TableHead class="text-right">Действия</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each news as newsItem}
								<TableRow onclick={() => openEditDialog(newsItem)}>
									<TableCell class="font-medium">
										{newsItem.title.length > 50
											? newsItem.title.substring(0, 50) + '...'
											: newsItem.title}
									</TableCell>
									<TableCell>{newsItem.author_username}</TableCell>
									<TableCell>{formatDate(newsItem.created_at)}</TableCell>
									<TableCell>{formatDate(newsItem.updated_at)}</TableCell>
									<TableCell class="text-right">
										<div class="flex justify-end gap-2">
											<Button
												variant="ghost"
												size="icon"
												onclick={(e) => {
													e.stopPropagation();
													openEditDialog(newsItem);
												}}
											>
												<Edit class="h-4 w-4" />
											</Button>
											<Button
												variant="ghost"
												size="icon"
												onclick={(e) => {
													e.stopPropagation();
													handleDeleteNews(newsItem);
												}}
											>
												<Trash2 class="h-4 w-4 text-destructive" />
											</Button>
										</div>
									</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				</div>
			{/if}
		</CardContent>
	</Card>
</div>

<!-- Edit Dialog -->
<Dialog bind:open={showEditDialog}>
	<DialogContent>
		<DialogHeader>
			<DialogTitle>Редактировать статью</DialogTitle>
		</DialogHeader>
		<div class="space-y-4 py-4">
			<div class="space-y-2">
				<Label for="edit_title">Заголовок</Label>
				<Input
					id="edit_title"
					bind:value={formData.title}
				/>
			</div>

			<div class="space-y-2">
				<Label for="edit_content">Содержание</Label>
				<Textarea
					id="edit_content"
					rows="6"
					bind:value={formData.content}
				/>
			</div>

			<div class="flex gap-2">
				<Button class="flex-1" onclick={handleUpdateNews} disabled={isUpdating}>
					{#if isUpdating}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						Обновление...
					{:else}
						Обновить
					{/if}
				</Button>
				<Button
					variant="outline"
					class="flex-1"
					disabled={isUpdating}
					onclick={() => {
						showEditDialog = false;
						selectedNews = null;
						resetForm();
						isUpdating = false;
					}}>Отмена</Button
				>
			</div>
		</div>
	</DialogContent>
</Dialog>
