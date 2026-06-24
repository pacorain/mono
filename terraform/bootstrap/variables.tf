variable "bucket_name" {
  type      = string
  sensitive = true
}

variable "github_repo" {
  type        = string
  description = "owner/repo allowed to assume the GitHub Actions role, e.g. pacorain/mono"
  default     = "pacorain/mono"
}

variable "github_environment" {
  type        = string
  description = "GitHub Environment that gates terraform apply (add required reviewers to it in repo settings)"
  default     = "production"
}