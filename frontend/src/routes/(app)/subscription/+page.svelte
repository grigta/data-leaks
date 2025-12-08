<script lang="ts">
	import { onMount } from 'svelte';
	import { user, refreshUser } from '$lib/stores/auth';
	import {
		getSubscriptionPlans,
		purchaseSubscription,
		getMySubscription,
		handleApiError,
		type SubscriptionPlanResponse,
		type SubscriptionResponse
	} from '$lib/api/client';
	import { formatCurrency } from '$lib/utils';
	import { t } from '$lib/i18n';
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Alert, AlertDescription, AlertTitle } from '$lib/components/ui/alert';
	import {
		Dialog,
		DialogContent,
		DialogDescription,
		DialogFooter,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import CreditCard from '@lucide/svelte/icons/credit-card';
	import Check from '@lucide/svelte/icons/check';
	import Clock from '@lucide/svelte/icons/clock';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Crown from '@lucide/svelte/icons/crown';
	import Sparkles from '@lucide/svelte/icons/sparkles';

	// State
	let plans = $state<SubscriptionPlanResponse[]>([]);
	let currentSubscription = $state<SubscriptionResponse | null>(null);
	let isLoading = $state(true);
	let isPurchasing = $state(false);
	let selectedPlanId = $state<string | null>(null);
	let showConfirmDialog = $state(false);
	let errorMessage = $state('');
	let successMessage = $state('');

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
			successMessage = 'Subscription purchased successfully!';
			toast.success('Subscription activated!', {
				description: `Your ${subscription.plan.name} subscription is now active.`
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
</script>

<svelte:head>
	<title>Subscription - Lookup SSN Access</title>
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
			<AlertTitle>Error</AlertTitle>
			<AlertDescription>{errorMessage}</AlertDescription>
		</Alert>
	{/if}

	{#if successMessage}
		<Alert class="mb-6 border-green-500 bg-green-50 text-green-700">
			<Check class="h-4 w-4" />
			<AlertTitle>Success</AlertTitle>
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
	{:else}
		<!-- Current Subscription Status -->
		<Card class="mb-8">
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<Clock class="h-5 w-5" />
					{$t('subscription.currentStatus')}
				</CardTitle>
			</CardHeader>
			<CardContent>
				{#if currentSubscription}
					<div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
						<div>
							<div class="flex items-center gap-2 mb-2">
								<Badge variant="default" class="bg-green-500">Active</Badge>
								<span class="font-semibold text-lg">{currentSubscription.plan.name}</span>
							</div>
							<div class="text-sm text-muted-foreground space-y-1">
								<p>Started: {formatDate(currentSubscription.start_date)}</p>
								<p>Expires: {formatDate(currentSubscription.end_date)}</p>
								<p class="font-medium text-foreground">
									{getDaysRemaining()} days remaining
								</p>
							</div>
						</div>
						{#if isExpiringSoon()}
							<Alert variant="destructive" class="md:max-w-xs">
								<AlertCircle class="h-4 w-4" />
								<AlertDescription>
									Your subscription is expiring soon! Renew to maintain access.
								</AlertDescription>
							</Alert>
						{/if}
					</div>
				{:else}
					<div class="text-center py-4">
						<div class="rounded-full bg-orange-100 p-4 w-16 h-16 mx-auto mb-3 flex items-center justify-center">
							<CreditCard class="h-8 w-8 text-orange-600" />
						</div>
						<p class="text-lg font-medium mb-1">{$t('subscription.noSubscription')}</p>
						<p class="text-muted-foreground">
							{$t('subscription.noSubscriptionDesc')}
						</p>
					</div>
				{/if}
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
								Best Value
							</Badge>
						</div>
					{/if}

					<CardHeader class="text-center pb-2">
						<CardTitle class="text-xl">{plan.name}</CardTitle>
						{#if plan.discount_percent > 0}
							<Badge variant="secondary" class="w-fit mx-auto mt-1">
								<Sparkles class="h-3 w-3 mr-1" />
								Save {plan.discount_percent}%
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
								${getPricePerMonth(plan).toFixed(2)}/month
							</p>
						</div>

						<ul class="text-sm text-left space-y-2 mb-4">
							<li class="flex items-center gap-2">
								<Check class="h-4 w-4 text-green-500 flex-shrink-0" />
								<span>Unlimited Lookup SSN searches</span>
							</li>
							<li class="flex items-center gap-2">
								<Check class="h-4 w-4 text-green-500 flex-shrink-0" />
								<span>Database-only results</span>
							</li>
							<li class="flex items-center gap-2">
								<Check class="h-4 w-4 text-green-500 flex-shrink-0" />
								<span>{plan.duration_months} month{plan.duration_months > 1 ? 's' : ''} access</span>
							</li>
						</ul>
					</CardContent>

					<CardFooter>
						<Button
							class="w-full"
							variant={isBestValue(plan) ? 'default' : 'outline'}
							disabled={!!currentSubscription || isPurchasing}
							onclick={() => handlePurchaseClick(plan.id)}
						>
							{#if currentSubscription}
								Already Subscribed
							{:else}
								Purchase
							{/if}
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
			<DialogTitle>Confirm Subscription Purchase</DialogTitle>
			<DialogDescription>
				You are about to purchase a subscription plan. This action will deduct the amount from your
				balance.
			</DialogDescription>
		</DialogHeader>

		{#if selectedPlan}
			<div class="py-4 space-y-4">
				<div class="flex justify-between items-center p-4 bg-muted rounded-lg">
					<span class="font-medium">{selectedPlan.name}</span>
					<span class="text-xl font-bold">${selectedPlan.price.toFixed(2)}</span>
				</div>

				<div class="flex justify-between items-center text-sm">
					<span class="text-muted-foreground">Your current balance:</span>
					<span class="font-medium">{formatCurrency($user?.balance ?? 0)}</span>
				</div>

				{#if ($user?.balance ?? 0) < selectedPlan.price}
					<Alert variant="destructive">
						<AlertCircle class="h-4 w-4" />
						<AlertDescription>
							Insufficient balance. Please deposit funds before purchasing.
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
				Cancel
			</Button>
			<Button
				onclick={handleConfirmPurchase}
				disabled={isPurchasing || !selectedPlan || ($user?.balance ?? 0) < (selectedPlan?.price ?? 0)}
			>
				{#if isPurchasing}
					<Loader2 class="h-4 w-4 mr-2 animate-spin" />
					Processing...
				{:else}
					Confirm Purchase
				{/if}
			</Button>
		</DialogFooter>
	</DialogContent>
</Dialog>
