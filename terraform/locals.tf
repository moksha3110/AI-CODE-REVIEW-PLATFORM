locals {
  common_tags = {
    Project     = "ai-code-review-platform"
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  # Must match the image placeholders in every k8s/*/deployment.yaml and
  # k8s/*/migration-job.yaml exactly - grep for `<AWS_ACCOUNT_ID>.dkr.ecr`
  # across k8s/ if these ever need to change. A `local`, not a `variable`:
  # these names are contractually fixed by already-committed manifests,
  # not something that should be casually overridden via tfvars.
  ecr_repository_names = [
    "auth-service",
    "repository-service",
    "ai-analysis-service",
    "review-service",
    "notification-service",
    "dashboard-service",
  ]
}

data "aws_availability_zones" "available" {
  state = "available"
}
