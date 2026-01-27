<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import type { UserTableItem } from '$lib/api/client';
	import { searchUsers, handleApiError } from '$lib/api/client';
	import { toast } from 'svelte-sonner';
	import type { AxiosError } from 'axios';
	import Input from '$lib/components/ui/input/input.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import { Search, User, Loader2, X } from 'lucide-svelte';

	interface Props {
		value?: UserTableItem | null;
		placeholder?: string;
		disabled?: boolean;
	}

	let {
		value = $bindable(null),
		placeholder = 'Search by username or ID',
		disabled = false
	}: Props = $props();

	const dispatch = createEventDispatcher<{ select: UserTableItem | null }>();

	let searchQuery = $state('');
	let searchResults = $state<UserTableItem[]>([]);
	let isSearching = $state(false);
	let showResults = $state(false);
	let searchTimeout: ReturnType<typeof setTimeout> | null = null;

	// Display value - show username if user is selected
	let displayValue = $derived(value?.username || searchQuery);

	async function handleSearchInput(event: Event) {
		const target = event.target as HTMLInputElement;
		searchQuery = target.value;

		// Clear previous timeout
		if (searchTimeout) {
			clearTimeout(searchTimeout);
		}

		// If query is empty, clear results
		if (!searchQuery.trim()) {
			searchResults = [];
			showResults = false;
			return;
		}

		// Debounce search (500ms)
		searchTimeout = setTimeout(async () => {
			isSearching = true;
			showResults = true;

			try {
				const results = await searchUsers(searchQuery);
				searchResults = results;
			} catch (error) {
				const errorMessage = handleApiError(error as AxiosError);
				toast.error(errorMessage);
				searchResults = [];
			} finally {
				isSearching = false;
			}
		}, 500);
	}

	function selectUser(user: UserTableItem) {
		value = user;
		searchQuery = user.username;
		showResults = false;
		dispatch('select', user);
	}

	function clearSelection() {
		value = null;
		searchQuery = '';
		searchResults = [];
		showResults = false;
		dispatch('select', null);
	}

	function handleFocus() {
		if (searchResults.length > 0 && searchQuery.trim()) {
			showResults = true;
		}
	}

	function handleBlur() {
		// Delay to allow click on results
		setTimeout(() => {
			showResults = false;
		}, 200);
	}
</script>

<div class="relative w-full">
	<div class="relative">
		<div class="absolute left-3 top-1/2 -translate-y-1/2">
			{#if isSearching}
				<Loader2 class="h-4 w-4 animate-spin text-muted-foreground" />
			{:else if value}
				<User class="h-4 w-4 text-primary" />
			{:else}
				<Search class="h-4 w-4 text-muted-foreground" />
			{/if}
		</div>

		<Input
			type="text"
			value={displayValue}
			oninput={handleSearchInput}
			onfocus={handleFocus}
			onblur={handleBlur}
			{placeholder}
			{disabled}
			class="pl-10 {value ? 'pr-10' : ''}"
		/>

		{#if value}
			<button
				type="button"
				onclick={clearSelection}
				class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
				disabled={disabled}
			>
				<X class="h-4 w-4" />
			</button>
		{/if}
	</div>

	{#if showResults}
		<div class="absolute z-50 w-full mt-1 bg-popover border rounded-md shadow-md max-h-64 overflow-y-auto">
			{#if searchResults.length > 0}
				<div class="p-1">
					{#each searchResults as user}
						<button
							type="button"
							onclick={() => selectUser(user)}
							class="w-full text-left px-3 py-2 rounded-sm hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground cursor-pointer transition-colors"
						>
							<div class="flex items-center justify-between">
								<div class="flex-1 min-w-0">
									<div class="font-medium truncate">{user.username}</div>
									<div class="text-sm text-muted-foreground truncate">ID: {user.id}</div>
								</div>
								<div class="ml-2 text-sm text-muted-foreground">
									${user.balance.toFixed(2)}
								</div>
							</div>
						</button>
					{/each}
				</div>
			{:else if !isSearching}
				<div class="p-4 text-center text-sm text-muted-foreground">
					No users found
				</div>
			{/if}
		</div>
	{/if}
</div>
