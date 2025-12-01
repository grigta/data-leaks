# SSN Admin Panel

Admin panel for managing the SSN platform - users, coupons, and analytics.

## Overview

Built with:
- **SvelteKit** - Full-stack web framework
- **TypeScript** - Type-safe development
- **Tailwind CSS** - Utility-first styling
- **shadcn-svelte** - High-quality UI components
- **Chart.js** - Interactive data visualization
- **Svelte 5** - Latest reactivity with runes syntax

## Features

### 🔐 Authentication
- **Two-Factor Authentication (2FA)** - Mandatory TOTP-based 2FA using Google Authenticator
- **JWT Tokens** - Secure session management
- **Protected Routes** - Automatic redirect to login for unauthenticated access

### 📊 Dashboard
- **User Statistics** - Total users, new users (24h, 30 days, all time)
- **Financial Metrics** - Total deposited, total spent, usage percentage
- **Transaction Analytics** - Status breakdown (pending, paid, expired, failed)
- **Product Breakdown** - Instant SSN, cart purchases, enrichment operations
- **Interactive Charts** - User growth trends and transaction distribution

### 🎟️ Coupon Management
- **Create Coupons** - Auto-generate codes or specify custom codes
- **Edit Coupons** - Update bonus percentage, max uses, and active status
- **Toggle Status** - Activate/deactivate coupons
- **Delete Coupons** - Remove unused or deprecated coupons
- **Usage Tracking** - Visual progress bars showing coupon usage

### 👥 User Management
- **User Table** - Comprehensive view of all platform users
- **Search** - Find users by username or email
- **Sorting** - Sort by username, email, balance, deposits, spending, or creation date
- **Pagination** - Navigate large user lists efficiently
- **Financial Overview** - Balance, total deposited, total spent per user
- **Applied Coupons** - View which coupons each user has applied

## Development

### Prerequisites
- Node.js 20+
- pnpm

### Installation

