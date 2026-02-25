<script lang="ts">
	import { onMount } from 'svelte';
	import { user, refreshUser } from '$lib/stores/auth';
	import { createDeposit, getTransactions, type TransactionResponse } from '$lib/api/client';
	import { formatCurrency, formatDate } from '$lib/utils';
	import { t } from '$lib/i18n';

	// Components
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';

	// Icons
	import Wallet from '@lucide/svelte/icons/wallet';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import CheckCircle from '@lucide/svelte/icons/check-circle';
	import Receipt from '@lucide/svelte/icons/receipt';
	import Copy from '@lucide/svelte/icons/copy';
	import QrCode from '@lucide/svelte/icons/qr-code';
	import TrendingUp from '@lucide/svelte/icons/trending-up';
	import Hash from '@lucide/svelte/icons/hash';

	// State
	let amount = $state('20');
	let isProcessing = $state(false);
	let isLoading = $state(true);
	let transactions = $state<TransactionResponse[]>([]);
	let totalTopUp = $state(0);
	let errorMessage = $state('');
	let successMessage = $state('');
	let currentDeposit = $state<TransactionResponse | null>(null);

	// Lifecycle
	onMount(async () => {
		// Load transactions and refresh user data in parallel
		await Promise.all([
			loadTransactions(),
			refreshUser()
		]);
	});

	// Auto-dismiss messages
	$effect(() => {
		if (successMessage) {
			const timer = setTimeout(() => {
				successMessage = '';
			}, 3000);
			return () => clearTimeout(timer);
		}
	});

	$effect(() => {
		if (errorMessage) {
			const timer = setTimeout(() => {
				errorMessage = '';
			}, 5000);
			return () => clearTimeout(timer);
		}
	});

	// Functions
	async function loadTransactions() {
		try {
			isLoading = true;
			const response = await getTransactions(undefined, 100, 0);
			transactions = response.transactions;

			// Calculate total top-up (only paid transactions)
			totalTopUp = transactions
				.filter(t => t.status === 'paid')
				.reduce((sum, t) => sum + t.amount, 0);
		} catch (error) {
			console.error('Failed to load transactions:', error);
			errorMessage = $t('balance.messages.loadFailed');
		} finally {
			isLoading = false;
		}
	}

	async function handlePay() {
		try {
			isProcessing = true;
			errorMessage = '';
			successMessage = '';

			const amountNum = parseFloat(amount);

			// Validation
			if (isNaN(amountNum) || amountNum <= 0) {
				errorMessage = $t('balance.messages.invalidAmount');
				return;
			}

			if (amountNum < 5) {
				errorMessage = $t('balance.messages.minAmountError');
				return;
			}

			if (amountNum > 5000) {
				errorMessage = $t('balance.messages.maxAmountError');
				return;
			}

			// Create deposit
			const deposit = await createDeposit(amountNum, 'crypto');

			// Store current deposit to show payment address
			currentDeposit = deposit;

			successMessage = $t('balance.messages.transactionCreated');

			// Reload transactions and user
			await loadTransactions();
			await refreshUser();

			// Reset form
			amount = '20';
		} catch (error: any) {
			console.error('Payment failed:', error);
			errorMessage = error.response?.data?.detail || $t('balance.messages.transactionFailed');
		} finally {
			isProcessing = false;
		}
	}

	function getStatusBadgeClass(status: string): string {
		switch (status.toLowerCase()) {
			case 'paid':
				return 'badge-success';
			case 'expired':
			case 'failed':
				return 'badge-error';
			case 'pending':
				return 'badge-warning';
			default:
				return '';
		}
	}

	function getStatusLabel(status: string): string {
		switch (status.toLowerCase()) {
			case 'paid':
				return $t('balance.statuses.paid');
			case 'expired':
				return $t('balance.statuses.expired');
			case 'failed':
				return $t('balance.statuses.failed');
			case 'pending':
				return $t('balance.statuses.pending');
			default:
				return status;
		}
	}

	async function copyAddress() {
		if (currentDeposit?.payment_address) {
			try {
				await navigator.clipboard.writeText(currentDeposit.payment_address);
				successMessage = $t('balance.addressCopied');
			} catch (error) {
				console.error('Failed to copy address:', error);
			}
		}
	}
