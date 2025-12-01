# SSN Management System - Frontend

Modern frontend application for the SSN Management System, built with SvelteKit, TypeScript, Tailwind CSS, and shadcn-svelte.

## Technology Stack

- **Svelte 5.42+**: Modern reactive framework with runes ($state, $derived, $effect)
- **SvelteKit 2.0+**: Full-stack framework with SSR capabilities
- **TypeScript**: Type-safe development
- **Tailwind CSS**: Utility-first CSS framework
- **shadcn-svelte**: Pre-built accessible UI components (Svelte 5 compatible)
- **bits-ui 1.8+**: Headless UI primitives (Svelte 5 rewrite)
- **@lucide/svelte**: Modern icon library (Svelte 5 compatible)
- **Formsnap 2.0+**: Form handling with snippets API
- **sveltekit-superforms 2.28+**: Advanced form validation (CVE-2025-62381 fix)
- **zod**: Schema validation
- **axios**: HTTP client for API communication

## Prerequisites

- Node.js 18+ and pnpm
- Backend APIs running on ports 8000 (Public API) and 8001 (Enrichment API)
- See main project README for backend setup

## Installation

1. Install dependencies:

```bash
cd frontend
pnpm install
```

2. Copy environment configuration:

```bash
cp .env.example .env
```

3. Install shadcn-svelte UI Components:

Run the following command to install all required shadcn-svelte components:

```bash
pnpm dlx shadcn-svelte@latest add button input label select form card table badge sidebar dropdown-menu avatar pagination collapsible dialog alert separator tooltip skeleton
```

This will install the following components to `src/lib/components/ui/`:
- **button** - Interactive buttons with variants
- **input** - Text input fields
- **label** - Form labels
- **select** - Dropdown selects
- **form** - Form wrapper with Formsnap integration
- **card** - Container components (Card, CardHeader, CardContent, CardFooter)
- **table** - Data tables (Table, TableHeader, TableBody, TableRow, TableCell)
- **badge** - Small labels/tags
- **sidebar** - Collapsible sidebar navigation
- **dropdown-menu** - Dropdown menus
- **avatar** - User avatars with fallback
- **pagination** - Page navigation
- **collapsible** - Expandable content sections
- **dialog** - Modal dialogs
- **alert** - Alert/notification messages
- **separator** - Visual dividers
- **tooltip** - Hover tooltips
- **skeleton** - Loading placeholders

**Note:** These components are required for the authentication pages, sidebar layout, and all subsequent features (dashboard, search, cart, orders).

**Important: Additional Components for Search Pages**

For the search pages (/lookup-ssn, /reverse-ssn, /buy-fullz) to work correctly, ensure all components listed above are installed. If you encounter missing component errors, verify that the following critical components are present:

- **table** - for displaying search results
- **select** - for state dropdown selection
- **badge** - for displaying source_table (ssn_1/ssn_2)
- **skeleton** - for loading states in the table
- **pagination** - for navigating through search results

**Verification:**
After installation, verify that `src/lib/components/ui/` contains all component directories:

```bash
ls src/lib/components/ui/
# Should show: table/ select/ badge/ skeleton/ pagination/ button/ input/ label/ etc.
```

4. Verify installation:

```bash
pnpm run check
```

## Svelte 5 Migration

This project has been migrated to **Svelte 5**. Key changes:

### Dependency Updates
- Svelte: 4.2.0 → 5.42.3
- bits-ui: 0.11.0 → 1.8.0 (breaking changes, complete rewrite)
- formsnap: 1.0.1 → 2.0.1 (snippets API)
- lucide-svelte → @lucide/svelte 0.544.0 (package rename)
- sveltekit-superforms: 2.12.0 → 2.28.0 (security fix CVE-2025-62381)

### Code Pattern Changes

**Props:**
```svelte
<!-- Svelte 4 -->
export let value;

<!-- Svelte 5 -->
let { value } = $props();
```

**Events:**
```svelte
<!-- Svelte 4 -->
<button on:click={handler}>Click</button>

<!-- Svelte 5 -->
<button onclick={handler}>Click</button>
```

**Reactivity:**
```svelte
<!-- Svelte 4 -->
$: doubled = value * 2;
$: { console.log(value) }

<!-- Svelte 5 -->
let doubled = $derived(value * 2);
$effect(() => { console.log(value) });
```

