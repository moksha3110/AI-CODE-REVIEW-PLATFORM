# Kubernetes manifests (Phase 6)

Plain YAML (no Helm/Kustomize) for running the whole platform - all six
services plus Postgres, Redis, and RabbitMQ - in a single Kubernetes
namespace. Targets AWS EKS eventually, but everything here runs in-cluster
rather than as managed AWS services, and no cloud resources are actually
provisioned by anything in this directory. See "Explicitly out of scope"
below for exactly what that means.

This mirrors `docker-compose.yml`'s topology as closely as Kubernetes
allows: one namespace, one Postgres instance with five logical databases,
one Redis, one RabbitMQ, and the same env-var names every service's
`app/core/config.py` already reads.

## Layout

```
k8s/
  namespace.yaml            single namespace: code-review-platform
  secrets.example.yaml      template for the real (gitignored) secrets.yaml
  ingress.yaml               one Ingress, 5 host rules
  infra/{postgres,redis,rabbitmq}/
  <service>/{configmap.yaml, deployment.yaml, service.yaml, migration-job.yaml}
```

`ai-analysis-service` has a `service.yaml` (ClusterIP, for in-cluster
reachability/debugging and a future Prometheus scrape target) but no
Ingress rule - it has no public API. `dashboard-service` has no
`configmap.yaml` - see "Building the dashboard image" below for why.

## Secrets

No Vault / External Secrets Operator / Sealed Secrets yet - that's a
Terraform-phase (Phase 8) decision, tied to real AWS IAM/KMS resources that
don't exist yet. For this phase:

1. Copy `k8s/secrets.example.yaml` to `k8s/secrets.yaml` (gitignored) and
   fill in every `CHANGE_ME`, **except** the two PEM-bearing secrets
   (`jwt-keypair`, `github-app-key`) - create those imperatively instead so
   PEM contents never end up pasted into a YAML file:

   ```bash
   kubectl create secret generic jwt-keypair \
     --from-file=private.pem=./services/auth-service/keys/private.pem \
     --from-file=public.pem=./services/auth-service/keys/public.pem \
     -n code-review-platform

   kubectl create secret generic jwt-public-key \
     --from-file=public.pem=./services/auth-service/keys/public.pem \
     -n code-review-platform

   kubectl create secret generic github-app-key \
     --from-file=app_private_key.pem=./services/repository-service/keys/app_private_key.pem \
     -n code-review-platform
   ```

