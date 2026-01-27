<script lang="ts">
  import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '$lib/components/ui/dialog';
  import Button from '$lib/components/ui/button/button.svelte';
  import { Label } from '$lib/components/ui/label';
  import Copy from '@lucide/svelte/icons/copy';
  import Check from '@lucide/svelte/icons/check';
  import type { InstantSSNResult } from '$lib/api/client';

  interface Props {
    open: boolean;
    result: InstantSSNResult | null;
    onClose: () => void;
  }

  let { open, result, onClose }: Props = $props();

  let copiedFields = $state<Set<string>>(new Set());
  let copiedAll = $state(false);

  async function copyToClipboard(text: string, fieldName: string) {
    try {
      await navigator.clipboard.writeText(text);
      copiedFields.add(fieldName);
      copiedFields = copiedFields; // trigger reactivity

      // Reset after 2 seconds
      setTimeout(() => {
        copiedFields.delete(fieldName);
        copiedFields = copiedFields;
      }, 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }

  async function copyAllData() {
    if (!result) return;

    const fullName = `${result.firstname}${result.middlename ? ' ' + result.middlename : ''} ${result.lastname}`;
    const addressLine = result.address || 'N/A';
    const cityState = result.city && result.state ? `${result.city}, ${result.state} ${result.zip_code || ''}` : 'N/A';
    const dob = result.dob || 'N/A';
    const ssn = result.ssn || 'N/A';
    const phone = result.phone || 'N/A';
    const email = result.email || 'N/A';

    const text = `${fullName}
${addressLine}
${cityState}
DOB: ${dob}
SSN: ${ssn}
Phone: ${phone}
Email: ${email}`;

    try {
      await navigator.clipboard.writeText(text);
      copiedAll = true;

      // Reset after 2 seconds
      setTimeout(() => {
        copiedAll = false;
      }, 2000);
    } catch (err) {
      console.error('Failed to copy all:', err);
    }
  }

  function handleClose() {
    // Reset copied states when closing
    copiedFields = new Set();
    copiedAll = false;
    onClose();
  }
</script>

<Dialog {open} onOpenChange={(isOpen) => { if (!isOpen) handleClose(); }}>
  <DialogContent class="sm:max-w-lg">
    <DialogHeader>
      <DialogTitle class="text-2xl">Result Details</DialogTitle>
    </DialogHeader>

    {#if !result}
      <div class="flex items-center justify-center py-8 text-muted-foreground">
        <p>No data available</p>
      </div>
    {:else if result}
      <div class="space-y-4 py-4">
        <!-- Full Name Section -->
        <div class="border-b pb-3">
          <h3 class="text-2xl font-bold">
            {result.firstname}{result.middlename ? ' ' + result.middlename : ''} {result.lastname}
          </h3>
        </div>

        <!-- Address Section -->
        <div class="space-y-2 border-b pb-3">
          <div>
            <Label class="text-sm font-semibold text-muted-foreground">Address</Label>
            <p class="text-base">{result.address || 'N/A'}</p>
          </div>
          <div>
            <Label class="text-sm font-semibold text-muted-foreground">City, State</Label>
            <p class="text-base">
              {#if result.city && result.state}
                {result.city}, {result.state}
              {:else}
                N/A
              {/if}
            </p>
          </div>
          <div>
            <Label class="text-sm font-semibold text-muted-foreground">ZIP Code</Label>
            <p class="text-base">{result.zip_code || 'N/A'}</p>
          </div>
        </div>

        <!-- SSN and DOB Section (Two Columns) -->
        <div class="grid grid-cols-2 gap-4 border-b pb-3">
          <!-- SSN -->
          <div class="space-y-1">
            <Label class="text-sm font-semibold text-muted-foreground">SSN</Label>
            <div class="flex items-center gap-2">
              <p class="text-lg font-mono font-semibold">{result.ssn || 'N/A'}</p>
              {#if result.ssn}
                <button
                  type="button"
                  class="p-1 hover:bg-gray-100 rounded transition-colors"
                  onclick={() => copyToClipboard(result.ssn || '', 'ssn')}
                >
                  {#if copiedFields.has('ssn')}
                    <Check class="h-4 w-4 text-green-600" />
                  {:else}
                    <Copy class="h-4 w-4 text-gray-600" />
                  {/if}
                </button>
              {/if}
            </div>
          </div>

          <!-- DOB -->
          <div class="space-y-1">
            <Label class="text-sm font-semibold text-muted-foreground">DOB</Label>
            <div class="flex items-center gap-2">
              <p class="text-lg font-medium">{result.dob || 'N/A'}</p>
              {#if result.dob}
                <button
                  type="button"
                  class="p-1 hover:bg-gray-100 rounded transition-colors"
                  onclick={() => copyToClipboard(result.dob || '', 'dob')}
                >
                  {#if copiedFields.has('dob')}
                    <Check class="h-4 w-4 text-green-600" />
                  {:else}
                    <Copy class="h-4 w-4 text-gray-600" />
                  {/if}
                </button>
              {/if}
            </div>
          </div>
        </div>

        <!-- Phone and Email Section -->
        <div class="space-y-3">
          <div>
            <Label class="text-sm font-semibold text-muted-foreground">Phone</Label>
            <div class="flex items-center gap-2">
              <p class="text-base font-mono">{result.phone || 'N/A'}</p>
              {#if result.phone}
                <button
                  type="button"
                  class="p-1 hover:bg-gray-100 rounded transition-colors"
                  onclick={() => copyToClipboard(result.phone || '', 'phone')}
                >
                  {#if copiedFields.has('phone')}
                    <Check class="h-4 w-4 text-green-600" />
                  {:else}
                    <Copy class="h-4 w-4 text-gray-600" />
                  {/if}
                </button>
              {/if}
            </div>
          </div>

          <div>
            <Label class="text-sm font-semibold text-muted-foreground">Email</Label>
            <div class="flex items-center gap-2">
              <p class="text-base">{result.email || 'N/A'}</p>
              {#if result.email}
                <button
                  type="button"
                  class="p-1 hover:bg-gray-100 rounded transition-colors"
                  onclick={() => copyToClipboard(result.email || '', 'email')}
                >
                  {#if copiedFields.has('email')}
                    <Check class="h-4 w-4 text-green-600" />
                  {:else}
                    <Copy class="h-4 w-4 text-gray-600" />
                  {/if}
                </button>
              {/if}
            </div>
          </div>
        </div>
      </div>

      <DialogFooter class="flex flex-col sm:flex-row gap-2 sm:justify-between">
        <Button
          variant="outline"
          onclick={copyAllData}
          class={`gap-2 transition-all duration-300 ${
            copiedAll ? 'bg-green-600 hover:bg-green-700 text-white border-green-600' : ''
          }`}
        >
          {#if copiedAll}
            <Check class="h-4 w-4" />
            Copied!
          {:else}
            <Copy class="h-4 w-4" />
            Copy All
          {/if}
        </Button>
        <Button onclick={handleClose}>Done</Button>
      </DialogFooter>
    {/if}
  </DialogContent>
</Dialog>

<style>
  /* Smooth transitions for copy buttons */
  button {
    transition: all 0.2s ease-in-out;
  }
</style>
