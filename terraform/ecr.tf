resource "aws_ecr_repository" "service" {
  for_each = toset(local.ecr_repository_names)

  name = each.value

  # MUTABLE to match the manifests' :latest convention as committed
  # (k8s/*/deployment.yaml). IMMUTABLE + per-commit-SHA tags is the better
  # real-world practice and the natural follow-up once CI/CD exists to
  # generate those tags.
  image_tag_mutability = "MUTABLE"

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