2. Delete those three Secret blocks from your local `k8s/secrets.yaml`
   before applying it (they're only in the example for documentation), then:

   ```bash
   kubectl apply -f k8s/secrets.yaml
   ```

Keep these consistent when filling in the template (not enforced by
Kubernetes - see the comments at the top of `secrets.example.yaml`):
every `DATABASE_URL` must embed the same password as
`postgres-credentials.POSTGRES_PASSWORD`; `rabbitmq-credentials.RABBITMQ_URL`
must embed the same user/pass as `rabbitmq-server-credentials`;
`internal-service-api-key` is one shared value referenced by
repository-service, ai-analysis-service, and notification-service.

## Building the dashboard image

`services/dashboard-service/Dockerfile` inlines four `NEXT_PUBLIC_*` backend
URLs into the client-side JS bundle **at `docker build` time** - confirmed
by reading the Dockerfile and `src/lib/config.ts`. Kubernetes Pod env vars
on `dashboard-service`'s Deployment have **zero effect** on these values at
runtime; that's why there's no ConfigMap for this service. Build it with:

```bash
docker build \
  -f services/dashboard-service/Dockerfile \
  --build-arg NEXT_PUBLIC_AUTH_SERVICE_URL=https://auth.crp.local \
  --build-arg NEXT_PUBLIC_REPOSITORY_SERVICE_URL=https://api-repos.crp.local \
  --build-arg NEXT_PUBLIC_REVIEW_SERVICE_URL=https://api-reviews.crp.local \
  --build-arg NEXT_PUBLIC_NOTIFICATION_SERVICE_URL=https://api-notifications.crp.local \
  -t <registry>/dashboard-service:<tag> .
```

**If a backend service's public hostname ever changes, this image must be
rebuilt and re-pushed** - re-applying `k8s/ingress.yaml` alone will not
update anything the browser already has. This is a real operational
coupling, not an oversight; it's why the five hostnames below are decided
once, up front, rather than left as free variables.

## Hostnames and image references (placeholders - replace before real use)

Every manifest uses two kinds of placeholder:

- **Hostnames**: `auth.crp.local`, `api-repos.crp.local`,
  `api-reviews.crp.local`, `api-notifications.crp.local`, `app.crp.local` -
  a clearly-fake domain, since real DNS doesn't exist until Phase 7. Used in
  `k8s/ingress.yaml`, every service's `CORS_ALLOW_ORIGINS`/`FRONTEND_URL`
  ConfigMap value, and the dashboard build-arg command above. Replace all of
  these together (grep for `crp.local`) when real DNS exists.

  **For a real end-to-end verification without owning a domain**, this
  project used [sslip.io](https://sslip.io) instead: once the AWS Load
  Balancer Controller (see `terraform/README.md`) provisions a real ALB,
  resolve its DNS name to an IP (`dig +short <alb-dns-name>`) and derive 5
  hostnames like `auth.<ip-with-dashes>.sslip.io`,
  `app.<ip-with-dashes>.sslip.io`, etc. - any subdomain of `<ip>.sslip.io`
  resolves to `<ip>` automatically, no DNS provisioning needed, and this
  maps directly onto the existing host-based Ingress rules. **Caveat,
  confirmed real**: ALB IPs are not guaranteed stable long-term (AWS can
  rotate the underlying IPs behind an ALB's DNS name) - fine for a
  demo verified now and `terraform destroy`-ed after, not something to
  treat as a permanent hostname. These real, ephemeral, account-specific
  values were applied directly to the live cluster (not committed here) -
  see "Secrets" above for why account-specific values stay out of the
  checked-in manifests.
- **Images**: `<AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/<service>:latest`
  in every `deployment.yaml`/`migration-job.yaml` - an ECR-shaped
  placeholder matching the actual Phase 7 target. Nothing in this phase
  creates the ECR repositories or pushes to them.

## Apply order

```bash
kubectl apply -f k8s/namespace.yaml

# secrets BEFORE infra (see "Secrets" above) - postgres and rabbitmq both
# read their credentials from a Secret at container start
# (postgres-credentials, rabbitmq-server-credentials), so they'll sit in
# CreateContainerConfigError until these exist. Confirmed the hard way
# during this phase's own kind/minikube smoke test - the original draft of
# this doc had secrets applied after infra and both pods blocked exactly
# like that.
kubectl apply -f k8s/secrets.yaml

# infra, then wait for it to be ready before anything depends on it
kubectl apply -f k8s/infra/postgres/ -f k8s/infra/redis/ -f k8s/infra/rabbitmq/
kubectl wait --for=condition=ready pod -l app=postgres -n code-review-platform --timeout=120s
kubectl wait --for=condition=ready pod -l app=redis -n code-review-platform --timeout=60s
kubectl wait --for=condition=ready pod -l app=rabbitmq -n code-review-platform --timeout=60s

# one service at a time: configmap + migration job, wait for it to complete,
# THEN the deployment + service. Not scripted as a single loop here on
# purpose - watch each migration job actually complete before moving on.
for svc in auth-service repository-service ai-analysis-service review-service notification-service; do
  kubectl apply -f k8s/$svc/configmap.yaml
  kubectl apply -f k8s/$svc/migration-job.yaml
  kubectl wait --for=condition=complete job/$svc-migrate -n code-review-platform --timeout=60s
  kubectl apply -f k8s/$svc/deployment.yaml -f k8s/$svc/service.yaml
done

kubectl apply -f k8s/dashboard-service/deployment.yaml -f k8s/dashboard-service/service.yaml
kubectl apply -f k8s/ingress.yaml
```

## Explicitly out of scope this phase

- Real EKS/VPC provisioning, node groups, security groups (Terraform,
  Phase 8).
- Installing the AWS Load Balancer Controller, and the real ALB it would
  create from `ingress.yaml` (Phase 7) - the Ingress annotations here are
  correct but inert until that controller exists.
- Route53 DNS records, ACM certificates, cert-manager, real TLS
  termination.
- IAM Roles for Service Accounts (IRSA) - nothing here talks to an AWS API.
- Migrating Postgres/Redis/RabbitMQ to RDS/ElastiCache/Amazon MQ -
  everything stays in-cluster per this phase's scope.
- HorizontalPodAutoscaler, Cluster Autoscaler/Karpenter - fixed replica
  counts only.
- NetworkPolicies - every pod in the namespace can currently reach every
  other pod; a real gap, deferred rather than silently accepted.
- Sealed Secrets / External Secrets Operator / Vault / SOPS - plain
  `kubectl create secret` only, see "Secrets" above.
- PodDisruptionBudgets, pod anti-affinity, topology spread constraints.
- CI/CD to build/push/deploy automatically.
- Prometheus actually scraping `/metrics` (every service already exposes
  it; nothing collects it yet).

## Local verification (kind)

No EKS cluster exists yet, so this is a smoke test against a local `kind`
cluster - it proves the manifests wire together correctly (Service DNS
names resolve, probes pass, migrations run), not that the AWS-specific
parts (ALB, IRSA) work, since those don't exist locally. `kind` uses the
NGINX ingress controller for local testing, not `alb` - a substitution for
this step only; the real target stays `alb` on EKS.

```bash
kind create cluster --name crp-smoke

# build all six images exactly as docker-compose does
for svc in auth-service repository-service ai-analysis-service review-service notification-service; do
  docker build -f services/$svc/Dockerfile -t crp/$svc:smoke .
  kind load docker-image crp/$svc:smoke --name crp-smoke
done
docker build -f services/dashboard-service/Dockerfile \
  --build-arg NEXT_PUBLIC_AUTH_SERVICE_URL=http://localhost:8000 \
  --build-arg NEXT_PUBLIC_REPOSITORY_SERVICE_URL=http://localhost:8001 \
  --build-arg NEXT_PUBLIC_REVIEW_SERVICE_URL=http://localhost:8003 \
  --build-arg NEXT_PUBLIC_NOTIFICATION_SERVICE_URL=http://localhost:8004 \
  -t crp/dashboard-service:smoke .
kind load docker-image crp/dashboard-service:smoke --name crp-smoke
```

Then temporarily edit every `image:` field to `crp/<service>:smoke` (or
`kubectl set image` after applying), fill in `k8s/secrets.yaml` with a
locally-generated dummy JWT keypair
(`services/auth-service/scripts/generate_keys.sh`), a placeholder GitHub
App key, and a fake `ANTHROPIC_API_KEY` - no real AI calls are needed to
verify the manifests wire together - and follow "Apply order" above.

Then:

```bash
kubectl get pods -n code-review-platform    # everything should reach Running/Ready

# confirm migrations actually created schema
kubectl exec -it postgres-0 -n code-review-platform -- \
  psql -U postgres -d auth_service -c '\dt'

# confirm in-cluster DNS/env wiring for each public service, one at a time
kubectl port-forward svc/auth-service 8000:8000 -n code-review-platform &
curl http://localhost:8000/api/v1/healthz
curl http://localhost:8000/api/v1/readyz   # exercises DATABASE_URL's in-cluster DNS
```

Repeat the port-forward+curl check for `repository-service`,
`review-service`, and `notification-service`; confirm
`ai-analysis-service` is reachable the same way but has no Ingress rule.
Finally, port-forward `dashboard-service`, open it in a browser, and try
the GitHub OAuth login flow against the port-forwarded `auth-service` - this
exercises CORS, JWT issuance, and the no-BFF (browser calls services
directly) architecture behind real Kubernetes Services instead of
`docker-compose`'s network.

Tear down with `kind delete cluster --name crp-smoke`.
