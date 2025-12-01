<script lang="ts">
  import { goto } from '$app/navigation';
  import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Badge } from '$lib/components/ui/badge';
  import { t } from '$lib/i18n';
  import { Wallet, ArrowRight, Coins } from '@lucide/svelte/icons';
  import { CRYPTO_OPTIONS } from '$lib/constants/crypto';

  let selectedProvider = $state<'ffio' | 'helket'>('ffio');
</script>

<div class="container mx-auto p-6 max-w-7xl">
  <!-- Page header -->
  <div class="mb-8">
    <div class="flex items-center gap-3 mb-2">
      <Wallet class="h-8 w-8 text-primary" />
      <h1 class="text-3xl font-bold">{$t('crypto.title')}</h1>
    </div>
    <p class="text-muted-foreground">{$t('crypto.subtitle')}</p>
  </div>

  <!-- Provider Selection -->
  <div class="mb-6">
    <h2 class="text-xl font-semibold mb-4">{$t('crypto.selectProvider')}</h2>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <Card
        class="cursor-pointer transition-all duration-200 {selectedProvider === 'ffio' ? 'border-primary ring-2 ring-primary' : 'hover:border-primary/50'}"
        onclick={() => selectedProvider = 'ffio'}
      >
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Coins class="h-5 w-5" />
            {$t('crypto.providerFFIO')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p class="text-sm text-muted-foreground">{$t('crypto.providerFFIODesc')}</p>
        </CardContent>
      </Card>

      <Card
        class="cursor-pointer transition-all duration-200 {selectedProvider === 'helket' ? 'border-primary ring-2 ring-primary' : 'hover:border-primary/50'}"
        onclick={() => selectedProvider = 'helket'}
      >
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Wallet class="h-5 w-5" />
            Helket
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p class="text-sm text-muted-foreground">Alternative crypto payment processor with webhook support</p>
        </CardContent>
      </Card>
    </div>
  </div>

  <!-- Crypto cards grid -->
  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    {#each CRYPTO_OPTIONS as option}
      <Card
        class="cursor-pointer hover:shadow-lg transition-all duration-200 border"
        onclick={() => goto(`/crypto-deposit/${option.id}?provider=${selectedProvider}`)}
      >
        <CardHeader class="pb-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <svelte:component this={option.icon} class="h-8 w-8 {option.color}" />
              <CardTitle class="text-lg">{option.name}</CardTitle>
            </div>
            <ArrowRight class="h-5 w-5 text-muted-foreground" />
          </div>
        </CardHeader>
        <CardContent>
          <p class="text-sm text-muted-foreground mb-3">{option.description}</p>
          <Badge variant="secondary" class="text-xs">
            {option.network}
          </Badge>
        </CardContent>
      </Card>
    {/each}
  </div>

  <!-- Info section -->
  <div class="mt-8 p-4 bg-muted/50 rounded-lg">
    <p class="text-sm text-muted-foreground">
      All popular cryptocurrencies are supported. Minimum deposit: $5.00.
      Maximum amount: $5,000.00
    </p>
  </div>
</div>
