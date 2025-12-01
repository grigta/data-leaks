# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Install pnpm
RUN npm install -g pnpm

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy source files
COPY . .

# Build the application
RUN pnpm build

# Stage 2: Runtime
FROM node:20-alpine

WORKDIR /app

# Install pnpm
RUN npm install -g pnpm

# Install curl for healthcheck
RUN apk add --no-cache curl

# Create non-root user
RUN addgroup -g 1001 -S sveltekit-admin && \
    adduser -S sveltekit-admin -u 1001

# Copy package files first
COPY --chown=sveltekit-admin:sveltekit-admin package.json pnpm-lock.yaml ./

# Install production dependencies - will use volume-mounted node_modules
RUN pnpm install --prod --frozen-lockfile

# Copy built application
COPY --from=builder --chown=sveltekit-admin:sveltekit-admin /app/build ./build

# Switch to non-root user
USER sveltekit-admin

# Expose port
EXPOSE 3000

# Environment variables
ENV NODE_ENV=production
ENV PORT=3000
ENV HOST=0.0.0.0

# Start the application
CMD ["node", "build"]
