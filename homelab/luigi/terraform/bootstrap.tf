# One-time provisioning of the DNS service on the container.
#
# Runs from the CI apply job, which is on the tailnet; 10.11.0.67 is reachable
# through the subnet router. Re-runs automatically when the container is
# recreated or the node-side scripts change, so a fresh node bootstraps itself
# and pulls the latest published DNS config with no manual steps.

locals {
  dns_scripts_dir = "${path.module}/../dns/scripts"

  luigi_dns_aws_env = sensitive(<<-EOT
    AWS_ACCESS_KEY_ID=${aws_iam_access_key.luigi_dns_reader.id}
    AWS_SECRET_ACCESS_KEY=${aws_iam_access_key.luigi_dns_reader.secret}
    AWS_REGION=us-east-1
    S3_BUCKET=${var.dns_artifacts_bucket}
    S3_PREFIX=${local.dns_s3_prefix}
    SELF_CHECK_NAME=luigi.home.arpa
  EOT
  )
}

resource "terraform_data" "luigi_dns_bootstrap" {
  triggers_replace = [
    proxmox_virtual_environment_container.luigi.id,
    filesha256("${local.dns_scripts_dir}/bootstrap.sh"),
    filesha256("${local.dns_scripts_dir}/luigi-dns-sync"),
  ]

  connection {
    type        = "ssh"
    host        = "10.11.0.67"
    user        = "root"
    private_key = sensitive(data.onepassword_item.services_ssh.private_key_openssh)
    timeout     = "2m"
  }

  provisioner "file" {
    source      = "${local.dns_scripts_dir}/luigi-dns-sync"
    destination = "/tmp/luigi-dns-sync"
  }

  provisioner "file" {
    content     = local.luigi_dns_aws_env
    destination = "/tmp/luigi-dns-aws.env"
  }

  provisioner "file" {
    content     = onepassword_item.luigi_dns_webhook_token.password
    destination = "/tmp/luigi-dns-webhook-token"
  }

  provisioner "file" {
    source      = "${local.dns_scripts_dir}/bootstrap.sh"
    destination = "/tmp/luigi-dns-bootstrap.sh"
  }

  provisioner "remote-exec" {
    inline = [
      "sh /tmp/luigi-dns-bootstrap.sh",
      "rm -f /tmp/luigi-dns-bootstrap.sh",
    ]
  }
}
