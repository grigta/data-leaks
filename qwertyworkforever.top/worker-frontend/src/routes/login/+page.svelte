<script lang="ts">
  import { login } from '$lib/api/client';
  import { goto } from '$app/navigation';

  let accessCode = $state('');
  let error = $state('');
  let loading = $state(false);

  async function handleLogin(e: Event) {
    e.preventDefault();
    error = '';
    loading = true;

    try {
      const result = await login({ access_code: accessCode });
      localStorage.setItem('worker_token', result.access_token);
      goto('/dashboard');
    } catch (err: any) {
      error = err.response?.data?.detail || 'Login failed';
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>Worker Login</title>
</svelte:head>

<div class="flex min-h-screen items-center justify-center bg-background px-4">
  <div class="w-full max-w-sm">
    <div class="mb-8 text-center">
      <h1 class="text-2xl font-bold text-foreground">Worker Portal</h1>
      <p class="mt-2 text-sm text-muted-foreground">Enter your access code to sign in</p>
    </div>

    <form onsubmit={handleLogin} class="space-y-4">
      {#if error}
        <div class="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      {/if}

      <div>
        <label for="access-code" class="mb-1.5 block text-sm font-medium text-foreground">Access Code</label>
        <input
          id="access-code"
          type="text"
          bind:value={accessCode}
          required
          autocomplete="off"
          class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-center font-mono text-sm tracking-widest text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background"
          placeholder="XXX-XXX-XXX-XXX"
        />
      </div>

      <button
        type="submit"
        disabled={loading || !accessCode}
        class="inline-flex h-10 w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
      >
        {#if loading}
          <svg class="mr-2 h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          Signing in...
        {:else}
          Sign In
        {/if}
      </button>
    </form>
  </div>
</div>
