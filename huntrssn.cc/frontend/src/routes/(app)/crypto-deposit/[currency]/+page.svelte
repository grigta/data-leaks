<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { user, refreshUser } from '$lib/stores/auth';
  import { createDeposit, type TransactionResponse } from '$lib/api/client';
  import { formatCurrency } from '$lib/utils';
  import { getCryptoOption } from '$lib/constants/crypto';
  import { t } from '$lib/i18n';

  // Components
  import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';
  import { Alert, AlertDescription } from '$lib/components/ui/alert';
  import { Badge } from '$lib/components/ui/badge';

  // Icons
  import { Wallet, Loader2, AlertCircle, CheckCircle, Copy, QrCode, ArrowLeft } from '@lucide/svelte/icons';

  // Get selected crypto from URL
  const selectedCrypto = $derived(getCryptoOption($page.params.currency));

  // Get provider from URL query params
  const selectedProvider = $derived($page.url.searchParams.get('provider') || 'crypto');

  // State
  let amount = $state('20');
  let isProcessing = $state(false);
  let errorMessage = $state('');
  let successMessage = $state('');
  let currentDeposit = $state<TransactionResponse | null>(null);

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

  async function handleDeposit() {
    if (!selectedCrypto) return;

    try {
      isProcessing = true;
      errorMessage = '';
      successMessage = '';

      const amountNum = parseFloat(amount);

      // Validation
      if (isNaN(amountNum) || amountNum <= 0) {
        errorMessage = $t('crypto.messages.invalidAmount');
        return;
      }

      if (amountNum < 5) {
        errorMessage = $t('crypto.messages.minAmountError');
        return;
      }

      if (amountNum > 5000) {
        errorMessage = $t('crypto.messages.maxAmountError');
        return;
      }

      // Create deposit with selected crypto and provider
      // Map provider selection to backend payment_provider value
      let paymentProvider = 'cryptocurrencyapi';
      if (selectedProvider === 'ffio') {
        paymentProvider = 'ffio';
      } else if (selectedProvider === 'helket') {
        paymentProvider = 'helket';
      }

      const deposit = await createDeposit(
        amountNum,
        'crypto',
        selectedCrypto.currency,
        selectedCrypto.network,
        paymentProvider
      );

      currentDeposit = deposit;
      successMessage = $t('crypto.messages.depositCreated');

      await refreshUser();
    } catch (error: any) {
      console.error('Payment failed:', error);
      errorMessage = error.response?.data?.detail || $t('crypto.messages.depositFailed');
    } finally {
      isProcessing = false;
    }
  }

  async function copyAddress() {
    if (currentDeposit?.payment_address) {
      try {
        await navigator.clipboard.writeText(currentDeposit.payment_address);
        successMessage = $t('crypto.depositPage.copied');
      } catch (error) {
        console.error('Failed to copy address:', error);
      }
    }
  }
</script>

