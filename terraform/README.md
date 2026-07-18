# Terraform: AWS infrastructure (Phase 8)

Provisions exactly what `k8s/` (Phase 6) needs to actually run on a real
cluster: a VPC, an EKS cluster + managed node group, and 6 ECR repositories.
Targets `us-east-1` by default.

## What this does NOT do

- **Install the AWS Load Balancer Controller.** `k8s/ingress.yaml` targets
  `ingressClassName: alb`, but the controller itself needs IRSA + a Helm
  install *onto* the cluster - that's deploying software, not provisioning
  infrastructure, and stays a Phase 7 step.
- **Route53 DNS, ACM certificates, TLS termination.**
- **Migrate Postgres/Redis/RabbitMQ to managed AWS services** (RDS,
  ElastiCache, Amazon MQ). This was already decided in Phase 6 - everything
  stays in-cluster - and isn't revisited here.
- **Per-service IRSA role bindings** beyond the two add-ons that need them
  to function at all (vpc-cni, aws-ebs-csi-driver). A future service that
  needs its own AWS permissions (e.g. S3 access) gets its own IRSA role
  when that need actually exists.
- **HorizontalPodAutoscaler / Cluster Autoscaler / Karpenter.**
- **An S3 remote state backend.** Local state only - see "State management"
  below.
- **Create the Kubernetes `StorageClass` object itself.** See "The
  StorageClass gap" below - Terraform provisions the AWS-side EBS CSI
  driver, but the actual Kubernetes object is a one-time manual `kubectl
  apply`.

## Key decisions and trade-offs

**Community modules, not hand-rolled resources.** Uses
`terraform-aws-modules/vpc/aws` and `.../eks/eks`. Unlike the k8s-phase
choice of plain YAML over Helm (about legibility of *this project's own*
application config), VPC/EKS wiring is undifferentiated cloud plumbing -
security group rules between control plane and nodes, OIDC provider
thumbprints, node bootstrap user-data - that these modules get right and
hand-rolling risks getting subtly wrong. Every module call here is still
explicit, with every non-default argument commented.

**The StorageClass gap.** `k8s/infra/postgres/statefulset.yaml`'s PVC has
no `storageClassName` and relies on the cluster's default. A stock EKS
cluster ships neither a default StorageClass nor the EBS CSI driver -
without both, the postgres pod's PVC sits `Pending` forever and blocks
every service downstream of it. This Terraform config installs the
`aws-ebs-csi-driver` EKS add-on and its IRSA role (see `irsa.tf`) - the
AWS-side half of the fix. It deliberately does **not** add a `kubernetes`
provider just to create the actual `StorageClass` object, to keep "Terraform
owns AWS, kubectl owns Kubernetes objects" a clean boundary, and to avoid
the `kubernetes` provider's known gotcha where its EKS auth token expires
after 15 minutes - a from-scratch `apply` creating VPC+EKS+node group
commonly takes 15-20 minutes, so a naively-wired provider resource can fail
on exactly the run that needs it most. After `apply` and `update-kubeconfig`
(below), run once:

```bash
kubectl apply -f - <<'EOF'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: ebs.csi.aws.com
volumeBindingMode: WaitForFirstConsumer
parameters:
  type: gp3
EOF
```

**Single NAT gateway, not one per AZ.** A deliberate SPOF: if it or its AZ
has an outage, every private-subnet node loses internet egress
simultaneously. Saves ~$32+/mo vs one-per-AZ. The right call for a
portfolio demo cluster - documented, not hidden.

**EKS API endpoint restricted to your IP**, not `0.0.0.0/0`
(`cluster_endpoint_public_access_cidrs`). Basic hygiene; means you need to
update `terraform.tfvars` and re-apply (or `-target` just that change) if
your IP changes.

**Node group: `t3.medium` x2, ON_DEMAND, AL2023.** Sized against the actual
committed manifests - 15 pods (12 app-tier + 3 infra) requesting ~1.9 vCPU /
~2.44Gi total, plus add-on overhead - comfortably under 2x t3.medium's
allocatable with ~40% headroom. `t3.large` is the more comfortable
alternative if every pod's `limits` (not just `requests`) were hit
simultaneously (~$60/mo more) - noted, not the default. On-demand (not
spot) to avoid interruption during a live demo. AL2023 (not Bottlerocket)
for debuggability - the better demo trade-off, not the better production
one.

