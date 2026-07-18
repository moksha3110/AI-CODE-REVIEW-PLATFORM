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
# HOSTNAME=0.0.0.0 is required, not just PORT: Kubernetes auto-injects a
# HOSTNAME env var set to the pod's name into every container, and the
# Next.js standalone server reads process.env.HOSTNAME to decide its bind
# address. Left unset here, that pod-name value resolves (via the pod's
# own /etc/hosts entry) to the pod's IP specifically, not all interfaces -
# Service-routed traffic still reaches it by coincidence (Services target
# Pod IPs), but loopback-based tooling like `kubectl port-forward` breaks,
# since it connects via 127.0.0.1 inside the pod's network namespace.
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
# node:22-slim already ships a UID/GID 1000 "node" user, so appuser needs
# a different uid to avoid a `useradd` collision.
RUN useradd --create-home --uid 1001 appuser

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
