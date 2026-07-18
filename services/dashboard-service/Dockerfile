FROM node:22-slim AS deps
WORKDIR /app
COPY services/dashboard-service/package.json services/dashboard-service/package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY services/dashboard-service .

# NEXT_PUBLIC_* vars are inlined into the client bundle at build time, not
# read at container start - these ARGs let a different deployment target
# (e.g. AWS in a later phase) override the localhost defaults baked into
# lib/config.ts. Local docker-compose works with no ARGs at all, since the
# defaults already match the ports docker-compose publishes to the host.
ARG NEXT_PUBLIC_AUTH_SERVICE_URL
ARG NEXT_PUBLIC_REPOSITORY_SERVICE_URL
ARG NEXT_PUBLIC_REVIEW_SERVICE_URL
ARG NEXT_PUBLIC_NOTIFICATION_SERVICE_URL
RUN npm run build

FROM node:22-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production PORT=3000
RUN useradd --create-home --uid 1000 appuser

# `output: "standalone"` traces the minimal server + pruned node_modules
# needed to run - static assets and public files are copied in separately.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

USER appuser
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://localhost:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