**State management: local, deliberately.** Solo operator, one machine, no
CI applying this. Trade-offs: no locking (a real concern only if you ever
run this from two machines), no remote backup (lose the disk, lose the
state - recovery means `terraform import`-ing everything back or
destroy/recreate), no team collaboration. Natural next step whenever this
stops being a one-person project: an S3 backend - Terraform 1.15's native
`use_lockfile` needs no DynamoDB table anymore, simpler than the old
S3+DynamoDB pattern.

## Cost (rough, us-east-1, verify against current AWS pricing before applying)

| Item | Monthly (~730 hrs) |
|---|---|
| EKS control plane (fixed) | ~$73 |
| 2x t3.medium on-demand | ~$61 |
| NAT gateway (fixed) + light data processing | ~$35 |
| EBS (2x 30GB node root + 10GB postgres PVC) | ~$6 |
| ECR storage (lifecycle-bounded) | ~$1-2 |
| KMS key (EKS module's default secrets-encryption key) | ~$1 |
| **Total, running continuously** | **~$175-180/mo** |

**~$108/mo of that (control plane + NAT gateway) accrues even with an idle,
empty cluster.** Since this is reviewed episodically (recruiter/admissions
committee), `terraform destroy` between review sessions and re-`apply`
before a demo is the realistic way to avoid a standing bill.

## Prerequisites

- Terraform >= 1.15, AWS CLI v2, credentials configured
  (`aws sts get-caller-identity` should succeed).
- `cp terraform.tfvars.example terraform.tfvars` and fill in `my_ip_cidr`
  (get it via `curl https://checkip.amazonaws.com`).

## Usage

```bash
terraform init
terraform validate
terraform plan -out=tfplan   # review carefully - creates ~$175-180/mo of real resources
terraform apply tfplan       # only when you're ready to incur that cost

# once applied:
aws eks update-kubeconfig --region us-east-1 --name code-review-platform
kubectl apply -f - <<'EOF'   # the StorageClass gap, see above
...
EOF

# push images (after `terraform output ecr_repository_urls`):
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
docker build -f services/auth-service/Dockerfile -t <account>.dkr.ecr.us-east-1.amazonaws.com/auth-service:latest .
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/auth-service:latest
# repeat per service, then update k8s/*/deployment.yaml's image: placeholders
# to match, and follow k8s/README.md's apply order.
```

## Installing the AWS Load Balancer Controller (manual, not Terraform)

`k8s/ingress.yaml` targets `ingressClassName: alb`, but nothing provisions
a real ALB until this controller exists in the cluster. This IRSA role
*is* provisioned by this Terraform config (`terraform/irsa.tf`'s
`lb_controller_irsa` module); the controller itself is a Helm chart,
installed as a deliberately separate, manual step - same
15-minute-EKS-auth-token-expiry reasoning that already kept the
`kubernetes` provider out of this config for the StorageClass gap above.

```bash
helm repo add eks https://aws.github.io/eks-charts && helm repo update
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=$(terraform output -raw cluster_name) \
  --set serviceAccount.create=true \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=$(terraform output -raw lb_controller_irsa_role_arn) \
  --set region=us-east-1 \
  --set vpcId=$(terraform output -raw vpc_id)
kubectl -n kube-system rollout status deployment/aws-load-balancer-controller
```

Once running, `kubectl apply -f k8s/ingress.yaml` provisions a real ALB
within a few minutes (`kubectl get ingress code-review-platform -n
code-review-platform -w` until `ADDRESS` populates). **Note**:
`alb.ingress.kubernetes.io/listen-ports` in that manifest must not declare
an HTTPS listener without a `certificate-arn` annotation - confirmed this
breaks reconciliation entirely (`no certificate found for host: ...`), not
just a no-op, if no ACM cert exists yet.

## GitHub Actions CI/CD (Phase 9)

`terraform/github_actions_oidc.tf` provisions what `.github/workflows/ci-cd.yml`
needs to deploy on merge to `main`: an OIDC provider trusting
`token.actions.githubusercontent.com`, an IAM role scoped via exact-match
(`StringEquals`, not `StringLike`) trust conditions to only
`repo:moksha3110@180270968/AI-CODE-REVIEW-PLATFORM@1304319896:ref:refs/heads/main`
(no long-lived AWS access keys stored in GitHub at all), and an EKS access
entry giving that role `AmazonEKSEditPolicy` scoped to the
`code-review-platform` namespace only - not cluster-admin.

**Note on the `sub` claim format**: GitHub embeds stable numeric owner/repo
IDs in the `sub` claim (`OWNER@id/REPO@id`), not just the plain
`repo:OWNER/REPO:ref:...` format most OIDC tutorials show - confirmed by
decoding an actual OIDC JWT from a live `deploy` run this session, after
the plain-name value silently failed every `AssumeRoleWithWebIdentity` call
with an identical, unhelpful "Not authorized" error. These IDs are
immutable (survive renames), so this is a *stricter* binding than the
name-only version, not a loosened one - but it means the trust policy's
`sub` value isn't guessable from the repo's URL alone if this project is
ever forked or the role recreated; re-derive it the same way: add a
throwaway debug step to the `deploy` job that decodes
`$ACTIONS_ID_TOKEN_REQUEST_TOKEN`'s JWT payload and prints `sub`.

After `terraform apply`, set these in the repo's Settings -> Secrets and
variables -> Actions (`gh` CLI isn't used in this project's workflow, so
this is a manual one-time step):

| Name | Type | Value |
|---|---|---|
| `AWS_GITHUB_ACTIONS_ROLE_ARN` | Secret | `terraform output github_actions_deploy_role_arn` |
| `AWS_REGION` | Variable | `us-east-1` |
| `EKS_CLUSTER_NAME` | Variable | `code-review-platform` |
| `NEXT_PUBLIC_AUTH_SERVICE_URL` | Variable | current `auth.<ip>.sslip.io` (or real domain) |
| `NEXT_PUBLIC_REPOSITORY_SERVICE_URL` | Variable | current `api-repos.<ip>.sslip.io` |
| `NEXT_PUBLIC_REVIEW_SERVICE_URL` | Variable | current `api-reviews.<ip>.sslip.io` |
| `NEXT_PUBLIC_NOTIFICATION_SERVICE_URL` | Variable | current `api-notifications.<ip>.sslip.io` |

The 4 `NEXT_PUBLIC_*` Variables need updating by hand whenever the ALB is
torn down and recreated (its IP isn't stable - see the sslip.io section in
`k8s/README.md`) - same "documented manual step" pattern as the
StorageClass and ALB Controller install above, not something CD resolves
dynamically (a real new failure mode - the Ingress/ALB might not exist yet
post-`destroy` - for marginal benefit).

**Expected failure mode, not a bug**: if the cluster has been
`terraform destroy`-ed since the last deploy, the `deploy` job's
`kubectl` steps fail (cluster doesn't exist) - re-`apply` this Terraform
config, redo the Load Balancer Controller install and Ingress steps
above, update the 4 hostname Variables, and the next merge to `main`
succeeds again.

## Teardown

**The ALB is created by this controller reacting to the Ingress object,
not by Terraform - `terraform destroy` has no knowledge of it and will
not delete it.** Deleting the cluster underneath a live ALB orphans a real
load balancer that keeps billing (~$16-25/mo) with nothing left to manage
it, and it won't show up in `terraform plan`/`show` at all since it's
entirely outside Terraform's graph. Confirmed real, not hypothetical, this
session.

```bash
# 1. delete the Ingress first, and WAIT for the ALB to actually deprovision:
kubectl delete -f k8s/ingress.yaml -n code-review-platform
aws elbv2 describe-load-balancers --region us-east-1 --query \
  "LoadBalancers[?contains(LoadBalancerName, 'codereviewplatform')]"
# ^ expect this to return empty before proceeding

# 2. optional but tidy - avoids a dangling Helm release for a cluster
#    that's about to disappear:
helm uninstall aws-load-balancer-controller -n kube-system

# 3. now safe - nothing AWS-created-but-Terraform-unmanaged remains:
terraform destroy
```

## Verification without incurring cost

```bash
terraform fmt -check -recursive
terraform init
terraform validate
terraform plan -out=tfplan   # calls real read-only AWS APIs, creates nothing
terraform show tfplan
```