**Icons:**
```typescript
// Svelte 4
import { Search, User } from 'lucide-svelte';

// Svelte 5
import Search from '@lucide/svelte/icons/search';
import User from '@lucide/svelte/icons/user';
```

**Forms (Formsnap v2):**
```svelte
<!-- Svelte 4 (Formsnap v1) -->
<FormField {config} name="email">
  <FormControl let:attrs>
    <Input {...attrs} bind:value={$form.email} />
  </FormControl>
</FormField>

<!-- Svelte 5 (Formsnap v2) -->
<FormField {config} name="email">
  {#snippet children({ props })}
    <FormControl>
      <Input {...props} bind:value={$form.email} />
    </FormControl>
  {/snippet}
</FormField>
```

### Stores Compatibility

Svelte stores continue to work without changes:
```typescript
import { writable, derived } from 'svelte/store';
// No migration needed for auth.ts and cart.ts
```

### shadcn-svelte Components

All components have been reinstalled for Svelte 5 compatibility (bits-ui 1.8.0). If you need to add more components:

```bash
npx shadcn-svelte@latest add <component-name>
```

### Migration Documentation

For complete migration details, see [MIGRATION_SVELTE5.md](./MIGRATION_SVELTE5.md).

### Resources

- [Svelte 5 Documentation](https://svelte.dev/docs/svelte/overview)
- [Svelte 5 Migration Guide](https://svelte.dev/docs/svelte/v5-migration-guide)
- [bits-ui 1.8 Documentation](https://bits-ui.com)
- [Formsnap v2 Documentation](https://formsnap.dev)

## Development

Start the development server:

```bash
pnpm run dev
```

The application will be available at http://localhost:5173

Other useful commands:

- `pnpm run check` - Run TypeScript type checking
- `pnpm run lint` - Run ESLint
- `pnpm run format` - Format code with Prettier

## Building for Production

Build the application:

```bash
pnpm run build
```

Preview the production build:

```bash
pnpm run preview
```

The build output will be in the `build/` directory, ready to be deployed as a Node.js server.

## Project Structure

```
src/
├── routes/              # SvelteKit routes (pages)
│   ├── (auth)/          # Authentication route group
│   │   ├── login/       # Login page
│   │   ├── register/    # Registration page
│   │   └── +layout.svelte # Auth layout (centered)
│   ├── (app)/           # Protected routes group
│   │   ├── dashboard/   # Dashboard with metrics and proxy data table
│   │   ├── lookup-ssn/  # Search by name, email, phone, state/ZIP
│   │   ├── reverse-ssn/ # Search by SSN
│   │   ├── buy-fullz/   # Search with cart functionality
│   │   ├── cart/        # Shopping cart with item management and checkout
│   │   ├── orders/      # Order history with expandable details
│   │   ├── +layout.svelte # App layout (with sidebar)
│   │   └── +layout.ts   # Auth protection middleware
│   ├── +layout.svelte   # Root layout
│   └── +page.svelte     # Home page
├── lib/
│   ├── components/
│   │   ├── ui/          # shadcn-svelte components
│   │   ├── layout/      # Layout components (Sidebar, Header)
│   │   ├── dashboard/   # Dashboard-specific components
│   │   │   ├── MetricCard.svelte  # Reusable metric card with icon and value
│   │   │   └── DataTable.svelte   # Complex data table with filters and pagination
│   │   ├── search/      # Search-related components
│   │   │   └── SearchResultsTable.svelte  # Reusable table for search results
│   │   └── cart/        # Cart/checkout components (optional)
│   ├── stores/          # Svelte stores (auth, cart)
│   │   ├── auth.ts      # Authentication state management with refreshUser()
│   │   └── cart.ts      # Shopping cart state management with auto-load
│   ├── constants/       # Application constants
│   │   ├── states.ts    # US states list for dropdown
│   │   ├── pricing.ts   # Pricing logic for records
│   │   ├── countries.ts # Country codes and names for dashboard filters
│   │   └── orderStatuses.ts # Order status constants and labels
│   ├── api/             # API client and TypeScript types
│   └── utils.ts         # Utility functions (including status badge helpers)
├── app.html             # HTML template
└── app.css              # Global styles and Tailwind directives
```

## API Integration

The API client is located in `src/lib/api/client.ts` and provides:

- **Authentication**: Login, register, get current user
- **Search**: Search by SSN, email, or name
- **Cart**: Manage shopping cart items
- **Orders**: Create and view orders
- **Type Safety**: TypeScript interfaces matching backend Pydantic models
- **Auto-authentication**: JWT token automatically added to requests
- **Error Handling**: Automatic token refresh and error redirects

Usage example:

```typescript
import { login, getCurrentUser } from '$lib/api/client';

const { access_token } = await login('username', 'password');
localStorage.setItem('access_token', access_token);

const user = await getCurrentUser();
```

## Authentication Setup

The application uses JWT token-based authentication with localStorage persistence:

### Auth Store

Import and use the auth store in your components:

```typescript
import { login, logout, register, user, isAuthenticated } from '$lib/stores/auth';

// Login
const result = await login(username, password);
if (result.success) {
  // Automatically redirects to /dashboard
}

// Register
const result = await register(username, email, password);
if (result.success) {
  // Automatically logs in and redirects to /dashboard
}

// Logout
logout(); // Clears token and redirects to /login

// Use reactive data in templates
$user?.username
$user?.balance
$isAuthenticated
```

### Route Groups

The application uses SvelteKit route groups for organization:

- **(auth)**: Public authentication pages (login, register)
  - Simple centered layout without sidebar
  - Redirects authenticated users to /dashboard

- **(app)**: Protected application pages (dashboard, search, cart, etc.)
  - Full layout with sidebar navigation
  - Requires authentication (checked in +layout.ts)
  - Redirects unauthenticated users to /login

### Protected Routes

All routes under `(app)` are automatically protected by the auth middleware in `(app)/+layout.ts`:

```typescript
// Automatically runs before rendering any (app) route
export const load: LayoutLoad = async () => {
  // Waits for auth initialization
  // Redirects to /login if not authenticated
  // Allows route to render if authenticated
};
```

### Creating Test Users

Before using the frontend, create a test user via the backend:

```bash
# Start backend services
docker-compose up -d

# Access Python REPL in container
docker-compose exec public_api python

# Create user
>>> from app.database import get_db
>>> from app.auth import get_password_hash
>>> from app.models import User
>>> db = next(get_db())
>>> user = User(username="testuser", email="test@example.com", hashed_password=get_password_hash("password123"), balance=100.0)
>>> db.add(user)
>>> db.commit()
>>> exit()
```

Or use the registration form at http://localhost:5173/register

## Styling

The application uses a light theme configured in `src/app.css`:

- **CSS Variables**: All colors defined as CSS variables for consistent theming
- **Tailwind Utilities**: Use Tailwind classes for rapid development
- **shadcn-svelte Components**: Pre-styled accessible components
- **Responsive Design**: Mobile-first approach with Tailwind breakpoints

Key utility classes:

- `.container` - Centered content with max-width and padding
- Use `cn()` helper from `$lib/utils` to merge Tailwind classes

## Environment Variables

Environment variables must be prefixed with `PUBLIC_` to be accessible in the browser:

- `PUBLIC_API_URL` - Backend Public API URL (default: /api/public)
- `PUBLIC_ENRICHMENT_API_URL` - Backend Enrichment API URL (default: /api/enrichment)

In production, use relative URLs - nginx will handle routing to the appropriate backend services.

## Development Tips

1. **Import Aliases**: Use path aliases for cleaner imports:
   ```typescript
   import { apiClient } from '$lib/api/client';
   import { cn } from '$lib/utils';
   ```

2. **Type Checking**: Run `pnpm run check` before committing to catch TypeScript errors

3. **Code Formatting**: Run `pnpm run format` to auto-format code according to project standards

4. **Vite Proxy**: In development, Vite automatically proxies API requests to avoid CORS issues

5. **Hot Module Replacement**: Changes to `.svelte` files trigger instant updates without full page reload

## Docker Deployment

The frontend is containerized and deployed as part of the full-stack Docker Compose setup.

### Building the Docker Image

```bash
# From project root
cd /root/soft
docker-compose build frontend
```

### Running with Docker Compose

```bash
# Start all services (from project root)
docker-compose up -d

# Frontend will be available at http://localhost/ (via nginx)
```

### Environment Variables

The frontend requires these environment variables (set in docker-compose.yml):

- `PUBLIC_API_URL`: Backend API URL (default: `/api/public`)
- `ORIGIN`: Application origin for CORS (default: `http://localhost`)
- `NODE_ENV`: Set to `production` in Docker
- `PORT`: Server port (default: `3000`)

### Dockerfile

The frontend uses a multi-stage Dockerfile:

**Stage 1 (builder):** Installs dependencies and builds the application
**Stage 2 (runtime):** Copies build artifacts and runs the Node.js server

**Benefits:**
- Small image size (~150MB vs ~500MB with dev dependencies)
- Fast startup time
- Production-optimized build
- Non-root user for security

### Accessing the Frontend

- **Via nginx (recommended):** http://localhost/
- **Direct access (development):** http://localhost:3000/ (if port is exposed)

### Logs

```bash
# View frontend logs
docker-compose logs frontend

# Follow logs in real-time
docker-compose logs -f frontend
```

### Rebuilding After Code Changes

```bash
# Rebuild and restart frontend
docker-compose up -d --build frontend

# Or rebuild all services
docker-compose up -d --build
```

### Production Configuration

In production, nginx reverse proxy routes requests:

- `/` → Frontend (port 3000)
- `/api/public` → Public API (port 8000)
- `/api/enrichment` → Enrichment API (port 8001)

## Troubleshooting

**CORS Errors**

Ensure backend CORS is configured for `http://localhost:5173`:

```python
CORS_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]
```

**API Connection Failed**

Check that backend services are running:

```bash
# From project root
docker-compose ps
```

**Type Errors**

Run type checking to see detailed errors:

```bash
pnpm run check
```

**Styling Issues**

Ensure Tailwind is processing correctly:

1. Check `postcss.config.js` exists
2. Verify `@tailwind` directives in `src/app.css`
3. Clear `.svelte-kit` cache: `rm -rf .svelte-kit`

**Build Errors**

1. Clear build cache: `rm -rf .svelte-kit build`
2. Reinstall dependencies: `rm -rf node_modules && pnpm install`
3. Run `pnpm run check` to identify TypeScript issues

## Implementation Status

### Phase 1: Authentication & Layout (Completed)

✅ JWT token-based authentication with localStorage
✅ Login and registration pages with form validation
✅ Protected routes with middleware
✅ Responsive sidebar layout with navigation
✅ User dropdown menu with logout
✅ Balance display in header
✅ Cart badge (placeholder, count=0)
✅ Light theme styling

### Phase 2: Search Pages (Completed)

✅ Lookup SSN page - search by name, email, phone, state/ZIP
✅ Reverse SSN page - search by SSN with auto-formatting
✅ Buy Fullz page - search with add to cart functionality
✅ Reusable SearchResultsTable component with sorting and pagination
✅ Client-side sorting by all columns
✅ Client-side pagination (10 items per page)
✅ Loading states with skeleton components
✅ Add to cart integration with visual feedback
✅ US states dropdown selection
✅ Form validation with sveltekit-superforms + zod
✅ Phone and SSN input formatting utilities

**Search Pages Overview:**
- **/lookup-ssn** - Search by name (firstname, lastname, email, phone, state/ZIP). Displays results in a sortable table.
- **/reverse-ssn** - Search by SSN with auto-formatting (XXX-XX-XXXX). Single field form.
- **/buy-fullz** - Same search as lookup-ssn but with "Add to Cart" buttons for purchasing records.

**Shared Components:**
- **SearchResultsTable.svelte** - Reusable table component with sorting, pagination, and optional cart integration

**Constants:**
- **states.ts** - All 50 US states for dropdown selection
- **pricing.ts** - Pricing logic (ssn_1: $12.99, ssn_2: $9.99, default: $9.99)

### Phase 3: Dashboard (Completed)

✅ 4 Metric cards (Current Online, Unique IPs, Balance, Loyalty)
✅ Proxy data table with 9 columns
✅ Filters: Country, State, City, ZIP, Type, Speed
✅ Search across proxy IP, city, ISP fields
✅ Sortable columns (click headers to sort)
✅ Pagination (10 items per page)
✅ Export to CSV functionality
✅ Refresh button to reload data
✅ Loading states with skeleton components
✅ Svelte 5 runes ($state, $derived, $effect)
✅ Deep Lucide icon imports for better tree-shaking

**Dashboard Features:**

**Metrics:**
- **Current Online**: Real-time count from PostgreSQL sessions table
- **Unique IPs**: Mock data (22,521 unique IPs, last 30 days)
- **Balance**: User's current balance from auth store
- **Loyalty**: Mock loyalty tier (20% OFF, Gold tier)

**Data Table:**
- 15 proxy data items (mock data from backend)
- Filters: Country, State, City, ZIP, Type (Residential/Mobile/Hosting), Speed (Fast/Moderate)
- Search: Filter across proxy IP, city, ISP
- Sorting: Click column headers to sort (all columns sortable)
- Pagination: 10 items per page with navigation
- Export: Download filtered data as CSV
- Refresh: Reload data from API
- Color-coded badges: Speed (green=Fast, yellow=Moderate), Type (blue=Residential, purple=Mobile, gray=Hosting)

**Svelte 5 Features Used:**
- $state rune for reactive state
- $derived rune for computed values (filtering, sorting, pagination)
- $props rune for component props
- Deep Lucide icon imports (e.g., `import Users from 'lucide-svelte/icons/users'`)

### Phase 4: E-commerce (Completed)

✅ Shopping cart page with item management
✅ Order history page with expandable details
✅ Cart store with auto-load functionality
✅ Auth store with refreshUser() for balance updates
✅ Order status constants and helpers
✅ Status badge styling utilities

**E-commerce Pages Overview:**

**/cart - Shopping Cart:**
- View all items in cart with full SSN details (name, email, phone, address)
- Remove individual items with loading feedback (trash icon button)
- Clear entire cart with one click
- See total price, current balance, and remaining balance after purchase
- Checkout creates order and deducts balance atomically
- Automatic redirect to orders page after successful checkout
- Empty state with link to /buy-fullz shopping page
- Real-time cart count badge in sidebar
- Balance indicator (red if insufficient, green if sufficient)
- Success/error messages with auto-dismiss
- Loading states on individual delete buttons

**/orders - Order History:**
- View all orders with pagination (10 per page)
- Filter by status dropdown: All, Pending, Completed, Failed, Cancelled
- Expandable rows show full order details with SSN records
- Status badges with color coding and icons:
  - Pending (yellow, Clock icon)
  - Completed (green, CheckCircle icon)
  - Failed (red, XCircle icon)
  - Cancelled (gray, Ban icon)
- Export orders to CSV functionality
- Refresh button to reload latest orders
- Order details cached to prevent redundant API calls
- Nested table inside expandable rows shows SSN records with all fields
- Loading states for both orders list and individual order details
- Empty state with link to shopping pages

**Cart Store Features:**
- `loadCart()` - Load cart from API
- `addItem(ssn, table_name, price)` - Add item to cart
- `removeItem(item_id)` - Remove item from cart
- `clearAll()` - Clear entire cart
- Derived stores: `cartItems`, `cartTotal`, `cartCount`
- Auto-loads on store initialization (browser only)
- Updates cart count badge in sidebar automatically

**Auth Store Features:**
- `refreshUser()` - Refresh user data (especially balance after checkout)
- Graceful error handling (logs but doesn't logout)
- Used after order creation to sync balance with backend

**Svelte 5 Features Used:**
- $state for reactive component state (isLoading, orders, selectedStatus, etc.)
- $derived for computed values (filteredOrders, paginatedOrders, totalPages)
- $props for component props
- $effect for side effects (data loading, auto-dismiss messages)
- Deep Lucide icon imports for better tree-shaking
- onclick event handlers instead of on:click
- Collapsible component for expandable order details
- Status badge styling with Tailwind classes

**API Integration:**
- Cart: GET /cart, POST /cart/add, DELETE /cart/{item_id}, DELETE /cart/clear
- Orders: POST /orders/create, GET /orders (with filters), GET /orders/{order_id}
- Atomic order creation: balance deduction + order creation + cart clearing in single transaction
- Full type safety with TypeScript interfaces

### Next Steps

Subsequent phases will implement:

1. **API Documentation Page**: Interactive API docs for developers
2. **Support Page**: Help center and contact form
3. **Admin Panel**: User management and system monitoring

## Resources

- [SvelteKit Documentation](https://kit.svelte.dev/docs)
- [shadcn-svelte Documentation](https://shadcn-svelte.com/)
- [Tailwind CSS Documentation](https://tailwindcss.com/docs)
- [Backend API Documentation](../README_API.md)
