import { Coins, Hexagon, Bitcoin } from '@lucide/svelte/icons';
import type { ComponentType } from 'svelte';

export interface CryptoOption {
  id: string;           // Unique identifier (e.g., 'usdt-trc20')
  name: string;         // Display name (e.g., 'USDT (TRC20)')
  currency: string;     // Currency code for API (e.g., 'USDT')
  network: string;      // Network code for API (e.g., 'TRC20')
  icon: ComponentType;  // Lucide icon component
  description: string;  // Short description
  color: string;        // Tailwind color class for styling
}

export const CRYPTO_OPTIONS: CryptoOption[] = [];

export const getCryptoOption = (id: string): CryptoOption | undefined => {
  return CRYPTO_OPTIONS.find(option => option.id === id);
};
