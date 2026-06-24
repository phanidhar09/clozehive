# ── Stage 1: build ────────────────────────────────────────────────────────────
# Use glibc (bookworm-slim) instead of alpine-musl so rollup's platform-specific
# optional dep (@rollup/rollup-linux-*-gnu) resolves cleanly — avoids
# https://github.com/npm/cli/issues/4828 when building from a macOS lockfile.
FROM node:20-bookworm-slim AS builder

WORKDIR /app

# Workaround for https://github.com/npm/cli/issues/4828 — lockfiles generated
# on a different OS/arch can omit rollup's platform-specific optional deps.
# Regenerate node_modules inside the container so the correct binary is linked.
COPY package.json package-lock.json* ./
RUN rm -f package-lock.json && npm install --no-audit --no-fund --include=optional

# Copy source and build
COPY . .
# Empty = relative `/api` + `/uploads` in the browser; this image proxies them to api-gateway (see nginx.docker.conf).
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
# Observability — Vite inlines VITE_* at build time, so these must be build args.
# All optional; empty values leave the integration disabled.
ARG VITE_SENTRY_DSN=""
ARG VITE_SENTRY_TRACES_SAMPLE_RATE=""
ARG VITE_POSTHOG_KEY=""
ARG VITE_POSTHOG_HOST=""
ARG VITE_ENVIRONMENT=""
ARG VITE_APP_VERSION=""
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN} \
    VITE_SENTRY_TRACES_SAMPLE_RATE=${VITE_SENTRY_TRACES_SAMPLE_RATE} \
    VITE_POSTHOG_KEY=${VITE_POSTHOG_KEY} \
    VITE_POSTHOG_HOST=${VITE_POSTHOG_HOST} \
    VITE_ENVIRONMENT=${VITE_ENVIRONMENT} \
    VITE_APP_VERSION=${VITE_APP_VERSION}
RUN npm run build

# ── Stage 2: nginx (proxies /api and /uploads — `serve` cannot, and breaks vision upload) ─
FROM nginx:1.27-alpine AS runner

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.docker.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/ || exit 1
