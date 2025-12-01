<script lang="ts">
  import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '$lib/components/ui/dialog';
  import { Button } from '$lib/components/ui/button';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';
  import Loader2 from '@lucide/svelte/icons/loader-2';
  import { toast } from 'svelte-sonner';
  import { applyCoupon, handleApiError } from '$lib/api/client';

  interface Props {
    open: boolean;
    onClose: () => void;
    onSuccess: (newBalance: number) => void;
  }

  let { open, onClose, onSuccess }: Props = $props();

  let couponCode = $state('');
  let isSubmitting = $state(false);
  let error = $state<string | null>(null);

  async function handleSubmit() {
    if (!couponCode.trim() || isSubmitting) return;

    isSubmitting = true;
    error = null;

    try {
      const response = await applyCoupon(couponCode);
      resetForm();
      onSuccess(response.new_balance);
    } catch (err) {
      const errorMessage = handleApiError(err);
      error = errorMessage;
      toast.error(errorMessage);
    } finally {
      isSubmitting = false;
    }
  }

  function handleClose() {
    resetForm();
    onClose();
  }

  function resetForm() {
    couponCode = '';
    error = null;
    isSubmitting = false;
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !isSubmitting && couponCode.trim()) {
      handleSubmit();
    }
  }
</script>

<Dialog {open} onOpenChange={(isOpen) => { if (!isOpen) handleClose(); }}>
  <DialogContent class="sm:max-w-md">
    <DialogHeader>
      <DialogTitle>Применить купон</DialogTitle>
    </DialogHeader>

    <div class="space-y-4 py-4">
      <div class="space-y-2">
        <Label for="coupon-code">Код купона</Label>
        <Input
          id="coupon-code"
          bind:value={couponCode}
          placeholder="Введите код купона"
          maxlength="20"
          class="uppercase"
          onkeydown={handleKeydown}
          autofocus
          disabled={isSubmitting}
        />
      </div>

      {#if error}
        <p class="text-sm text-destructive">{error}</p>
      {/if}
    </div>

    <DialogFooter class="flex flex-col sm:flex-row gap-2">
      <Button variant="outline" onclick={handleClose} disabled={isSubmitting}>
        Отмена
      </Button>
      <Button onclick={handleSubmit} disabled={!couponCode.trim() || isSubmitting}>
        {#if isSubmitting}
          <Loader2 class="mr-2 h-4 w-4 animate-spin" />
          Применение...
        {:else}
          Применить
        {/if}
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
