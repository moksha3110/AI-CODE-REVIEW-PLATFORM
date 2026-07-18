# IRSA roles for the two add-ons that need AWS API access beyond what the
# node role should have (least-privilege - the node role only needs
# AmazonEKSWorkerNodePolicy + ECR pull, not CNI/EBS permissions directly).
#
# aws-ebs-csi-driver specifically exists to make k8s/infra/postgres's PVC
# bindable at all: a stock EKS cluster ships no default StorageClass and no
# EBS CSI driver, so without this the postgres pod's PersistentVolumeClaim
# sits Pending forever and blocks every service downstream of it. This
# module/addon pair is the AWS-side half of that fix; the Kubernetes-side
# half (an actual `StorageClass` object) is a deliberately-manual step -
# see terraform/README.md - to avoid adding a `kubernetes` provider here
# just to create one 5-line object.
module "vpc_cni_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name             = "${var.cluster_name}-vpc-cni"
  attach_vpc_cni_policy = true
  vpc_cni_enable_ipv4   = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-node"]
    }
  }

  tags = local.common_tags
}

module "ebs_csi_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name             = "${var.cluster_name}-ebs-csi"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }

  tags = local.common_tags
}

# Standalone aws_eks_addon resources, not part of module.eks's
# cluster_addons - see the comment in eks.tf for why (avoids a Terraform
# dependency cycle between the cluster's OIDC output and these roles'
# input).
resource "aws_eks_addon" "vpc_cni" {
  cluster_name             = module.eks.cluster_name
  addon_name               = "vpc-cni"
  service_account_role_arn = module.vpc_cni_irsa.iam_role_arn

  tags = local.common_tags
}

resource "aws_eks_addon" "ebs_csi_driver" {
  cluster_name             = module.eks.cluster_name
  addon_name               = "aws-ebs-csi-driver"
  service_account_role_arn = module.ebs_csi_irsa.iam_role_arn

  tags = local.common_tags
}
