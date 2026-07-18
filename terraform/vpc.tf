# 2 AZs, 1 public + 1 private subnet each, single shared NAT gateway.
#
# Single NAT (not one per AZ) is a deliberate SPOF trade-off: if it or its
# AZ has an outage, every private-subnet node loses internet egress
# simultaneously. Saves ~$32+/mo vs one-per-AZ - the right call for a
# portfolio demo cluster, documented rather than silently accepted. See
# terraform/README.md.
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.cluster_name}-vpc"
  cidr = var.vpc_cidr

  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  # /24s carved out of the /16: 10.0.0.0/24, 10.0.1.0/24 private;
  # 10.0.100.0/24, 10.0.101.0/24 public.
  private_subnets = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i)]
  public_subnets  = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 100)]

  enable_nat_gateway = true
  single_nat_gateway = true

  enable_dns_hostnames = true
  enable_dns_support   = true

  # Required for the EKS cluster to find these subnets, and for the AWS
  # Load Balancer Controller (Phase 7 - not installed yet) to auto-discover
  # them. Tagging now is cheap and avoids a real debugging session later.
  public_subnet_tags = {
    "kubernetes.io/role/elb"                    = "1"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"           = "1"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }

  tags = local.common_tags
}
