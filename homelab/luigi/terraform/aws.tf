# Read-only S3 credential for luigi itself.
#
# The node uses this to pull its DNS config from the artifacts bucket
# (see ../dns/). It can read the lab/luigi/dns/ prefix and nothing else, so
# a leaked key exposes only the DNS config.

variable "dns_artifacts_bucket" {
  type        = string
  sensitive   = true
  description = "Name of the CI artifacts bucket (created in terraform/bootstrap). Injected via TF_VAR_dns_artifacts_bucket, see .env.tpl"
}

locals {
  dns_s3_prefix = "lab/luigi/dns"
}

resource "aws_iam_user" "luigi_dns_reader" {
  name = "luigi-dns-reader"
}

data "aws_iam_policy_document" "luigi_dns_reader" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.dns_artifacts_bucket}/${local.dns_s3_prefix}/*"]
  }
}

resource "aws_iam_user_policy" "luigi_dns_reader" {
  name   = "luigi-dns-read"
  user   = aws_iam_user.luigi_dns_reader.name
  policy = sensitive(data.aws_iam_policy_document.luigi_dns_reader.json)
}

resource "aws_iam_access_key" "luigi_dns_reader" {
  user = aws_iam_user.luigi_dns_reader.name
}

# Keep the key recoverable/rotatable outside of Terraform state inspection
resource "onepassword_item" "luigi_dns_reader_key" {
  vault    = "adcbsm44sq5jkjf5hh7jmhdtg4"
  title    = "luigi-dns-reader-aws-key"
  category = "login"
  username = aws_iam_access_key.luigi_dns_reader.id
  password = aws_iam_access_key.luigi_dns_reader.secret
  tags     = ["terraform"]
}
