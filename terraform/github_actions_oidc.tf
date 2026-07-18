# GitHub Actions OIDC federation for CI/CD (Phase 9) - deliberately a
# separate file from irsa.tf. Every role in irsa.tf federates against
# module.eks.oidc_provider_arn (the EKS cluster's OWN OIDC issuer, trusted
# by EKS for in-cluster ServiceAccounts via IRSA). token.actions.
# githubusercontent.com is a completely different, account-level OIDC
# trust relationship with no connection to the cluster's identity
# provider - keeping them in separate files avoids implying a dependency
# between the two that doesn't exist.

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = local.common_tags
}

# Trust policy uses StringEquals (exact match), not StringLike, on both
# claims - this role is only ever assumed by the `deploy` job in
# .github/workflows/ci-cd.yml, which itself only runs on push to main, so
# nothing legitimate needs a looser match. repo:OWNER/REPO:* (matching
# ANY branch/PR/tag) is the single most common real-world OIDC
# misconfiguration - deliberately not doing that here.
data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      # GitHub now embeds stable numeric owner/repo IDs in the sub claim
      # (immutable IDs, added to survive org/repo renames) instead of the
      # plain "repo:OWNER/REPO:ref:..." format - confirmed by decoding the
      # actual OIDC JWT a live `deploy` run received, since the old
      # name-only value here silently never matched. Still StringEquals,
      # still exact-match: this is a stricter binding than before (tied to
      # the immutable IDs, not just the renameable name), not a loosening.
      values = ["repo:moksha3110@180270968/AI-CODE-REVIEW-PLATFORM@1304319896:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions_deploy" {
  name               = "${var.cluster_name}-github-actions-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json

  tags = local.common_tags
}

# ECR push (to the 6 repos this project owns) + eks:DescribeCluster (needed
# for `aws eks update-kubeconfig`). No eks:* write actions here - actual
# in-cluster authorization is the access entry below, not IAM policy.
data "aws_iam_policy_document" "github_actions_deploy" {
  statement {
    sid       = "EcrAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # the only ECR action that doesn't support resource scoping
  }

  statement {
    sid    = "EcrPush"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = [for r in aws_ecr_repository.service : r.arn]
  }

  statement {
    sid       = "EksDescribe"
    effect    = "Allow"
    actions   = ["eks:DescribeCluster"]
    resources = [module.eks.cluster_arn]
  }
}

resource "aws_iam_role_policy" "github_actions_deploy" {
  name   = "${var.cluster_name}-github-actions-deploy"
  role   = aws_iam_role.github_actions_deploy.id
  policy = data.aws_iam_policy_document.github_actions_deploy.json
}

# In-cluster authorization: EditPolicy scoped to this namespace only, not
# cluster-admin. Covers everything CD needs (create/update/delete
# Deployments, Jobs, Services, ConfigMaps) but excludes RBAC objects - a
# token minted automatically on every merge has no legitimate reason to
# touch cluster RBAC.
resource "aws_eks_access_entry" "github_actions" {
  cluster_name  = module.eks.cluster_name
  principal_arn = aws_iam_role.github_actions_deploy.arn

  tags = local.common_tags
}

resource "aws_eks_access_policy_association" "github_actions" {
  cluster_name  = module.eks.cluster_name
  principal_arn = aws_iam_role.github_actions_deploy.arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"

  access_scope {
    type       = "namespace"
    namespaces = ["code-review-platform"]
  }
}
