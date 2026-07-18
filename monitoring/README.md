# Monitoring: Prometheus + Grafana (Phase 10)

Real-time metrics for the EKS cluster and its workloads: node/pod
CPU+memory, API server health, kubelet health, plus every standard
`kubernetes-mixin` Grafana dashboard (Cluster, Namespace, Pod, Node,
Workload, Networking, API server, Kubelet, CoreDNS, Alertmanager).

## What this does NOT do

- **Application-level metrics** (e.g. review-processing latency, queue
  depth, per-service request rates). The 6 services don't currently
  expose a `/metrics` endpoint or `ServiceMonitor` - this phase covers
  cluster/infrastructure observability only. Adding app metrics is a
  natural next step (each service already has structured logging; a
  `prometheus_client`/`prom-client` endpoint per service plus a
  `ServiceMonitor` pointed at it would slot into this same Prometheus).
- **Real alert routing** (Slack/email/PagerDuty). Alertmanager is
  installed and running with the chart's default alerting rules, but no
  `receiver` beyond the default no-op is configured - alerts fire and are
  visible in the Alertmanager UI, they don't page anyone. Wiring a real
  receiver is a `monitoring/values.yaml` change (`alertmanager.config`),
  not an architecture change.
- **Long-term metrics retention.** 2-day retention, no persistent
  storage (see below) - consistent with this project's
  `terraform destroy`-between-sessions pattern (see
  `terraform/README.md`'s Teardown section). Metrics have no reason to
  outlive the cluster.
- **A Terraform-managed install.** Same boundary already established for
  the AWS Load Balancer Controller: this is a cluster workload (Helm
  chart + Kubernetes objects), not AWS infrastructure, so it's installed
  imperatively via the Helm CLI and documented here, not provisioned via
  Terraform's helm provider.

## Key decisions and trade-offs

**Every resource request is trimmed from the chart's defaults.** The
cluster's 2x m7i-flex.large nodes were already at ~65-70% CPU requests
before this stack (see `terraform/README.md`'s node sizing note) -
installing `kube-prometheus-stack` at its out-of-the-box defaults would
risk pods stuck `Pending`. `values.yaml` sets explicit, conservative
`requests`/`limits` for the operator, Prometheus, Alertmanager, Grafana,
and kube-state-metrics. Confirmed after install: CPU requests now sit at
82%/68% across the two nodes - all 7 monitoring pods scheduled and
`Running`, but headroom is genuinely tight. A future service that needs
meaningfully more CPU may need a 3rd node.

**No persistent storage.** Prometheus, Alertmanager, and Grafana all use
`emptyDir` (the chart's default when no `storageSpec`/persistence is
configured) - no extra EBS volumes, no extra cost, and consistent with
the "cluster gets destroyed between review sessions" reality: a
dashboard's *definition* should survive (it's in this chart's defaults +
version control), but *historical data* has nowhere useful to persist to
anyway.

**Shares the existing ALB, doesn't provision a second one.** Grafana's
`Ingress` (`monitoring/grafana-ingress.yaml`) uses the same
`alb.ingress.kubernetes.io/group.name: code-review-platform` annotation
as `k8s/ingress.yaml`, so the AWS Load Balancer Controller merges it into
the one ALB that already exists rather than creating a second one - this
project already paid once (documented in `terraform/README.md`) for the
lesson that a stray ALB left running is a real, easy-to-miss cost
(~$16-25/mo). It's a separate YAML file (not folded into
`k8s/ingress.yaml`) because Grafana runs in the `monitoring` namespace,
and an `Ingress` rule can't reference a `Service` in a different
namespace.

**Grafana admin credentials: a real generated password, not the chart's
`prom-operator` default.** Created imperatively
(`kubectl create secret generic grafana-admin-credentials`), referenced
in `values.yaml` via `grafana.admin.existingSecret` - never committed to
git, same pattern as `k8s/secrets.example.yaml` vs the real
(gitignored) `k8s/secrets.yaml`.

**Cluster-only monitors disabled.** `kubeEtcd`/`kubeControllerManager`/
`kubeScheduler`/`kubeProxy` are off in `values.yaml` - EKS manages the
control plane, so these endpoints don't exist on the nodes and the chart
would otherwise show permanently-down scrape targets for components that
were never reachable to begin with.

## Prerequisites

- The EKS cluster from `terraform/` already applied, `kubectl` pointed
  at it (`aws eks update-kubeconfig --region us-east-1 --name
  code-review-platform`).
- The AWS Load Balancer Controller already installed (see
  `terraform/README.md`'s "Installing the AWS Load Balancer Controller"
  section) - Grafana's `Ingress` depends on it exactly like the app's.

## Install

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

kubectl create namespace monitoring

# Real password, not committed - save it somewhere you'll find it again.
GRAFANA_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | head -c 24)
kubectl create secret generic grafana-admin-credentials \
  --namespace monitoring \
  --from-literal=admin-user=admin \
  --from-literal=admin-password="$GRAFANA_PASSWORD"
echo "Grafana admin password: $GRAFANA_PASSWORD"

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --version 87.17.0 \
  -f monitoring/values.yaml \
  --wait --timeout 5m

# Grafana Ingress - replace grafana.crp.local with your ALB's actual
# sslip.io hostname (see k8s/README.md's sslip.io section for how to
# derive it - same IP the app's 5 hostnames already use).
sed 's/grafana.crp.local/grafana.<ALB-IP-with-dashes>.sslip.io/' \
  monitoring/grafana-ingress.yaml | kubectl apply -f -
```

## Verification

```bash
kubectl get pods -n monitoring
# all 7 pods (operator, prometheus, alertmanager, grafana, kube-state-metrics,
# 2x node-exporter) should be Running

kubectl get ingress -n monitoring
# ADDRESS should match `kubectl get ingress -n code-review-platform` -
# same ALB, confirming it merged rather than provisioning a second one

# Confirm real scrape targets are healthy (not just "pods exist"):
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s "http://localhost:9090/api/v1/query?query=up" | grep -o '"value":\[[0-9.]*,"[01]"\]' | sort | uniq -c
```

Then open `http://grafana.<ALB-IP>.sslip.io`, log in with the generated
credentials, and open any `kubernetes-mixin` dashboard (e.g. "Kubernetes
/ Compute Resources / Cluster") - panels should show real, non-empty
data for both nodes.

## Teardown

Helm-managed, not Terraform-managed - `terraform destroy` has no
knowledge of this and won't remove it (same reasoning as the AWS Load
Balancer Controller in `terraform/README.md`). Unlike that controller,
this doesn't provision any AWS resource outside the cluster (no extra
ALB, no extra EBS volume), so there's no orphaned-cost risk if the
cluster is destroyed out from under it - but tearing down cleanly first
is still tidier:

```bash
kubectl delete -f monitoring/grafana-ingress.yaml
helm uninstall kube-prometheus-stack -n monitoring
kubectl delete namespace monitoring
```
