# Local state deliberately, for this solo/one-machine phase - no `backend`
# block here. See terraform/README.md's "State management" section for the
# trade-offs (no locking, no remote backup) and the natural next step (an
# S3 backend, using Terraform 1.15's native `use_lockfile` - no DynamoDB
# table needed anymore).
terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
