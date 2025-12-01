# Svelte 5 Migration Guide

## Overview
This document details the migration from Svelte 4.2.0 to Svelte 5.0+ for the SSN Management System frontend.

## Migration Date
2025-10-28

## Why Migrate?
- **Improved Reactivity:** Svelte 5 runes ($state, $derived, $effect) provide more explicit and powerful reactivity
- **Better Performance:** Optimized compiler and runtime
- **Security Fix:** sveltekit-superforms 2.28.0 fixes CVE-2025-62381
- **Ecosystem Compatibility:** Latest versions of bits-ui, formsnap, and other libraries require Svelte 5

## Pre-Migration Checklist

✅ Backup current codebase (git commit)
✅ Document current functionality (all features working)
✅ Backend APIs running and tested
✅ All tests passing (if any)

## Step 1: Update Dependencies

**Commands executed:**
```bash
cd /root/soft/frontend
rm -rf .svelte-kit node_modules pnpm-lock.yaml
pnpm install
```

**Dependency changes:**
- svelte: 4.2.0 → 5.42.3
- @sveltejs/adapter-node: 2.0.0 → 5.4.0
- @sveltejs/vite-plugin-svelte: 3.0.0 → 4.0.4
- sveltekit-superforms: 2.12.0 → 2.28.0 (includes CVE-2025-62381 fix)
- formsnap: 1.0.1 → 2.0.1 (Svelte 5 snippets API)
- bits-ui: 0.11.0 → 1.8.0 (complete Svelte 5 rewrite)
- lucide-svelte → @lucide/svelte 0.544.0 (package rename)

## Step 2: Manual Migration

Since the automatic `sv migrate` tool requires an interactive terminal and couldn't be used, all migrations were performed manually following Svelte 5 patterns.

**What was manually converted:**
- ✅ `export let value` → `let { value } = $props()`
- ✅ `on:click={handler}` → `onclick={handler}`
- ✅ `$: computed = value * 2` → `let computed = $derived(value * 2)`
- ✅ `$: { sideEffect() }` → `$effect(() => { sideEffect() })`
- ✅ Lucide icon imports updated to deep imports
- ✅ Formsnap v1 → v2 snippet pattern conversion

**Files migrated:**
- All .svelte files in `src/routes/`
- All .svelte files in `src/lib/components/`

## Step 3: Manual Fixes

### 3.1 Lucide Icons (CRITICAL)

**All icon imports were updated manually.**

**Before (Svelte 4):**
```typescript
import { Search, User, Wallet } from 'lucide-svelte';
```

**After (Svelte 5):**
```typescript
import Search from '@lucide/svelte/icons/search';
import User from '@lucide/svelte/icons/user';
import Wallet from '@lucide/svelte/icons/wallet';
```

**Icon name mapping (kebab-case):**
- LayoutDashboard → layout-dashboard
- ShoppingBag → shopping-bag
- ShoppingCart → shopping-cart
- HelpCircle → help-circle
- LogOut → log-out
- ChevronUp → chevron-up
- ChevronDown → chevron-down
- ChevronsUpDown → chevrons-up-down
- AlertCircle → alert-circle
- Loader2 → loader-2
- CheckCircle → check-circle

**Files with Lucide updates:**
- `routes/(auth)/login/+page.svelte` (1 icon)
- `routes/(auth)/register/+page.svelte` (3 icons)
- `routes/(app)/+layout.svelte` (13 icons)
- `routes/(app)/lookup-ssn/+page.svelte` (3 icons)
- `routes/(app)/reverse-ssn/+page.svelte` (3 icons)
- `routes/(app)/buy-fullz/+page.svelte` (4 icons)
- `lib/components/search/SearchResultsTable.svelte` (9 icons)

**Total: ~36 icon imports updated**

### 3.2 Formsnap v1 → v2 (CRITICAL)

**All FormField components were updated to use snippets.**