<div class="container mx-auto p-6 max-w-7xl">
  <!-- Error/Success Alerts -->
  {#if errorMessage}
    <Alert variant="destructive" class="mb-6">
      <AlertCircle class="h-4 w-4" />
      <AlertDescription>{errorMessage}</AlertDescription>
    </Alert>
  {/if}

  {#if successMessage}
    <Alert class="mb-6 border-success/20 bg-success/10">
      <CheckCircle class="h-4 w-4 text-success" />
      <AlertDescription class="text-success">{successMessage}</AlertDescription>
    </Alert>
  {/if}

  <!-- Validation: check if crypto is valid -->
  {#if !selectedCrypto}
    <Card class="border-red-200">
      <CardHeader>
        <CardTitle class="text-red-600">{$t('crypto.depositPage.title').replace('{{currency}}', 'Unknown')}</CardTitle>
      </CardHeader>
      <CardContent>
        <p class="mb-4 text-muted-foreground">
          {$t('crypto.messages.depositFailed')}
        </p>
        <Button onclick={() => goto('/crypto-deposit')}>
          <ArrowLeft class="mr-2 h-4 w-4" />
          {$t('crypto.depositPage.backToCrypto')}
        </Button>
      </CardContent>
    </Card>
  {:else}
    <!-- Main layout -->
    <div class="flex flex-col gap-6 lg:flex-row">
      <!-- Left Column - Deposit Form -->
      <div class="lg:w-96">
        <!-- Back button -->
        <Button
          variant="ghost"
          class="mb-4"
          onclick={() => goto('/crypto-deposit')}
        >
          <ArrowLeft class="mr-2 h-4 w-4" />
          {$t('crypto.depositPage.backToCrypto')}
        </Button>

        <!-- Selected Crypto Card -->
        <Card class="mb-6">
          <CardHeader>
            <div class="flex items-center gap-3">
              <svelte:component this={selectedCrypto.icon} class="h-8 w-8 {selectedCrypto.color}" />
              <div>
                <CardTitle>{selectedCrypto.name}</CardTitle>
                <p class="text-sm text-muted-foreground">{selectedCrypto.description}</p>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div class="flex gap-2">
              <Badge variant="secondary">{selectedCrypto.network}</Badge>
              <Badge variant="outline">{selectedProvider === 'crypto' ? 'CryptoCurrencyAPI' : selectedProvider === 'ffio' ? 'ff.io' : 'Helket'}</Badge>
            </div>
          </CardContent>
        </Card>

        <!-- Amount Form -->
        <Card>
          <CardHeader>
            <CardTitle class="flex items-center gap-2">
              <Wallet class="h-5 w-5" />
              {$t('crypto.depositPage.title').replace('{{currency}}', selectedCrypto.name)}
            </CardTitle>
          </CardHeader>
          <CardContent class="space-y-4">
            <!-- Current Balance -->
            <div class="rounded-lg bg-muted p-3">
              <p class="text-sm text-muted-foreground">{$t('balance.currentBalance')}</p>
              <p class="text-2xl font-bold">{formatCurrency($user?.balance || 0)}</p>
            </div>

            <!-- Amount Input -->
            <div class="space-y-2">
              <Label for="amount">{$t('crypto.depositPage.amount')}</Label>
              <Input
                id="amount"
                type="number"
                min="5"
                max="5000"
                step="1"
                bind:value={amount}
                placeholder={$t('crypto.depositPage.amountPlaceholder')}
                disabled={isProcessing}
              />
              <p class="text-xs text-muted-foreground">{$t('crypto.depositPage.minAmount')} • {$t('crypto.depositPage.maxAmount')}</p>
            </div>

            <!-- Submit Button -->
            <Button
              class="w-full"
              onclick={handleDeposit}
              disabled={isProcessing}
            >
              {#if isProcessing}
                <Loader2 class="mr-2 h-4 w-4 animate-spin" />
                {$t('crypto.depositPage.creating')}
              {:else}
                {$t('crypto.depositPage.createDeposit')}
              {/if}
            </Button>

            <!-- Info -->
            <p class="text-xs text-muted-foreground">
              {$t('crypto.depositPage.minAmount')} {$t('crypto.depositPage.maxAmount')}
            </p>
          </CardContent>
        </Card>
      </div>

      <!-- Right Column - Payment Details -->
      {#if currentDeposit && currentDeposit.payment_address}
        <div class="flex-1">
          <Card class="border-success/20 bg-success/5">
            <CardHeader>
              <CardTitle class="flex items-center gap-2 text-success">
                <QrCode class="h-5 w-5" />
                {$t('crypto.depositPage.paymentInfo')}
              </CardTitle>
            </CardHeader>
            <CardContent class="space-y-4">
              <!-- Amount -->
              <div class="rounded-lg bg-card p-3">
                <p class="text-sm text-muted-foreground">{$t('crypto.depositPage.amountToPay')}</p>
                <p class="text-2xl font-bold text-success">{formatCurrency(currentDeposit.amount)}</p>
              </div>

              <!-- Crypto Details -->
              <div class="rounded-lg bg-card p-3">
                <p class="text-sm text-muted-foreground">{$t('balance.table.currency')}</p>
                <p class="font-semibold">{currentDeposit.currency || selectedCrypto.currency} ({currentDeposit.network || selectedCrypto.network})</p>
              </div>

              <!-- Payment Address -->
              <div class="space-y-2">
                <Label>{$t('crypto.depositPage.address')}</Label>
                <div class="flex gap-2">
                  <Input
                    value={currentDeposit.payment_address}
                    readonly
                    class="bg-background font-mono text-sm"
                  />
                  <Button size="icon" variant="outline" onclick={copyAddress}>
                    <Copy class="h-4 w-4" />
                  </Button>
                </div>
                <p class="text-xs text-muted-foreground">
                  {$t('crypto.depositPage.amountToPay')}
                </p>
              </div>

              <!-- QR Code if available -->
              {#if currentDeposit.metadata?.qr || currentDeposit.metadata?.qr_code}
                <div class="flex justify-center rounded-lg bg-card p-4">
                  <img
                    src={currentDeposit.metadata.qr || currentDeposit.metadata.qr_code}
                    alt="QR Code"
                    class="h-48 w-48"
                  />
                </div>
              {/if}

              <!-- Warning -->
              {#if selectedProvider === 'ffio'}
                <Alert class="border-warning/50 bg-warning/10">
                  <AlertCircle class="h-4 w-4 text-warning" />
                  <AlertDescription class="text-warning">
                    {$t('crypto.depositPage.ffioWarning')}
                  </AlertDescription>
                </Alert>
              {:else}
                <Alert class="border-warning/50 bg-warning/10">
                  <AlertCircle class="h-4 w-4 text-warning" />
                  <AlertDescription class="text-warning">
                    После оплаты средства поступят автоматически. Обычно это занимает 5-15 минут.
                    Убедитесь, что вы отправляете {currentDeposit.currency || selectedCrypto.currency} в сети {currentDeposit.network || selectedCrypto.network}.
                  </AlertDescription>
                </Alert>
              {/if}
            </CardContent>
          </Card>
        </div>
      {/if}
    </div>
  {/if}
</div>
