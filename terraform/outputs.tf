output "cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS cluster API server endpoint."
  value       = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded cluster CA certificate."
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "cluster_oidc_issuer_url" {
  description = "OIDC issuer URL - needed for any future per-service IRSA role (e.g. the AWS Load Balancer Controller's own role in Phase 7)."
  value       = module.eks.cluster_oidc_issuer_url
}

output "cluster_security_group_id" {
  description = "Security group ID attached to the EKS cluster."
  value       = module.eks.cluster_security_group_id
}

output "vpc_id" {
  description = "VPC ID."
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs (where the node group runs)."
  value       = module.vpc.private_subnets
}

output "public_subnet_ids" {
  description = "Public subnet IDs (NAT gateway now; ALB in Phase 7)."
  value       = module.vpc.public_subnets
}

output "ecr_repository_urls" {
  description = "ECR repository URLs, keyed by service name - these are what k8s/*/deployment.yaml's <AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/<service>:latest placeholders should be replaced with."
  value       = { for name, repo in aws_ecr_repository.service : name => repo.repository_url }
}

output "vpc_cni_irsa_role_arn" {
  description = "IRSA role ARN for the vpc-cni add-on (debug visibility)."
  value       = module.vpc_cni_irsa.iam_role_arn
}

output "ebs_csi_irsa_role_arn" {
  description = "IRSA role ARN for the aws-ebs-csi-driver add-on (debug visibility)."
  value       = module.ebs_csi_irsa.iam_role_arn
}

output "lb_controller_irsa_role_arn" {
  description = "IRSA role ARN for the AWS Load Balancer Controller - pass this to the Helm install's serviceAccount.annotations, see terraform/README.md."
  value       = module.lb_controller_irsa.iam_role_arn
}

output "update_kubeconfig_command" {
  description = "Run this to point kubectl at the new cluster."
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}