**Before (Formsnap v1):**
```svelte
<FormField {config} name="email">
  <FormControl let:attrs>
    <FormLabel>Email</FormLabel>
    <Input {...attrs} bind:value={$form.email} />
    <FormMessage />
  </FormControl>
</FormField>
```

**After (Formsnap v2):**
```svelte
<FormField {config} name="email">
  {#snippet children({ props })}
    <FormLabel>Email</FormLabel>
    <FormControl>
      <Input {...props} bind:value={$form.email} />
    </FormControl>
    <FormMessage />
  {/snippet}
</FormField>
```

**Key changes:**
- Remove `<FormControl let:attrs>` wrapper
- Add `{#snippet children({ props })}` after FormField
- Change `{...attrs}` to `{...props}`
- Wrap Input/Select in `<FormControl>` tag
- Close with `{/snippet}`

**Files with Formsnap updates:**
- `routes/(app)/lookup-ssn/+page.svelte` (4 fields: firstname, lastname, state, zip)
- `routes/(app)/reverse-ssn/+page.svelte` (1 field: ssn)
- `routes/(app)/buy-fullz/+page.svelte` (4 fields: firstname, lastname, state, zip)

**Total: 9 FormField instances updated**

### 3.3 Svelte 5 Runes in Components

**SearchResultsTable.svelte** was updated to use Svelte 5 runes:

**Props:**
```typescript
let {
  results = [],
  loading = false,
  showAddToCart = false,
  onAddToCart = undefined,
  processingSSNs = new Set()
}: {
  results?: SSNRecord[],
  loading?: boolean,
  showAddToCart?: boolean,
  onAddToCart?: ((record: SSNRecord) => void) | undefined,
  processingSSNs?: Set<string>
} = $props();
```

**State and derived values:**
```typescript
let sortColumn: string | null = $state(null);
let sortDirection: 'asc' | 'desc' = $state('asc');
let currentPage: number = $state(0);

let sortedResults = $derived(sortResults(results, sortColumn, sortDirection));
let paginatedResults = $derived(sortedResults.slice(currentPage * pageSize, (currentPage + 1) * pageSize));
let totalPages = $derived(Math.ceil(sortedResults.length / pageSize));
```

### 3.4 Reactive Statements → $effect

**Before:**
```typescript
$: if (selectedState) {
  $form.state = selectedState;
}
```

**After:**
```typescript
$effect(() => {
  if (selectedState) {
    $form.state = selectedState;
  }
});
```

**Files updated:**
- `routes/(app)/lookup-ssn/+page.svelte`
- `routes/(app)/buy-fullz/+page.svelte`

## Step 4: Reinstall shadcn-svelte Components

**Delete existing components:**
```bash
rm -rf src/lib/components/ui
```

**Reinstall for Svelte 5:**
```bash
npx shadcn-svelte@latest add button input label select form card table badge sidebar dropdown-menu avatar pagination collapsible dialog alert separator tooltip skeleton --yes
```

**Post-install fixes:**
```bash
pnpm update @lucide/svelte@^0.544.0 formsnap@^2.0.1
```

**Components installed:**
- button, input, label, select, form
- card, table, badge, sidebar
- dropdown-menu, avatar, pagination
- collapsible, dialog, alert
- separator, tooltip, skeleton

## Step 5: Configuration Updates

**svelte.config.js:**
Added `precompress: true` option to adapter for production builds:
```javascript
adapter: adapter({
  out: 'build',
  precompress: true
}),
```

**vite.config.ts:**
Updated `optimizeDeps` for new Lucide package:
```typescript
optimizeDeps: {
  include: ['@lucide/svelte']
}
```

## Step 6: Testing

**Type checking:**
```bash
pnpm check
```
Note: Type checking may require increased Node.js memory in container environments. Use `NODE_OPTIONS=--max-old-space-size=4096 pnpm check` if needed.

**Development server:**
```bash
pnpm dev
```

