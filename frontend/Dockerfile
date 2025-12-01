# Multi-stage Dockerfile for SvelteKit frontend
# Stage 1: Builder - Install dependencies and build the application
FROM node:20-alpine AS builder

WORKDIR /app

# Install pnpm globally
RUN npm install -g pnpm

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --no-frozen-lockfile

# Copy all source files
COPY . .

# Build application (creates build/ directory with compiled SvelteKit app)
RUN pnpm build

# Stage 2: Runtime - Create minimal production image
FROM node:20-alpine

WORKDIR /app

# Install pnpm globally
RUN npm install -g pnpm

# Install curl for healthcheck
RUN apk add --no-cache curl

# Create non-root user for security
RUN addgroup -g 1001 -S nodejs && adduser -S sveltekit -u 1001

# Copy package files first
COPY --chown=sveltekit:nodejs package.json pnpm-lock.yaml ./

# Install production dependencies - will use volume-mounted node_modules
RUN pnpm install --prod --no-frozen-lockfile

# Copy build artifacts from builder stage
COPY --from=builder --chown=sveltekit:nodejs /app/build ./build

# Switch to non-root user
USER sveltekit

# Expose port
EXPOSE 3000

# Runtime environment variables
# Note: PROTOCOL_HEADER, HOST_HEADER, and PORT_HEADER should be set via docker-compose
# to allow SvelteKit adapter-node to work correctly behind reverse proxy.
# These variables tell SvelteKit which HTTP headers to trust for determining the origin.
# See: https://kit.svelte.dev/docs/adapter-node
ENV NODE_ENV=production
ENV PORT=3000
ENV HOST=0.0.0.0

# Additional env vars set via docker-compose:
# - PROTOCOL_HEADER=x-forwarded-proto (for https detection)
# - HOST_HEADER=x-forwarded-host (for correct host)
# - PORT_HEADER=x-forwarded-port (for non-standard ports)
# - PUBLIC_API_URL (internal API endpoint)
# - ENRICHMENT_API_URL (internal enrichment endpoint)

# Start the Node.js server
CMD ["node", "build"]
