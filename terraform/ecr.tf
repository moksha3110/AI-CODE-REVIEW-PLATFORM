resource "aws_ecr_repository" "service" {
  for_each = toset(local.ecr_repository_names)

  name = each.value

  # IMMUTABLE, now that CI/CD (Phase 9) generates real per-commit-SHA
  # tags - this was flagged as the natural follow-up the moment this
  # comment was first written. CD never pushes :latest; the :latest
  # placeholder still committed in k8s/*/deployment.yaml is illustrative
  # only (it was never directly appliable anyway, given the
  # <AWS_ACCOUNT_ID> placeholder alongside it) - the live cluster's image
  # references are always set imperatively, either by hand (documented in
  # k8s/README.md) or by CD's `kubectl set image`.
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

# Bounds storage cost during iterative `docker build && docker push`
# cycles without manual cleanup: untagged images (superseded by a newer
# push of the same tag) expire after a day, and only the most recent 10
# tagged images are kept per repository.
resource "aws_ecr_lifecycle_policy" "service" {
  for_each = aws_ecr_repository.service

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the last 10 tagged images"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["*"]
          countType      = "imageCountMoreThan"
          countNumber    = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}
