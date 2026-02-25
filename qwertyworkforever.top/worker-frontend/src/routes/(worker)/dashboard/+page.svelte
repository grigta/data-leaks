<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import {
    getMyTickets,
    getHistory,
    respondToTicket,
    rejectTicket,
    type Ticket,
    type HistoryStats
  } from '$lib/api/client';

  let myTickets: Ticket[] = $state([]);
  let historyTickets: Ticket[] = $state([]);
  let myCount = $state(0);
  let historyCount = $state(0);
  let historyStats: HistoryStats | null = $state(null);
  let loadingMy = $state(true);
  let loadingHistory = $state(true);
  let submittingId: string | null = $state(null);
  let error = $state('');
  let successMsg = $state('');
  let activeTab: 'my' | 'history' = $state('my');
  let historyPeriod: string | undefined = $state(undefined);

  // Single text input per ticket
  let responseText: Record<string, string> = $state({});

  // Date format preference: 'mdy' = MM/DD, 'dmy' = DD/MM
  let dateFormat: 'mdy' | 'dmy' = $state('mdy');

  // WebSocket for real-time updates
  let ws: WebSocket | null = null;
  let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function connectWebSocket() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = localStorage.getItem('worker_token');
    const wsUrl = token
      ? `${proto}//${location.host}/api/worker/ws?token=${encodeURIComponent(token)}`
      : `${proto}//${location.host}/api/worker/ws`;
    ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event === 'NEW_TICKET') {
          loadMyTickets();
        } else if (msg.event === 'SCHEDULE_UPDATED' && msg.data) {
          window.dispatchEvent(new CustomEvent('schedule-updated', { detail: msg.data }));
        }
      } catch {}
    };

    ws.onclose = () => {
      ws = null;
      wsReconnectTimer = setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = () => {
      ws?.close();
    };
  }

  onMount(() => {
    // Load date format preference
    const saved = localStorage.getItem('worker_date_format');
    if (saved === 'dmy' || saved === 'mdy') dateFormat = saved;

    loadMyTickets();
    connectWebSocket();
  });

  onDestroy(() => {
    if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
    if (ws) {
      ws.onclose = null;
      ws.close();
    }
  });

  async function loadMyTickets() {
    try {
      const res = await getMyTickets();
      myTickets = res.tickets;
      myCount = res.total_count;
    } catch (e: any) {
      if (!loadingMy) return;
      error = e.response?.data?.detail || 'Failed to load tickets';
    }
    loadingMy = false;
  }

  async function loadHistory(period?: string) {
    loadingHistory = true;
    try {
      const res = await getHistory(period);
      historyTickets = res.tickets;
      historyCount = res.total_count;
      historyStats = res.stats;
    } catch (e: any) {
      error = e.response?.data?.detail || 'Failed to load history';
    }
    loadingHistory = false;
  }

  function switchTab(tab: 'my' | 'history') {
    activeTab = tab;
    if (tab === 'history' && historyStats === null) {
      loadHistory(historyPeriod);
    }
  }

  function setPeriod(period?: string) {
    historyPeriod = period;
    loadHistory(period);
  }

  async function handleRespond(ticketId: string) {
    const text = (responseText[ticketId] || '').trim();
    if (!text) {
      error = 'Enter SSN (and optionally DOB)';
      return;
    }

    submittingId = ticketId;
    error = '';

    try {
      await respondToTicket(ticketId, text);
      successMsg = 'Submitted!';
      setTimeout(() => (successMsg = ''), 3000);
      delete responseText[ticketId];
      await loadMyTickets();
    } catch (e: any) {
      error = e.response?.data?.detail || 'Failed to submit';
    }
    submittingId = null;
  }

  async function handleReject(ticketId: string) {
    submittingId = ticketId;
    error = '';
    try {
      await rejectTicket(ticketId);
      successMsg = 'Ticket rejected. User refunded.';
      setTimeout(() => (successMsg = ''), 3000);
      await loadMyTickets();
    } catch (e: any) {
      error = e.response?.data?.detail || 'Failed to reject';
    }
    submittingId = null;
  }

  function handleKeydown(e: KeyboardEvent, ticketId: string) {
    if (e.key === 'Enter') {
      handleRespond(ticketId);
    }
  }

  function setDateFormat(fmt: 'mdy' | 'dmy') {
    dateFormat = fmt;
    localStorage.setItem('worker_date_format', fmt);
  }

  let copiedField: string | null = $state(null);

  async function copyText(text: string, fieldId: string) {
    try {
      await navigator.clipboard.writeText(text);
      copiedField = fieldId;
      setTimeout(() => { if (copiedField === fieldId) copiedField = null; }, 1500);
    } catch {}
  }

  function formatDate(iso: string): string {
    const d = new Date(iso);
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const mins = String(d.getMinutes()).padStart(2, '0');
    if (dateFormat === 'dmy') {
      return `${day}/${month} ${hours}:${mins}`;
    }
    return `${month}/${day} ${hours}:${mins}`;
  }
