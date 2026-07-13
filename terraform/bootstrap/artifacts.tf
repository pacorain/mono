# Artifacts bucket for CI-built deployables (currently: luigi DNS config).
#
# Deliberately separate from the state bucket: the node that consumes these
# artifacts holds a read-only key for this bucket, and state files contain
# secrets it must never be able to reach.

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "artifacts" {
  bucket = var.artifacts_bucket_name
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expire-old-dns-builds"
    status = "Enabled"
    filter {
      prefix = "lab/luigi/dns/builds/"
    }
    expiration {
      days = 30
    }
  }

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# ==========
# DNS publish role
#
# Assumed by the luigi-dns workflow's publish job. Scoped to pushes on main
# (not the production environment) so the scheduled blocklist refresh never
# waits on a manual approval.
# ==========

data "aws_iam_policy_document" "dns_publish_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "dns_publish" {
  name               = "github-actions-luigi-dns-publish"
  assume_role_policy = data.aws_iam_policy_document.dns_publish_assume.json
}

data "aws_iam_policy_document" "dns_publish_permissions" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/lab/luigi/dns/*"]
  }
}

resource "aws_iam_role_policy" "dns_publish" {
  name   = "luigi-dns-publish"
  role   = aws_iam_role.dns_publish.id
  policy = sensitive(data.aws_iam_policy_document.dns_publish_permissions.json)
}

output "dns_publish_role_arn" {
  description = "role-to-assume for the luigi-dns publish job (set as repo var DNS_PUBLISH_ROLE_ARN)."
  value       = aws_iam_role.dns_publish.arn
}
