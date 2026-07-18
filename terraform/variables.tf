variable "aws_region" {
  description = "AWS region to provision into."
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "EKS cluster name. Matches the k8s/ namespace name (code-review-platform) for consistency across layers."
  type        = string
  default     = "code-review-platform"
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version. Verify this is still within AWS EKS standard support at apply time (support windows move) - check `aws eks describe-addon-versions` or the EKS console."
  type        = string
  default     = "1.31"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones. 2 is EKS's minimum and the cost-conscious choice for a portfolio demo cluster - 3+ buys HA this project doesn't need yet."
  type        = number
  default     = 2
}

variable "node_instance_types" {
  description = "Instance type(s) for the EKS managed node group. This AWS account is restricted to free-tier-eligible instance types only (a hard launch-time restriction, not a quota - confirmed via a failed t3.medium apply). m7i-flex.large (2 vCPU/8GiB) x2 is the free-tier-eligible option that still comfortably fits the resource requests in every k8s/*/deployment.yaml - see terraform/README.md's sizing math."
  type        = list(string)
  default     = ["m7i-flex.large"]
}

variable "node_desired_size" {
  description = "Desired node count."
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum node count."
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Maximum node count."
  type        = number
  default     = 3
}

variable "node_capacity_type" {
  description = "ON_DEMAND (not SPOT) - avoids interruption during a live demo/review session. See terraform/README.md for the spot cost-saving trade-off this deliberately doesn't take."
  type        = string
  default     = "ON_DEMAND"
}

variable "environment" {
  description = "Environment tag applied to every resource."
  type        = string
  default     = "portfolio-demo"
}

variable "my_ip_cidr" {
  description = "Your public IP in CIDR form (e.g. 203.0.113.42/32), used to restrict the EKS API's public endpoint to just you. No default on purpose - get it via `curl https://checkip.amazonaws.com` and fill in terraform.tfvars, same pattern as k8s/secrets.example.yaml's CHANGE_ME placeholders."
  type        = string
}
