/**
 * Instant SSN Search Rules Constants
 *
 * Содержит текст правил для Instant SSN Search.
 * При необходимости может быть интегрировано с системой локализации.
 */

export const INSTANT_SSN_RULES = {
  title: 'Instant SSN Search Rules',
  description: 'Please read and accept the following rules before using Instant SSN Search:',
  rules: [
    {
      text: 'Do not search full DOB range (1990-2025) more than 3 times in a row',
      severity: 'normal' as const
    },
    {
      text: 'Do not search the same fullname (firstname + lastname + address) that is not found more than 3 times in a row',
      severity: 'normal' as const
    },
    {
      text: 'Violation of these rules will result in account ban',
      severity: 'critical' as const
    }
  ],
  buttons: {
    cancel: 'Cancel',
    accept: 'Hold to Accept (3s)',
    holding: (seconds: number) => `Hold (${seconds}s)`
  }
} as const;
