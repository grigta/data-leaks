<script lang="ts">
	import { onMount } from 'svelte';
	import { user, refreshUser } from '$lib/stores/auth';
	import {
		getSubscriptionPlans,
		purchaseSubscription,
		getMySubscription,
		searchDatabase,
		handleApiError,
		type SubscriptionPlanResponse,
		type SubscriptionResponse,
		type LookupSearchRequest,
		type LookupSearchMatch
	} from '$lib/api/client';
	import { formatCurrency } from '$lib/utils';
	import { t } from '$lib/i18n';
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Alert, AlertDescription, AlertTitle } from '$lib/components/ui/alert';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import {
		Dialog,
		DialogContent,
		DialogDescription,
		DialogFooter,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import CreditCard from '@lucide/svelte/icons/credit-card';
	import Check from '@lucide/svelte/icons/check';
	import Clock from '@lucide/svelte/icons/clock';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Crown from '@lucide/svelte/icons/crown';
	import Sparkles from '@lucide/svelte/icons/sparkles';
	import Database from '@lucide/svelte/icons/database';
	import Search from '@lucide/svelte/icons/search';
	import X from '@lucide/svelte/icons/x';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';

	// State
	let plans = $state<SubscriptionPlanResponse[]>([]);
	let currentSubscription = $state<SubscriptionResponse | null>(null);
	let isLoading = $state(true);
	let isPurchasing = $state(false);
	let selectedPlanId = $state<string | null>(null);
	let showConfirmDialog = $state(false);
	let errorMessage = $state('');
	let successMessage = $state('');

	// Search state
	let searchForm = $state<LookupSearchRequest>({
		firstname: '',
		lastname: '',
		street: '',
		phone: '',
		city: '',
		state: ''
	});
	let searchResults = $state<LookupSearchMatch[]>([]);
	let isSearching = $state(false);
	let searchError = $state('');
	let hasSearched = $state(false);

	// Computed
	const selectedPlan = $derived(plans.find((p) => p.id === selectedPlanId));

	onMount(async () => {
		await Promise.all([loadPlans(), loadSubscription()]);
	});

	async function loadPlans() {
		try {
			plans = await getSubscriptionPlans();
		} catch (error) {
			console.error('Failed to load subscription plans:', error);
			errorMessage = handleApiError(error);
		}
	}

	async function loadSubscription() {
		try {
			currentSubscription = await getMySubscription();
		} catch (error) {
			console.error('Failed to load subscription:', error);
		} finally {
			isLoading = false;
		}
	}

	function handlePurchaseClick(planId: string) {
		selectedPlanId = planId;
		errorMessage = '';
		showConfirmDialog = true;
	}

	async function handleConfirmPurchase() {
		if (!selectedPlanId) return;

		isPurchasing = true;
		errorMessage = '';

		try {
			const subscription = await purchaseSubscription(selectedPlanId);
			currentSubscription = subscription;
			showConfirmDialog = false;
			await refreshUser();
			successMessage = $t('subscription.purchaseSuccess');
			toast.success($t('subscription.subscriptionActivated'), {
				description: $t('subscription.subscriptionActivatedDesc', { planName: subscription.plan.name })
			});
			setTimeout(() => {
				successMessage = '';
			}, 5000);
		} catch (error) {
			console.error('Failed to purchase subscription:', error);
			errorMessage = handleApiError(error);
		} finally {
			isPurchasing = false;
		}
	}

	async function handleRenewal() {
		if (!currentSubscription) return;
		handlePurchaseClick(currentSubscription.plan.id);
	}

	async function handleSearch() {
		// Validate required fields
		if (!searchForm.firstname.trim()) {
			searchError = $t('subscription.firstnameRequired');
			return;
		}
		if (!searchForm.lastname.trim()) {
			searchError = $t('subscription.lastnameRequired');
			return;
		}

		searchError = '';
		isSearching = true;
		hasSearched = true;
		searchResults = [];

		try {
			const response = await searchDatabase({
				firstname: searchForm.firstname.trim(),
				lastname: searchForm.lastname.trim(),
				street: searchForm.street?.trim() || undefined,
				phone: searchForm.phone?.trim() || undefined,
				city: searchForm.city?.trim() || undefined,
				state: searchForm.state?.trim() || undefined
			});
			searchResults = response.database_matches;
		} catch (error: any) {
			console.error('Search error:', error);
			if (error.response?.status === 401) {
				searchError = $t('subscription.errorAuthRequired');
			} else if (error.response?.status === 403) {
				searchError = $t('subscription.errorSubscriptionRequired');
			} else {
				searchError = handleApiError(error);
			}
		} finally {
			isSearching = false;
		}
	}

	function clearSearchForm() {
		searchForm = {
			firstname: '',
			lastname: '',
			street: '',
			phone: '',
			city: '',
			state: ''
		};
		searchResults = [];
		searchError = '';
		hasSearched = false;
	}

	function isExpiringSoon(): boolean {
		if (!currentSubscription) return false;
		const endDate = new Date(currentSubscription.end_date);
		const now = new Date();
		const daysRemaining = Math.ceil((endDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
		return daysRemaining <= 3 && daysRemaining >= 0;
	}

	function getDaysRemaining(): number {
		if (!currentSubscription) return 0;
		const endDate = new Date(currentSubscription.end_date);
		const now = new Date();
		return Math.ceil((endDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
	}

	function formatDate(dateString: string): string {
		return new Date(dateString).toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'long',
			day: 'numeric'
		});
	}

	function getOriginalPrice(plan: SubscriptionPlanResponse): number {
		if (plan.discount_percent === 0) return plan.price;
		return Math.round((plan.price / (1 - plan.discount_percent / 100)) * 100) / 100;
	}

	function getPricePerMonth(plan: SubscriptionPlanResponse): number {
		return Math.round((plan.price / plan.duration_months) * 100) / 100;
	}

	function isBestValue(plan: SubscriptionPlanResponse): boolean {
		return plan.duration_months === 12;
	}

	function formatPhones(phones: any[]): string {
		if (!phones || phones.length === 0) return '-';
		return phones.map(p => typeof p === 'string' ? p : p.phone || p.number || JSON.stringify(p)).join(', ');
	}

	function formatEmails(emails: any[]): string {
		if (!emails || emails.length === 0) return '-';
		return emails.map(e => typeof e === 'string' ? e : e.email || e.address || JSON.stringify(e)).join(', ');
	}

	function formatAddresses(addresses: any[]): string {
		if (!addresses || addresses.length === 0) return '-';
		return addresses.map(a => {
			if (typeof a === 'string') return a;
			const parts = [a.address, a.city, a.state, a.zip].filter(Boolean);
			return parts.join(', ') || JSON.stringify(a);
		}).join(' | ');
	}
</script>

<svelte:head>
	<title>{$t('subscription.title')} - Lookup SSN Access</title>
</svelte:head>

<div class="container mx-auto px-4 py-8 max-w-6xl">
	<!-- Header -->
	<div class="mb-8">
		<div class="flex items-center gap-3 mb-2">
			<CreditCard class="h-8 w-8 text-primary" />
			<h1 class="text-3xl font-bold">{$t('subscription.title')}</h1>
		</div>
		<p class="text-muted-foreground">
			{$t('subscription.description')}
		</p>
	</div>

	<!-- Alerts -->
	{#if errorMessage}
		<Alert variant="destructive" class="mb-6">
			<AlertCircle class="h-4 w-4" />
			<AlertTitle>{$t('subscription.error')}</AlertTitle>
			<AlertDescription>{errorMessage}</AlertDescription>
		</Alert>
	{/if}

	{#if successMessage}
		<Alert class="mb-6 border-green-500 bg-green-50 text-green-700">
			<Check class="h-4 w-4" />
			<AlertTitle>{$t('subscription.success')}</AlertTitle>
			<AlertDescription>{successMessage}</AlertDescription>
		</Alert>
	{/if}

	{#if isLoading}
		<!-- Loading Skeleton -->
		<div class="space-y-6">
			<Skeleton class="h-32 w-full" />
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
				{#each Array(4) as _}
					<Skeleton class="h-64" />
				{/each}
			</div>
		</div>
	{:else if currentSubscription}
		<!-- HAS SUBSCRIPTION VIEW -->

		<!-- Section 1: Current Subscription Card -->
		<Card class="mb-8">
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<Clock class="h-5 w-5" />
					{$t('subscription.currentStatus')}
				</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
					<div>
						<div class="flex items-center gap-2 mb-2">
							<Badge variant="default" class="bg-green-500">{$t('subscription.active')}</Badge>
							<span class="font-semibold text-lg">{currentSubscription.plan.name}</span>
						</div>
						<div class="text-sm text-muted-foreground space-y-1">
							<p>{$t('subscription.started')}: {formatDate(currentSubscription.start_date)}</p>
							<p>{$t('subscription.expires')}: {formatDate(currentSubscription.end_date)}</p>
							<p class="font-medium text-foreground">
								{$t('subscription.daysRemaining', { days: getDaysRemaining() })}
							</p>
						</div>
					</div>
					<div class="flex flex-col gap-2">
						{#if isExpiringSoon()}
							<Alert variant="destructive" class="md:max-w-xs">
								<AlertCircle class="h-4 w-4" />
								<AlertDescription>
									{$t('subscription.expiringSoon')}
								</AlertDescription>
							</Alert>
						{/if}
						<Button onclick={handleRenewal} variant="outline">
							<RefreshCw class="h-4 w-4 mr-2" />
							{$t('subscription.renewSubscription')}
						</Button>
					</div>
				</div>
			</CardContent>
		</Card>

		<!-- Section 2: Database Lookup Service -->
		<Card class="mb-8">
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<Database class="h-5 w-5" />
					{$t('subscription.lookupService')}
				</CardTitle>
				<CardDescription>{$t('subscription.lookupServiceDesc')}</CardDescription>
			</CardHeader>
			<CardContent>
				<!-- Search Form -->
				<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
					<div class="space-y-2">
						<Label for="firstname">{$t('subscription.firstname')} *</Label>
						<Input
							id="firstname"
							bind:value={searchForm.firstname}
							placeholder={$t('subscription.firstname')}
						/>
					</div>
					<div class="space-y-2">
						<Label for="lastname">{$t('subscription.lastname')} *</Label>
						<Input
							id="lastname"
							bind:value={searchForm.lastname}
							placeholder={$t('subscription.lastname')}
						/>
					</div>
					<div class="space-y-2">
						<Label for="street">{$t('subscription.street')}</Label>
						<Input
							id="street"
							bind:value={searchForm.street}
							placeholder={$t('subscription.street')}
						/>
					</div>
					<div class="space-y-2">
						<Label for="phone">{$t('subscription.phone')}</Label>
						<Input
							id="phone"
							bind:value={searchForm.phone}
							placeholder={$t('subscription.phone')}
						/>
					</div>
					<div class="space-y-2">
						<Label for="city">{$t('subscription.city')}</Label>
						<Input
							id="city"
							bind:value={searchForm.city}
							placeholder={$t('subscription.city')}
						/>
					</div>
					<div class="space-y-2">
						<Label for="state">{$t('subscription.state')}</Label>
						<Input
							id="state"
							bind:value={searchForm.state}
							placeholder={$t('subscription.state')}
							maxlength={2}
						/>
					</div>
				</div>

				{#if searchError}
					<Alert variant="destructive" class="mb-4">
						<AlertCircle class="h-4 w-4" />
						<AlertDescription>{searchError}</AlertDescription>
					</Alert>
				{/if}

				<div class="flex gap-4 mb-6">
					<Button onclick={handleSearch} disabled={isSearching}>
						{#if isSearching}
							<Loader2 class="h-4 w-4 mr-2 animate-spin" />
							{$t('subscription.searching')}
						{:else}
							<Search class="h-4 w-4 mr-2" />
							{$t('subscription.searchDatabase')}
						{/if}
					</Button>
					<Button variant="outline" onclick={clearSearchForm}>
						<X class="h-4 w-4 mr-2" />
						{$t('subscription.clearForm')}
					</Button>
				</div>

				<!-- Search Results -->
				{#if hasSearched}
					{#if searchResults.length > 0}
						<div class="border rounded-lg overflow-hidden">
							<div class="bg-muted px-4 py-2 font-medium">
								{$t('subscription.resultsFound', { count: searchResults.length })}
							</div>
							<div class="overflow-x-auto">
								<Table>
									<TableHeader>
										<TableRow>
											<TableHead>{$t('subscription.name')}</TableHead>
											<TableHead>{$t('subscription.ssn')}</TableHead>
											<TableHead>{$t('subscription.dob')}</TableHead>
											<TableHead>{$t('subscription.city')}</TableHead>
											<TableHead>{$t('subscription.state')}</TableHead>
											<TableHead>{$t('subscription.phones')}</TableHead>
											<TableHead>{$t('subscription.emails')}</TableHead>
										</TableRow>
									</TableHeader>
									<TableBody>
										{#each searchResults as result}
											<TableRow>
												<TableCell class="font-medium">
													{[result.firstname, result.middlename, result.lastname].filter(Boolean).join(' ') || '-'}
												</TableCell>
												<TableCell class="font-mono">{result.ssn || '-'}</TableCell>
												<TableCell>{result.dob || '-'}</TableCell>
												<TableCell>{result.city || '-'}</TableCell>
												<TableCell>{result.state || '-'}</TableCell>
												<TableCell class="max-w-[200px] truncate">{formatPhones(result.phones || [])}</TableCell>
												<TableCell class="max-w-[200px] truncate">{formatEmails(result.emails || [])}</TableCell>
											</TableRow>
										{/each}
									</TableBody>
								</Table>
							</div>
						</div>
					{:else if !isSearching}
						<Alert>
							<AlertCircle class="h-4 w-4" />
							<AlertDescription>{$t('subscription.noResults')}</AlertDescription>
						</Alert>
					{/if}
				{/if}
			</CardContent>
		</Card>

		<!-- Section 3: Available Plans (for renewal reference) -->
		<div class="mb-6">
			<h2 class="text-2xl font-bold mb-2">{$t('subscription.availablePlans')}</h2>
			<p class="text-muted-foreground">{$t('subscription.choosePlan')}</p>
		</div>

		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
			{#each plans as plan (plan.id)}
				<Card
					class="relative transition-all duration-200 hover:shadow-lg {isBestValue(plan)
						? 'border-primary ring-2 ring-primary shadow-md'
						: ''}"
				>
					{#if isBestValue(plan)}
						<div class="absolute -top-3 left-1/2 -translate-x-1/2">
							<Badge class="bg-primary text-primary-foreground flex items-center gap-1">
								<Crown class="h-3 w-3" />
								{$t('subscription.bestValue')}
							</Badge>
						</div>
					{/if}

					<CardHeader class="text-center pb-2">
						<CardTitle class="text-xl">{plan.name}</CardTitle>
						{#if plan.discount_percent > 0}
							<Badge variant="secondary" class="w-fit mx-auto mt-1">
								<Sparkles class="h-3 w-3 mr-1" />
								{$t('subscription.save', { percent: plan.discount_percent })}
							</Badge>
						{/if}
					</CardHeader>

					<CardContent class="text-center pb-4">
						<div class="mb-4">
							{#if plan.discount_percent > 0}
								<p class="text-sm text-muted-foreground line-through">
									${getOriginalPrice(plan).toFixed(2)}
								</p>
							{/if}
							<p class="text-4xl font-bold text-primary">${plan.price.toFixed(2)}</p>
							<p class="text-sm text-muted-foreground">
								${getPricePerMonth(plan).toFixed(2)}{$t('subscription.perMonth')}
							</p>
						</div>

						<ul class="text-sm text-left space-y-2 mb-4">
							<li class="flex items-center gap-2">
								<Check class="h-4 w-4 text-green-500 flex-shrink-0" />
								<span>{$t('subscription.unlimitedSearches')}</span>
							</li>
							<li class="flex items-center gap-2">
								<Check class="h-4 w-4 text-green-500 flex-shrink-0" />
								<span>{$t('subscription.databaseOnlyResults')}</span>
							</li>
							<li class="flex items-center gap-2">
								<Check class="h-4 w-4 text-green-500 flex-shrink-0" />
								<span>{$t('subscription.monthsAccess', { months: plan.duration_months })}</span>
							</li>
						</ul>
					</CardContent>

					<CardFooter>
						<Button
							class="w-full"
							variant={isBestValue(plan) ? 'default' : 'outline'}
							onclick={() => handlePurchaseClick(plan.id)}
						>
							{$t('subscription.extendSubscription')}
						</Button>
					</CardFooter>
				</Card>
			{/each}
		</div>
	{:else}
		<!-- NO SUBSCRIPTION VIEW -->

		<!-- Current Subscription Status -->
		<Card class="mb-8">
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<Clock class="h-5 w-5" />
					{$t('subscription.currentStatus')}
				</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="text-center py-4">
					<div class="rounded-full bg-orange-100 p-4 w-16 h-16 mx-auto mb-3 flex items-center justify-center">
						<CreditCard class="h-8 w-8 text-orange-600" />
					</div>
					<p class="text-lg font-medium mb-1">{$t('subscription.noSubscription')}</p>
					<p class="text-muted-foreground">
						{$t('subscription.noSubscriptionDesc')}
					</p>
				</div>
			</CardContent>
		</Card>

		<!-- Subscription Plans -->
		<div class="mb-6">
			<h2 class="text-2xl font-bold mb-2">{$t('subscription.availablePlans')}</h2>
			<p class="text-muted-foreground">{$t('subscription.choosePlan')}</p>
		</div>

		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
			{#each plans as plan (plan.id)}
				<Card
					class="relative transition-all duration-200 hover:shadow-lg {isBestValue(plan)
						? 'border-primary ring-2 ring-primary shadow-md'
						: ''}"
				>
					{#if isBestValue(plan)}
						<div class="absolute -top-3 left-1/2 -translate-x-1/2">
							<Badge class="bg-primary text-primary-foreground flex items-center gap-1">
								<Crown class="h-3 w-3" />
								{$t('subscription.bestValue')}
							</Badge>
						</div>
					{/if}

					<CardHeader class="text-center pb-2">
						<CardTitle class="text-xl">{plan.name}</CardTitle>
						{#if plan.discount_percent > 0}
							<Badge variant="secondary" class="w-fit mx-auto mt-1">
								<Sparkles class="h-3 w-3 mr-1" />
								{$t('subscription.save', { percent: plan.discount_percent })}
							</Badge>
						{/if}
					</CardHeader>

					<CardContent class="text-center pb-4">
						<div class="mb-4">
							{#if plan.discount_percent > 0}
								<p class="text-sm text-muted-foreground line-through">
									${getOriginalPrice(plan).toFixed(2)}
								</p>
							{/if}
							<p class="text-4xl font-bold text-primary">${plan.price.toFixed(2)}</p>
							<p class="text-sm text-muted-foreground">
								${getPricePerMonth(plan).toFixed(2)}{$t('subscription.perMonth')}
							</p>
						</div>

						<ul class="text-sm text-left space-y-2 mb-4">
							<li class="flex items-center gap-2">
								<Check class="h-4 w-4 text-green-500 flex-shrink-0" />
								<span>{$t('subscription.unlimitedSearches')}</span>
							</li>
							<li class="flex items-center gap-2">
								<Check class="h-4 w-4 text-green-500 flex-shrink-0" />
								<span>{$t('subscription.databaseOnlyResults')}</span>
							</li>
							<li class="flex items-center gap-2">
								<Check class="h-4 w-4 text-green-500 flex-shrink-0" />
								<span>{$t('subscription.monthsAccess', { months: plan.duration_months })}</span>
							</li>
						</ul>
					</CardContent>

					<CardFooter>
						<Button
							class="w-full"
							variant={isBestValue(plan) ? 'default' : 'outline'}
							onclick={() => handlePurchaseClick(plan.id)}
						>
							{$t('subscription.purchase')}
						</Button>
					</CardFooter>
				</Card>
			{/each}
		</div>

		<!-- Info Section -->
		<Card class="mt-8 bg-muted/50">
			<CardContent class="pt-6">
				<div class="flex items-start gap-4">
					<div class="rounded-full bg-primary/10 p-3">
						<AlertCircle class="h-6 w-6 text-primary" />
					</div>
					<div>
						<h3 class="font-semibold mb-1">{$t('subscription.importantInfo')}</h3>
						<ul class="text-sm text-muted-foreground space-y-1">
							<li>• {$t('subscription.infoDeducted')}</li>
							<li>• {$t('subscription.infoNoRefund')}</li>
							<li>• {$t('subscription.infoManualRenew')}</li>
							<li>• {$t('subscription.infoAccessExpire')}</li>
						</ul>
					</div>
				</div>
			</CardContent>
		</Card>
	{/if}
</div>

<!-- Confirm Purchase Dialog -->
<Dialog bind:open={showConfirmDialog}>
	<DialogContent>
		<DialogHeader>
			<DialogTitle>{$t('subscription.confirmPurchase')}</DialogTitle>
			<DialogDescription>
				{$t('subscription.confirmPurchaseDesc')}
			</DialogDescription>
		</DialogHeader>

		{#if selectedPlan}
			<div class="py-4 space-y-4">
				<div class="flex justify-between items-center p-4 bg-muted rounded-lg">
					<span class="font-medium">{selectedPlan.name}</span>
					<span class="text-xl font-bold">${selectedPlan.price.toFixed(2)}</span>
				</div>

				<div class="flex justify-between items-center text-sm">
					<span class="text-muted-foreground">{$t('subscription.yourBalance')}:</span>
					<span class="font-medium">{formatCurrency($user?.balance ?? 0)}</span>
				</div>

				{#if ($user?.balance ?? 0) < selectedPlan.price}
					<Alert variant="destructive">
						<AlertCircle class="h-4 w-4" />
						<AlertDescription>
							{$t('subscription.insufficientBalance')}
						</AlertDescription>
					</Alert>
				{/if}

				{#if errorMessage}
					<Alert variant="destructive">
						<AlertCircle class="h-4 w-4" />
						<AlertDescription>{errorMessage}</AlertDescription>
					</Alert>
				{/if}
			</div>
		{/if}

		<DialogFooter>
			<Button variant="outline" onclick={() => (showConfirmDialog = false)} disabled={isPurchasing}>
				{$t('subscription.cancel')}
			</Button>
			<Button
				onclick={handleConfirmPurchase}
				disabled={isPurchasing || !selectedPlan || ($user?.balance ?? 0) < (selectedPlan?.price ?? 0)}
			>
				{#if isPurchasing}
					<Loader2 class="h-4 w-4 mr-2 animate-spin" />
					{$t('subscription.processing')}
				{:else}
					{$t('subscription.confirm')}
				{/if}
			</Button>
		</DialogFooter>
	</DialogContent>
</Dialog>