</script>

<svelte:head>
  <title>Dashboard — Worker Portal</title>
</svelte:head>

{#if error}
  <div class="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
    {error}
    <button onclick={() => (error = '')} class="float-right font-bold">&times;</button>
  </div>
{/if}

{#if successMsg}
  <div class="mb-4 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
    {successMsg}
  </div>
{/if}

<!-- Date format selector -->
<div class="mb-4 flex items-center justify-end gap-1.5">
  <span class="text-xs text-muted-foreground">Date:</span>
  <button
    onclick={() => setDateFormat('mdy')}
    class="rounded px-2 py-0.5 text-xs font-medium transition-colors {dateFormat === 'mdy' ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground'}"
  >
    MM/DD
  </button>
  <button
    onclick={() => setDateFormat('dmy')}
    class="rounded px-2 py-0.5 text-xs font-medium transition-colors {dateFormat === 'dmy' ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground'}"
  >
    DD/MM
  </button>
</div>

<!-- Tabs -->
<div class="mb-6 flex gap-1 rounded-lg border border-border bg-secondary p-1">
  <button
    onclick={() => switchTab('my')}
    class="flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors {activeTab === 'my' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}"
  >
    My Orders ({myCount})
  </button>
  <button
    onclick={() => switchTab('history')}
    class="flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors {activeTab === 'history' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}"
  >
    Panel {historyStats ? `(${historyStats.total})` : ''}
  </button>
</div>

<!-- My Orders -->
{#if activeTab === 'my'}
  {#if loadingMy}
    <div class="flex justify-center py-12">
      <svg class="h-6 w-6 animate-spin text-muted-foreground" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
    </div>
  {:else if myTickets.length === 0}
    <div class="py-12 text-center text-muted-foreground">No active tickets</div>
  {:else}
    <div class="space-y-4">
      {#each myTickets as ticket (ticket.id)}
        <div class="rounded-lg border border-border bg-card p-4">
          <div class="mb-3 flex items-start justify-between">
            <div class="min-w-0 flex-1 mr-3">
              <button
                type="button"
                onclick={() => copyText(`${ticket.firstname} ${ticket.lastname}`, `name-${ticket.id}`)}
                class="block w-full text-left text-sm font-medium text-foreground transition-colors hover:text-primary cursor-pointer"
              >
                {ticket.firstname} {ticket.lastname}
                {#if copiedField === `name-${ticket.id}`}
                  <span class="ml-1 text-xs text-success">copied</span>
                {/if}
              </button>
              <button
                type="button"
                onclick={() => copyText(ticket.address, `addr-${ticket.id}`)}
                class="block w-full text-left text-sm text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
              >
                {ticket.address}
                {#if copiedField === `addr-${ticket.id}`}
                  <span class="ml-1 text-xs text-success">copied</span>
                {/if}
              </button>
            </div>
            <div class="flex flex-col items-end gap-1 shrink-0">
              <span
                class="rounded-full px-2.5 py-0.5 text-xs font-medium bg-warning/10 text-warning"
              >
                {ticket.status}
              </span>
              <span class="text-xs text-muted-foreground">
                {formatDate(ticket.created_at)}
              </span>
            </div>
          </div>

          <!-- Quick response input -->
          <div class="border-t border-border pt-3">
            <div class="flex gap-2">
              <input
                type="text"
                bind:value={responseText[ticket.id]}
                onkeydown={(e) => handleKeydown(e, ticket.id)}
                placeholder="123-45-6789 01/15/1985"
                class="flex h-9 flex-1 rounded-md border border-input bg-background px-3 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <button
                onclick={() => handleRespond(ticket.id)}
                disabled={submittingId === ticket.id || !responseText[ticket.id]?.trim()}
                class="rounded-md bg-success px-4 py-2 text-sm font-medium text-success-foreground transition-colors hover:bg-success/90 disabled:opacity-50"
              >
                {submittingId === ticket.id ? '...' : 'Submit'}
              </button>
              <button
                onclick={() => handleReject(ticket.id)}
                disabled={submittingId === ticket.id}
                class="rounded-md border border-destructive/30 px-4 py-2 text-sm font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
              >
                NF
              </button>
            </div>
            <p class="mt-1 text-xs text-muted-foreground">Paste SSN and DOB in one line, then Submit. Or press NF if not found.</p>
          </div>
        </div>
      {/each}
    </div>
  {/if}
{/if}

<!-- History -->
{#if activeTab === 'history'}
  {#if loadingHistory}
    <div class="flex justify-center py-12">
      <svg class="h-6 w-6 animate-spin text-muted-foreground" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
    </div>
  {:else}
    <!-- Stats -->
    {#if historyStats}
      <div class="mb-4 grid grid-cols-3 gap-3 sm:grid-cols-6">
        <div class="rounded-lg border border-border bg-card p-3 text-center">
          <div class="text-2xl font-bold text-foreground">{historyStats.total}</div>
          <div class="text-xs text-muted-foreground">Total</div>
        </div>
        <div class="rounded-lg border border-border bg-card p-3 text-center">
          <div class="text-2xl font-bold text-success">{historyStats.completed}</div>
          <div class="text-xs text-muted-foreground">Completed</div>
        </div>
        <div class="rounded-lg border border-border bg-card p-3 text-center">
          <div class="text-2xl font-bold text-destructive">{historyStats.rejected}</div>
          <div class="text-xs text-muted-foreground">Not Found</div>
        </div>
        <div class="rounded-lg border border-border bg-card p-3 text-center">
          <div class="text-2xl font-bold text-foreground">{historyStats.success_rate}%</div>
          <div class="text-xs text-muted-foreground">Success Rate</div>
        </div>
        <div class="rounded-lg border border-border bg-card p-3 text-center">
          <div class="text-2xl font-bold text-foreground">{historyStats.avg_time}</div>
          <div class="text-xs text-muted-foreground">Avg Time</div>
        </div>
        <div class="rounded-lg border border-border bg-card p-3 text-center">
          <div class="text-2xl font-bold text-success">${historyStats.payout}</div>
          <div class="text-xs text-muted-foreground">Payout</div>
        </div>
      </div>

      <!-- Period filter -->
      <div class="mb-6 flex items-center justify-center gap-2">
        {#each [{ key: '24h', label: '24h' }, { key: '7d', label: '7d' }, { key: '30d', label: '30d' }, { key: undefined, label: 'All' }] as opt}
          <button
            onclick={() => setPeriod(opt.key)}
            class="rounded-lg border px-4 py-1.5 text-sm font-medium transition-colors {historyPeriod === opt.key ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card text-muted-foreground hover:text-foreground'}"
          >
            {opt.label}
          </button>
        {/each}
      </div>
    {/if}

    <!-- Tickets list -->
    {#if historyTickets.length === 0}
      <div class="py-12 text-center text-muted-foreground">No history yet</div>
    {:else}
      <div class="space-y-3">
        {#each historyTickets as ticket (ticket.id)}
          <div class="rounded-lg border border-border bg-card p-4">
            <div class="flex items-start justify-between">
              <div>
                <div class="text-sm font-medium text-foreground">
                  {ticket.firstname} {ticket.lastname}
                </div>
                <div class="text-sm text-muted-foreground">{ticket.address}</div>
                <div class="text-xs text-muted-foreground">
                  {formatDate(ticket.updated_at)}
                </div>
              </div>
              <span
                class="rounded-full px-2.5 py-0.5 text-xs font-medium
                  {ticket.status === 'completed' ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}"
              >
                {ticket.status}
              </span>
            </div>

            {#if ticket.status === 'completed' && ticket.response_data}
              <div class="mt-2 rounded-md bg-secondary p-3">
                <div class="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
                  {#each Object.entries(ticket.response_data) as [key, value]}
                    <div>
                      <span class="text-muted-foreground">{key}:</span>
                      <span class="ml-1 font-mono text-foreground">{value}</span>
                    </div>
                  {/each}
                </div>
              </div>
            {:else if ticket.status === 'rejected'}
              <div class="mt-2 rounded-md bg-destructive/5 p-3 text-sm text-destructive">
                Not found — user refunded
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
{/if}
