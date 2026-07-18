# No kubernetes/helm provider here on purpose - Terraform owns AWS
# resources, kubectl owns Kubernetes objects (see terraform/README.md).
# The AWS Load Balancer Controller and the postgres StorageClass are both
# deliberately left as documented manual/Phase-7 steps rather than pulled
# into this provider's blast radius.
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}
