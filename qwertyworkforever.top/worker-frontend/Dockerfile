# Multi-stage Dockerfile for Worker Frontend
FROM node:20-alpine AS builder

WORKDIR /app

RUN npm install -g pnpm

COPY package.json pnpm-lock.yaml ./

RUN pnpm install --no-frozen-lockfile

COPY . .

RUN pnpm build

FROM node:20-alpine

WORKDIR /app

RUN npm install -g pnpm
RUN apk add --no-cache curl
RUN addgroup -g 1001 -S nodejs && adduser -S sveltekit -u 1001

COPY --chown=sveltekit:nodejs package.json pnpm-lock.yaml ./
RUN pnpm install --prod --no-frozen-lockfile

COPY --from=builder --chown=sveltekit:nodejs /app/build ./build

USER sveltekit

EXPOSE 3000

ENV NODE_ENV=production
ENV PORT=3000
ENV HOST=0.0.0.0

CMD ["node", "build"]