</script>

<div class="container mx-auto max-w-5xl space-y-6 p-6">
	<!-- Page Title -->
	<div class="flex items-center justify-between">
		<h1 class="text-3xl font-bold">{$t('balance.title')}</h1>
	</div>

	<!-- Error Alert -->
	{#if errorMessage}
		<Alert variant="destructive">
			<AlertCircle class="h-4 w-4" />
			<AlertDescription>{errorMessage}</AlertDescription>
		</Alert>
	{/if}

	<!-- Success Alert -->
	{#if successMessage}
		<Alert class="border-success/20 bg-success/10 text-success">
			<CheckCircle class="h-4 w-4" />
			<AlertDescription>{successMessage}</AlertDescription>
		</Alert>
	{/if}

	<!-- Stats Bar -->
	<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
		<!-- Balance Card -->
		<Card class="border overflow-hidden">
			<div class="h-1 bg-foreground"></div>
			<CardContent class="pt-4 pb-4">
				<div class="flex items-center gap-2 text-sm text-muted-foreground mb-1">
					<Wallet class="h-4 w-4" />
					{$t('balance.currentBalance')}
				</div>
				<p class="text-3xl font-bold tabular-nums">{formatCurrency($user?.balance || 0)}</p>
			</CardContent>
		</Card>

		<!-- Total Deposits Card -->
		<Card class="border overflow-hidden">
			<div class="h-1 bg-foreground"></div>
			<CardContent class="pt-4 pb-4">
				<div class="flex items-center gap-2 text-sm text-muted-foreground mb-1">
					<TrendingUp class="h-4 w-4" />
					{$t('balance.totalDeposits')}
				</div>
				<p class="text-3xl font-bold tabular-nums">{formatCurrency(totalTopUp)}</p>
			</CardContent>
		</Card>

		<!-- Transaction Count Card -->
		<Card class="border overflow-hidden">
			<div class="h-1 bg-foreground"></div>
			<CardContent class="pt-4 pb-4">
				<div class="flex items-center gap-2 text-sm text-muted-foreground mb-1">
					<Hash class="h-4 w-4" />
					{$t('balance.transactionCount')}
				</div>
				<p class="text-3xl font-bold tabular-nums">{transactions.length}</p>
			</CardContent>
		</Card>
	</div>

	<!-- Add Funds Button -->
	<Button
		class="w-full bg-white hover:bg-gray-100 text-black border border-black/20 dark:bg-white dark:hover:bg-gray-200 dark:text-black dark:border-transparent"
		size="lg"
		onclick={handlePay}
		disabled={isProcessing}
	>
		{#if isProcessing}
			<Loader2 class="mr-2 h-4 w-4 animate-spin" />
		{:else}
			<Wallet class="mr-2 h-4 w-4" />
		{/if}
		{$t('balance.addFunds')}
	</Button>

	<!-- Transaction History -->
	<Card class="border">
		<CardHeader>
			<CardTitle class="flex items-center gap-2">
				<Receipt class="h-5 w-5" />
				{$t('balance.transactionHistory')}
			</CardTitle>
		</CardHeader>
		<CardContent class="p-0">
			{#if isLoading}
				<div class="space-y-2 p-6">
					{#each Array(5) as _}
						<Skeleton class="h-12 w-full" />
					{/each}
				</div>
			{:else if transactions.length === 0}
				<div class="flex flex-col items-center justify-center py-12">
					<Receipt class="mb-4 h-16 w-16 text-muted-foreground/30" />
					<h2 class="mb-2 text-xl font-semibold">{$t('balance.noTransactions')}</h2>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>{$t('balance.table.date')}</TableHead>
								<TableHead class="text-right">{$t('balance.table.amount')}</TableHead>
								<TableHead>{$t('balance.table.status')}</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each transactions as transaction (transaction.id)}
								<TableRow>
									<TableCell class="text-sm">
										{formatDate(transaction.created_at)}
									</TableCell>
									<TableCell class="text-right font-semibold">
										{formatCurrency(transaction.amount)}
									</TableCell>
									<TableCell>
										<Badge class={getStatusBadgeClass(transaction.status)}>
											{getStatusLabel(transaction.status)}
										</Badge>
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
