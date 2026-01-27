<script lang="ts">
  import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '$lib/components/ui/dialog';
  import { INSTANT_SSN_RULES } from '$lib/constants/instantSSNRules';
  import { onMount, onDestroy } from 'svelte';
  import { browser } from '$app/environment';

  interface Props {
    open: boolean;
    onAccept: () => void;
  }

  let { open, onAccept }: Props = $props();

  let holdProgress = $state(0);
  let isHolding = $state(false);
  let holdInterval: number | undefined;
  let holdStartTime = 0;
  const HOLD_DURATION = 3000; // 3 seconds
  const UPDATE_INTERVAL = 50; // Update every 50ms
  const MIN_HOLD_TIME = 2500; // Minimum 2.5 seconds to prevent accidental triggers

  function startHold() {
    isHolding = true;
    holdProgress = 0;
    holdStartTime = Date.now();

    holdInterval = window.setInterval(() => {
      holdProgress += (UPDATE_INTERVAL / HOLD_DURATION) * 100;

      if (holdProgress >= 100) {
        completeHold();
      }
    }, UPDATE_INTERVAL);
  }

  function stopHold() {
    isHolding = false;
    holdProgress = 0;
    holdStartTime = 0;
    if (holdInterval !== undefined) {
      clearInterval(holdInterval);
      holdInterval = undefined;
    }
  }

  function completeHold() {
    // Проверяем минимальное время удержания для защиты от случайного срабатывания
    const actualHoldTime = Date.now() - holdStartTime;
    if (actualHoldTime < MIN_HOLD_TIME) {
      console.warn('Hold completed too quickly, ignoring (possible interval lag)');
      stopHold();
      return;
    }

    stopHold();
    onAccept();
  }

  function handleMouseDown() {
    startHold();
  }

  function handleMouseUp() {
    stopHold();
  }

  function handleTouchStart(e: TouchEvent) {
    e.preventDefault();
    startHold();
  }

  function handleTouchEnd(e: TouchEvent) {
    e.preventDefault();
    stopHold();
  }

  // Обработчик потери фокуса окна/вкладки
  function handleVisibilityChange() {
    if (browser && document.hidden && isHolding) {
      console.log('Page hidden, stopping hold');
      stopHold();
    }
  }

  // Обработчик потери фокуса окна
  function handleBlur() {
    if (browser && isHolding) {
      console.log('Window lost focus, stopping hold');
      stopHold();
    }
  }

  onMount(() => {
    // Добавляем обработчики для предотвращения зависших интервалов
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleBlur);
  });

  onDestroy(() => {
    // Очищаем интервал и обработчики при размонтировании компонента
    stopHold();
    if (browser) {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleBlur);
    }
  });
</script>

<Dialog {open}>
  <DialogContent class="sm:max-w-md" closable={false}>
    <DialogHeader>
      <DialogTitle>{INSTANT_SSN_RULES.title}</DialogTitle>
      <DialogDescription>
        {INSTANT_SSN_RULES.description}
      </DialogDescription>
    </DialogHeader>

    <div class="space-y-4 py-4">
      <ul class="list-disc list-inside space-y-2 text-sm text-muted-foreground">
        {#each INSTANT_SSN_RULES.rules as rule}
          <li class={rule.severity === 'critical' ? 'font-semibold text-destructive' : ''}>
            {rule.text}
          </li>
        {/each}
      </ul>
    </div>

    <DialogFooter class="flex flex-col gap-2 sm:flex-row sm:justify-center">
      <button
        class="relative w-full sm:min-w-[280px] h-14 px-8 py-4 rounded-lg text-base font-semibold transition-colors overflow-hidden bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:pointer-events-none"
        onmousedown={handleMouseDown}
        onmouseup={handleMouseUp}
        onmouseleave={handleMouseUp}
        ontouchstart={handleTouchStart}
        ontouchend={handleTouchEnd}
        ontouchcancel={handleTouchEnd}
      >
        <span class="relative z-10">
          {isHolding ? INSTANT_SSN_RULES.buttons.holding(Math.floor((holdProgress / 100) * 3)) : INSTANT_SSN_RULES.buttons.accept}
        </span>
        <div
          class="absolute inset-0 bg-green-500 transition-none duration-0"
          style="width: {holdProgress}%; opacity: 0.3;"
        ></div>
      </button>
    </DialogFooter>
  </DialogContent>
</Dialog>

<style>
  /* Prevent text selection during hold */
  button {
    user-select: none;
    -webkit-user-select: none;
    -moz-user-select: none;
    -ms-user-select: none;
  }
</style>
