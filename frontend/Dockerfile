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
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

RUN npm install -g serve@14

COPY --from=builder /app/dist ./dist

RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:3000 || exit 1

# serve with SPA fallback (--single) so React Router handles 404s
CMD ["serve", "-s", "dist", "-l", "3000", "--single"]