\`\`\`bash
cd admin-frontend
pnpm install
\`\`\`

### Development Server

Run the development server with hot-reload:

\`\`\`bash
pnpm dev
\`\`\`

The admin panel will be available at http://localhost:5174/admin

### Build for Production

\`\`\`bash
pnpm build
\`\`\`

### Preview Production Build

\`\`\`bash
pnpm preview
\`\`\`

### Type Checking

\`\`\`bash
pnpm run check
\`\`\`

### Code Formatting

\`\`\`bash
pnpm run format
\`\`\`

## Authentication Setup

### First-Time Admin Login

1. **Login with credentials** - Enter your admin username and password
2. **Configure 2FA** - Scan the QR code with Google Authenticator app
3. **Save backup codes** - Store them securely for account recovery
4. **Verify TOTP** - Enter the 6-digit code from your authenticator app

### Subsequent Logins

1. **Enter credentials** - Username and password
2. **Enter TOTP code** - 6-digit code from Google Authenticator
3. **Access granted** - Redirected to admin dashboard

## Project Structure

\`\`\`
admin-frontend/
├── src/
│   ├── routes/
│   │   ├── (admin)/              # Protected admin routes
│   │   │   ├── +layout.svelte    # Admin layout with sidebar
│   │   │   ├── +layout.ts        # Route protection logic
│   │   │   ├── dashboard/        # Analytics dashboard
│   │   │   ├── coupons/          # Coupon management
│   │   │   └── users/            # User management
│   │   ├── login/                # Login page with 2FA
│   │   ├── +layout.svelte        # Root layout
│   │   └── +layout.ts            # Root layout logic
│   ├── lib/
│   │   ├── api/
│   │   │   └── client.ts         # API client with auth interceptors
│   │   ├── stores/
│   │   │   ├── auth.ts           # Authentication store (2FA support)
│   │   │   └── theme.ts          # Theme management store
│   │   ├── components/
│   │   │   └── ui/               # Shared UI components (symlinked)
│   │   ├── constants/
│   │   │   └── animations.ts     # Animation timing constants
│   │   └── utils.ts              # Utility functions
│   ├── app.css                   # Global styles
│   └── app.html                  # HTML template
├── package.json                  # Dependencies and scripts
├── svelte.config.js              # SvelteKit configuration
├── vite.config.ts                # Vite configuration
├── tailwind.config.js            # Tailwind CSS configuration
├── tsconfig.json                 # TypeScript configuration
├── Dockerfile                    # Docker build instructions
└── README.md                     # This file
\`\`\`

## Deployment

### Docker

Build and run with Docker Compose:

\`\`\`bash
# From project root
docker-compose up admin_frontend
\`\`\`

The admin panel will be accessible via nginx at http://localhost/admin

### Environment Variables

Create a \`.env\` file based on \`.env.example\`:

\`\`\`bash
PUBLIC_ADMIN_API_URL=/api/admin
ORIGIN=http://localhost
NODE_ENV=production
PORT=3001
\`\`\`

### Nginx Routing

The admin panel is accessible at the \`/admin\` path:

- **Development**: http://localhost:5174/admin (direct access)
- **Production**: http://localhost/admin (via nginx)

API requests are proxied to \`/api/admin\` which routes to the admin API backend.

## Security

### 2FA Requirement
- All admin users must configure 2FA on first login
- TOTP codes generated by Google Authenticator
- Backup codes provided for account recovery

### JWT Authentication
- Admin access token stored in localStorage
- Temporary token used during 2FA verification
- Automatic logout on 401 responses

### Route Protection
- All admin routes protected by authentication check
- Automatic redirect to login for unauthenticated users
- Token validation on every API request

### IP Whitelisting (Recommended for Production)
Uncomment the IP restrictions in \`nginx.conf\`:

\`\`\`nginx
location /admin {
    allow 10.0.0.0/8;
    allow 172.16.0.0/12;
    allow 192.168.0.0/16;
    deny all;

    # ... rest of config
}
\`\`\`

## API Integration

The admin frontend communicates with the admin API at \`/api/admin\`:

### Authentication Endpoints
- \`POST /auth/login\` - Username/password authentication
- \`POST /auth/verify-2fa\` - TOTP verification
- \`POST /auth/setup-2fa\` - Configure 2FA for new admin
- \`POST /auth/confirm-2fa\` - Confirm 2FA setup
- \`POST /auth/disable-2fa\` - Disable 2FA (requires password)

### Analytics Endpoints
- \`GET /analytics/stats/users\` - User statistics
- \`GET /analytics/stats/financial\` - Financial statistics
- \`GET /analytics/stats/transactions\` - Transaction statistics
- \`GET /analytics/stats/products\` - Product statistics
- \`GET /analytics/stats/coupons\` - Coupon usage statistics
- \`GET /analytics/users/table\` - User table with pagination

### Coupon Endpoints
- \`GET /coupons\` - List all coupons
- \`POST /coupons\` - Create new coupon
- \`GET /coupons/{id}\` - Get coupon details
- \`PATCH /coupons/{id}\` - Update coupon
- \`DELETE /coupons/{id}\` - Delete coupon
- \`POST /coupons/{id}/deactivate\` - Deactivate coupon

## UI Components

The admin panel shares UI components with the main frontend via symlink:

\`\`\`bash
admin-frontend/src/lib/components/ui -> frontend/src/lib/components/ui
\`\`\`

Available components:
- Button, Card, Input, Label, Badge
- Table, Dialog, Alert, Checkbox
- Dropdown Menu, Avatar, Skeleton
- And more from shadcn-svelte

## Chart.js Integration

Charts are initialized in \`onMount\` to avoid SSR issues:

\`\`\`typescript
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);

onMount(() => {
  // Create charts after component mounts
  const chart = new Chart(canvasRef, config);

  return () => {
    chart.destroy(); // Cleanup on unmount
  };
});
\`\`\`

## Troubleshooting

### Symlink Issues in Docker
If the UI components symlink doesn't work in Docker, the Dockerfile copies the components during the build process.

### 2FA Setup Issues
- Ensure the admin user has \`is_admin=true\` in the database
- Check that the admin API is running and accessible
- Verify JWT_SECRET is configured correctly

### Chart.js SSR Errors
Chart.js is configured to skip SSR in \`svelte.config.js\`:
\`\`\`javascript
vite: {
  ssr: {
    noExternal: ['chart.js', 'chartjs-adapter-date-fns']
  }
}
\`\`\`

### API Connection Issues
- Check that \`PUBLIC_ADMIN_API_URL\` is set correctly
- Verify nginx is routing \`/api/admin\` to the admin API backend
- Check admin API logs for errors

## License

Same as parent project.
