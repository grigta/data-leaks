<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
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

<div class="container mx-auto max-w-7xl space-y-6 p-6">
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

	<!-- Main Content - Two Columns -->
	<div class="flex flex-col gap-6 lg:flex-row lg:items-stretch">
		<!-- Left Column - Add Funds -->
		<div class="w-full shrink-0 lg:w-96">
			<Card class="border h-full flex flex-col">
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<Wallet class="h-5 w-5" />
						{$t('balance.addFunds')}
					</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4 flex-1">
					<!-- Current Balance Display -->
					<div class="rounded-lg bg-muted/50 p-4">
						<p class="text-sm text-muted-foreground">{$t('balance.currentBalance')}</p>
						<p class="text-2xl font-bold">{formatCurrency($user?.balance || 0)}</p>
					</div>

					<!-- Total Deposits Display -->
					<div class="rounded-lg bg-muted/30 p-3">
						<p class="text-xs text-muted-foreground">{$t('balance.totalDeposits')}</p>
						<p class="text-lg font-semibold text-muted-foreground">{formatCurrency(totalTopUp)}</p>
					</div>
				</CardContent>
				<CardFooter>
					<Button
						class="w-full bg-white hover:bg-gray-100 text-black dark:bg-white dark:hover:bg-gray-200 dark:text-black"
						onclick={() => goto('/crypto-deposit')}
					>
						<Wallet class="mr-2 h-4 w-4" />
						{$t('balance.addFunds')}
					</Button>
				</CardFooter>
			</Card>
		</div>

		<!-- Right Column - Invoices -->
		<div class="flex-1">
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
							<Receipt class="mb-4 h-16 w-16 text-gray-400" />
							<h2 class="mb-2 text-xl font-semibold">{$t('balance.noTransactions')}</h2>
							<p class="text-gray-500">{$t('balance.noTransactions')}</p>
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
	</div>
</div>
