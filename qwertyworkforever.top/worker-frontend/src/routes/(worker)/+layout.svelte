<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import {
    getMe,
    getWallet,
    updateWallet,
    createWithdraw,
    getInvoices,
    getCurrentShift,
    startShift,
    pauseShift,
    resumeShift,
    stopShift,
    type WorkerUser,
    type WalletInfo,
    type InvoiceItem,
    type ShiftResponse
  } from '$lib/api/client';

  let { children } = $props();
  let user: WorkerUser | null = $state(null);
  let loading = $state(true);

  // Withdraw dialog
  let showWithdrawDialog = $state(false);
  let walletInfo: WalletInfo | null = $state(null);
  let invoices: InvoiceItem[] = $state([]);
  let walletAddress = $state('');
  let walletNetwork = $state<'erc20' | 'trc20'>('trc20');
  let withdrawAmount = $state('');
  let isLoadingWallet = $state(false);
  let isSavingWallet = $state(false);
  let isWithdrawing = $state(false);
  let walletError = $state('');
  let walletSuccess = $state('');
  let activeWalletTab = $state<'withdraw' | 'history'>('withdraw');
  let hasNewPayout = $state(false);

  // Shift state
  let workerStatus = $state<'idle' | 'active' | 'paused'>('idle');
  let shiftData = $state<ShiftResponse | null>(null);
  let displayElapsed = $state(0);
  let elapsedTimer: ReturnType<typeof setInterval> | null = null;
  let isShiftLoading = $state(false);

  function formatElapsed(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }

  function startElapsedTimer() {
    stopElapsedTimer();
    elapsedTimer = setInterval(() => {
      if (workerStatus === 'active') {
        displayElapsed += 1;
      }
    }, 1000);
  }

  function stopElapsedTimer() {
    if (elapsedTimer) {
      clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  async function loadShift() {
    try {
      const res = await getCurrentShift();
      workerStatus = res.worker_status;
      shiftData = res;
      displayElapsed = res.elapsed_seconds;
      if (workerStatus === 'active' || workerStatus === 'paused') {
        startElapsedTimer();
      }
    } catch {}
  }

  async function handleStartShift() {
    isShiftLoading = true;
    try {
      const res = await startShift();
      workerStatus = res.worker_status;
      shiftData = res;
      displayElapsed = res.elapsed_seconds;
      startElapsedTimer();
    } catch {}
    isShiftLoading = false;
  }

  async function handlePauseShift() {
    isShiftLoading = true;
    try {
      const res = await pauseShift();
      workerStatus = res.worker_status;
      shiftData = res;
      displayElapsed = res.elapsed_seconds;
    } catch {}
    isShiftLoading = false;
  }

  async function handleResumeShift() {
    isShiftLoading = true;
    try {
      const res = await resumeShift();
      workerStatus = res.worker_status;
      shiftData = res;
      displayElapsed = res.elapsed_seconds;
    } catch {}
    isShiftLoading = false;
  }

  async function handleStopShift() {
    isShiftLoading = true;
    try {
      const res = await stopShift();
      workerStatus = 'idle';
      shiftData = null;
      displayElapsed = 0;
      stopElapsedTimer();
    } catch {}
    isShiftLoading = false;
  }

  function handleShiftUpdatedEvent(e: Event) {
    const data = (e as CustomEvent).detail;
    if (data) {
      workerStatus = data.worker_status || 'idle';
      if (workerStatus === 'idle') {
        shiftData = null;
        displayElapsed = 0;
        stopElapsedTimer();
      }
    }
  }

  onMount(async () => {
    const token = localStorage.getItem('worker_token');
    if (!token) {
      goto('/login');
      return;
    }
    try {
      user = await getMe();
    } catch {
      localStorage.removeItem('worker_token');
      goto('/login');
      return;
    }
    loading = false;
    checkNewPayouts();

    // Shift
    loadShift();
    window.addEventListener('shift-updated', handleShiftUpdatedEvent);
  });

  onDestroy(() => {
    stopElapsedTimer();
    if (typeof window !== 'undefined') {
      window.removeEventListener('shift-updated', handleShiftUpdatedEvent);
    }
  });

  async function checkNewPayouts() {
    try {
      const res = await getInvoices(10, 0);
      const lastSeen = localStorage.getItem('last_seen_payout_at') || '';
      const paidInvoices = res.invoices.filter((inv) => inv.status === 'paid' && inv.paid_at);
      if (paidInvoices.length > 0) {
        const newest = paidInvoices.reduce((a, b) =>
          (a.paid_at || '') > (b.paid_at || '') ? a : b
        );
        if (newest.paid_at && newest.paid_at > lastSeen) {
          hasNewPayout = true;
        }
      }
    } catch {}
  }

  function handleLogout() {
    localStorage.removeItem('worker_token');
    goto('/login');
  }

  async function openWithdrawDialog() {
    showWithdrawDialog = true;
    activeWalletTab = 'withdraw';
    isLoadingWallet = true;
    walletError = '';
    walletSuccess = '';
    withdrawAmount = '';
    try {
      walletInfo = await getWallet();
      walletAddress = walletInfo.wallet_address || '';
      walletNetwork = (walletInfo.wallet_network as 'erc20' | 'trc20') || 'trc20';
    } catch (e: any) {
      walletError = e.response?.data?.detail || 'Failed to load wallet';
    }
    isLoadingWallet = false;
  }

  async function handleSaveWallet() {
    if (!walletAddress.trim()) {
      walletError = 'Enter wallet address';
      return;
    }
    isSavingWallet = true;
    walletError = '';
    walletSuccess = '';
    try {
      walletInfo = await updateWallet({
        wallet_address: walletAddress.trim(),
        wallet_network: walletNetwork
      });
      walletSuccess = 'Wallet saved';
      setTimeout(() => (walletSuccess = ''), 3000);
    } catch (e: any) {
      walletError = e.response?.data?.detail || 'Failed to save';
    }
    isSavingWallet = false;
  }

  async function handleWithdraw() {
    const amount = parseFloat(withdrawAmount);
    if (!amount || amount <= 0) {
      walletError = 'Enter valid amount';
      return;
    }
    if (!walletInfo?.wallet_address) {
      walletError = 'Set wallet address first';
      return;
    }
    if (amount > parseFloat(walletInfo.available_balance)) {
      walletError = 'Insufficient balance';
      return;
    }
    isWithdrawing = true;
    walletError = '';
    walletSuccess = '';
    try {
      await createWithdraw({ amount });
      walletSuccess = 'Withdraw request created!';
      withdrawAmount = '';
      walletInfo = await getWallet();
      setTimeout(() => (walletSuccess = ''), 3000);
    } catch (e: any) {
      walletError = e.response?.data?.detail || 'Failed to withdraw';
    }
    isWithdrawing = false;
  }

  async function loadInvoiceHistory() {
    try {
      const res = await getInvoices();
      invoices = res.invoices;
      // Mark payouts as seen
      const paidInvoices = invoices.filter((inv) => inv.status === 'paid' && inv.paid_at);
      if (paidInvoices.length > 0) {
        const newest = paidInvoices.reduce((a, b) =>
          (a.paid_at || '') > (b.paid_at || '') ? a : b
        );
        if (newest.paid_at) {
          localStorage.setItem('last_seen_payout_at', newest.paid_at);
        }
      }
      hasNewPayout = false;
    } catch {
      // Silent fail
    }
  }
</script>

{#if loading}
  <div class="flex min-h-screen items-center justify-center bg-background">
    <svg class="h-8 w-8 animate-spin text-muted-foreground" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
  </div>
{:else}
  <div class="min-h-screen bg-background">
    <header class="border-b border-border">
      <div class="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <h1 class="text-lg font-semibold text-foreground">Worker Portal</h1>
        <div class="flex items-center gap-3">
          <span class="text-sm text-muted-foreground">{user?.username}</span>
          <button
            onclick={openWithdrawDialog}
            class="relative rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-emerald-700"
          >
            Withdraw
            {#if hasNewPayout}
              <span class="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-red-500"></span>
            {/if}
          </button>
          {#if workerStatus === 'idle'}
            <button
              onclick={handleStartShift}
              disabled={isShiftLoading}
              class="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
            >
              {isShiftLoading ? '...' : 'Start Shift'}
            </button>
          {:else}
            <span class="font-mono text-sm tabular-nums {workerStatus === 'paused' ? 'text-orange-500' : 'text-emerald-500'}">
              {formatElapsed(displayElapsed)}
            </span>
            {#if workerStatus === 'active'}
              <button
                onclick={handlePauseShift}
                disabled={isShiftLoading}
                class="rounded-md border border-orange-500/50 px-3 py-1.5 text-sm font-medium text-orange-500 transition-colors hover:bg-orange-500/10 disabled:opacity-50"
              >
                {isShiftLoading ? '...' : 'Pause'}
              </button>
            {:else}
              <button
                onclick={handleResumeShift}
                disabled={isShiftLoading}
                class="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
              >
                {isShiftLoading ? '...' : 'Resume'}
              </button>
            {/if}
            <button
              onclick={handleStopShift}
              disabled={isShiftLoading}
              class="rounded-md border border-red-500/50 px-3 py-1.5 text-sm font-medium text-red-500 transition-colors hover:bg-red-500/10 disabled:opacity-50"
            >
              {isShiftLoading ? '...' : 'Stop'}
            </button>
          {/if}
          <button
            onclick={handleLogout}
            class="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            Logout
          </button>
        </div>
      </div>
    </header>
    <main class="mx-auto max-w-5xl px-4 py-6">
      {@render children()}
    </main>
  </div>

  <!-- Withdraw Dialog -->
  {#if showWithdrawDialog}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onclick={() => (showWithdrawDialog = false)}
    >
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div
        class="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-lg"
        onclick={(e) => e.stopPropagation()}
      >
        <h2 class="text-lg font-semibold mb-4">Withdraw</h2>

        {#if isLoadingWallet}
          <div class="flex justify-center py-8">
            <svg class="h-6 w-6 animate-spin text-muted-foreground" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          </div>
        {:else}
          {#if walletError}
            <div class="mb-3 rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-500">{walletError}</div>
          {/if}
          {#if walletSuccess}
            <div class="mb-3 rounded-md bg-emerald-500/10 px-3 py-2 text-sm text-emerald-500">{walletSuccess}</div>
          {/if}

          <!-- Tabs -->
          <div class="mb-4 flex gap-1 rounded-lg border border-border bg-muted p-1">
            <button
              class="flex-1 rounded-md px-3 py-1.5 text-sm transition-colors {activeWalletTab === 'withdraw' ? 'bg-background shadow-sm font-medium' : 'text-muted-foreground hover:text-foreground'}"
              onclick={() => (activeWalletTab = 'withdraw')}
            >
              Withdraw
            </button>
            <button
              class="relative flex-1 rounded-md px-3 py-1.5 text-sm transition-colors {activeWalletTab === 'history' ? 'bg-background shadow-sm font-medium' : 'text-muted-foreground hover:text-foreground'}"
              onclick={() => {
                activeWalletTab = 'history';
                loadInvoiceHistory();
              }}
            >
              History
              {#if hasNewPayout}
                <span class="absolute right-2 top-1 h-2 w-2 rounded-full bg-red-500"></span>
              {/if}
            </button>
          </div>

          {#if activeWalletTab === 'withdraw'}
            <!-- Balance -->
            <div class="mb-4 rounded-md bg-muted p-4">
              <div class="text-2xl font-bold text-emerald-500">${walletInfo?.available_balance ?? '0.00'}</div>
              <div class="text-xs text-muted-foreground">Available balance</div>
              <div class="mt-1 text-xs text-muted-foreground">
                Earned: ${walletInfo?.total_earned ?? '0.00'} &middot; Paid: ${walletInfo?.total_paid ?? '0.00'}
              </div>
            </div>

            <!-- Wallet Address -->
            <label class="block text-sm text-muted-foreground mb-1">Wallet Address (USDT)</label>
            <input
              type="text"
              bind:value={walletAddress}
              placeholder="0x... or T..."
              class="mb-3 w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            />

            <!-- Network -->
            <label class="block text-sm text-muted-foreground mb-1">Network</label>
            <div class="mb-3 flex gap-2">
              <button
                class="flex-1 rounded-md border px-3 py-2 text-sm transition-colors {walletNetwork === 'trc20' ? 'border-emerald-500 bg-emerald-500/10 text-emerald-500 font-medium' : 'border-border text-muted-foreground hover:border-foreground'}"
                onclick={() => (walletNetwork = 'trc20')}
              >
                USDT TRC20
              </button>
              <button
                class="flex-1 rounded-md border px-3 py-2 text-sm transition-colors {walletNetwork === 'erc20' ? 'border-emerald-500 bg-emerald-500/10 text-emerald-500 font-medium' : 'border-border text-muted-foreground hover:border-foreground'}"
                onclick={() => (walletNetwork = 'erc20')}
              >
                USDT ERC20
              </button>
            </div>

            <!-- Save Wallet -->
            <button
              onclick={handleSaveWallet}
              disabled={isSavingWallet}
              class="mb-4 w-full rounded-md border border-border bg-muted px-3 py-2 text-sm transition-colors hover:bg-accent disabled:opacity-50"
            >
              {isSavingWallet ? 'Saving...' : 'Save Wallet'}
            </button>

            <hr class="mb-4 border-border" />

            <!-- Withdraw Amount -->
            <label class="block text-sm text-muted-foreground mb-1">Amount ($)</label>
            <input
              type="number"
              bind:value={withdrawAmount}
              placeholder="0.00"
              min="0"
              step="0.01"
              class="mb-3 w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            />

            <button
              onclick={handleWithdraw}
              disabled={isWithdrawing || !walletAddress}
              class="w-full rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
            >
              {isWithdrawing ? 'Processing...' : 'Request Withdraw'}
            </button>
          {:else}
            <!-- History tab -->
            {#if invoices.length === 0}
              <p class="text-center text-muted-foreground py-6 text-sm">No invoices yet</p>
            {:else}
              <div class="max-h-80 overflow-y-auto space-y-1">
                {#each invoices as inv}
                  <div class="flex items-center justify-between border-b border-border py-2.5">
                    <div>
                      <div class="font-medium text-sm">${inv.amount}</div>
                      <div class="text-xs text-muted-foreground">
                        {new Date(inv.created_at).toLocaleDateString()} {new Date(inv.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>
                    <span
                      class="text-xs rounded-full px-2 py-0.5 {inv.status === 'paid'
                        ? 'bg-emerald-500/10 text-emerald-500'
                        : 'bg-orange-500/10 text-orange-500'}"
                    >
                      {inv.status}
                    </span>
                  </div>
                {/each}
              </div>
            {/if}
          {/if}
        {/if}

        <button
          onclick={() => (showWithdrawDialog = false)}
          class="mt-4 w-full rounded-md border border-border px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent"
        >
          Close
        </button>
      </div>
    </div>
  {/if}

{/if}