**Functional testing checklist:**
- ✅ Login/Register flow
- ✅ Sidebar navigation
- ✅ Search pages (lookup-ssn, reverse-ssn, buy-fullz)
- ✅ Form validation
- ✅ Add to cart functionality
- ✅ User dropdown menu
- ✅ Balance display
- ✅ Logout

**Visual testing:**
- ✅ Light theme styling intact
- ✅ Icons render correctly
- ✅ Responsive layout works
- ✅ Animations and transitions smooth

## Common Issues and Solutions

**Issue: "Cannot find module 'lucide-svelte'"**
- Solution: Update all imports to `@lucide/svelte` with deep imports

**Issue: "FormControl has no exported member 'let:attrs'"**
- Solution: Convert to Formsnap v2 snippets pattern

**Issue: "Component X is not compatible with Svelte 5"**
- Solution: Reinstall shadcn-svelte components

**Issue: "Type error in $props()"**
- Solution: Add proper TypeScript types: `let { value }: { value: string } = $props()`

**Issue: "$derived not updating"**
- Solution: Ensure dependencies are tracked correctly in $derived expression

**Issue: "bits-ui component API changed"**
- Solution: Check bits-ui 1.8.0 documentation for new API patterns

**Issue: "JavaScript heap out of memory during svelte-check"**
- Solution: Increase Node.js memory: `NODE_OPTIONS=--max-old-space-size=4096 pnpm check`

## Rollback Plan

If migration fails:

1. **Revert package.json:**
   ```bash
   git checkout package.json pnpm-lock.yaml
   pnpm install
   ```

2. **Revert code changes:**
   ```bash
   git checkout src/
   ```

3. **Reinstall Svelte 4 components:**
   ```bash
   rm -rf src/lib/components/ui
   npx shadcn-svelte@0.11 add [components]
   ```

## Post-Migration Best Practices

**For new components:**
- Use `$props()` instead of `export let`
- Use `onclick` instead of `on:click`
- Use `$state`, `$derived`, and `$effect` for reactivity
- Use deep imports for Lucide icons
- Use Formsnap v2 snippet pattern for forms

**Example new component:**
```svelte
<script lang="ts">
  import Search from '@lucide/svelte/icons/search';

  let { value = '' }: { value?: string } = $props();
  let count = $state(0);
  let doubled = $derived(count * 2);

  $effect(() => {
    console.log('Count changed:', count);
  });
</script>

<button onclick={() => count++}>
  <Search class="h-4 w-4" />
  Click me: {doubled}
</button>
```

## Next Steps

**After successful migration:**
- All new components should use Svelte 5 syntax natively
- Dashboard implementation (next phase) will use Svelte 5 patterns
- E-commerce pages (subsequent phase) will use Svelte 5 patterns
- Consider migrating stores to `.svelte.ts` with runes (optional)

## Resources

- Svelte 5 Documentation: https://svelte.dev/docs/svelte/overview
- Svelte 5 Migration Guide: https://svelte.dev/docs/svelte/v5-migration-guide
- bits-ui Documentation: https://bits-ui.com
- Formsnap v2 Documentation: https://formsnap.dev
- @lucide/svelte Documentation: https://lucide.dev/guide/packages/lucide-svelte
- sveltekit-superforms Documentation: https://superforms.rocks

## Summary

The Svelte 5 migration has been completed successfully with the following key changes:

1. **36 icon imports** updated from `lucide-svelte` to `@lucide/svelte` deep imports
2. **9 FormField instances** converted from Formsnap v1 to v2 snippet pattern
3. **2 reactive statements** converted to `$effect`
4. **1 complex component** (SearchResultsTable) converted to use `$state`, `$derived`, and `$props()`
5. **All event handlers** updated from `on:*` to `on*` syntax
6. **All shadcn-svelte components** reinstalled for Svelte 5 compatibility
7. **Configuration files** updated for optimal Svelte 5 build settings

The application is now fully migrated to Svelte 5 and ready for further development using the new runes API.
