# vpc-cni and aws-ebs-csi-driver are deliberately NOT declared in
# cluster_addons here - see irsa.tf. Wiring their service_account_role_arn
# via this module's cluster_addons input would create a genuine Terraform
# dependency cycle (this module's OIDC provider output feeds the IRSA role,
# but the IRSA role's ARN would need to feed back into this same module's
# input). coredns/kube-proxy don't need IRSA so they're safe to declare
# here; vpc-cni/ebs-csi-driver are created as standalone aws_eks_addon
# resources in irsa.tf, downstream of both this module and their IRSA
# roles - no cycle.
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.kubernetes_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Public access is required (kubectl from your own machine, not a
  # bastion) but restricted to your IP - not 0.0.0.0/0. Private access is
  # also on so nodes reach the API server over the VPC rather than the
  # single NAT gateway.
  cluster_endpoint_public_access       = true
  cluster_endpoint_public_access_cidrs = [var.my_ip_cidr]
  cluster_endpoint_private_access      = true

  # Off by default: unbounded CloudWatch Logs cost for an idle demo
  # cluster. Add specific log types here (e.g. ["api", "audit"]) if
  # actively debugging something.
  cluster_enabled_log_types = []

  enable_irsa = true

  # The module does NOT grant the applying IAM principal cluster access by
  # default (unlike the old aws-auth-configmap-era behavior where the
  # creator got implicit system:masters) - without this, `terraform apply`
  # succeeds but neither `kubectl` nor the AWS Console can see any
  # Kubernetes objects on the cluster afterward. This creates an EKS
  # access entry for whatever principal ran apply.
  enable_cluster_creator_admin_permissions = true

  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
  }

  eks_managed_node_groups = {
    default = {
      instance_types = var.node_instance_types
      capacity_type  = var.node_capacity_type
      ami_type       = "AL2023_x86_64_STANDARD"

      min_size     = var.node_min_size
      max_size     = var.node_max_size
      desired_size = var.node_desired_size

      disk_size = 30
    }
  }

  tags = local.common_tags
}
