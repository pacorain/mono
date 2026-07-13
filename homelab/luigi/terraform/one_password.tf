data "onepassword_item" "services_ssh" {
  vault = "yu7fihprz6dmby76gpkpsh7rdy"
  uuid  = "32vl6nu353ofade3fr3d7cre5e"
}

locals {
  services_ssh_key = sensitive(data.onepassword_item.services_ssh.public_key)
}

# Bearer token for luigi's dns-sync webhook. The bootstrap provisioner
# installs it on the node; CI reads it via `op` to trigger a sync after
# publishing. Alphanumeric only: it's embedded in JSON and an HTTP header.
resource "onepassword_item" "luigi_dns_webhook_token" {
  vault    = "adcbsm44sq5jkjf5hh7jmhdtg4"
  title    = "luigi-dns-webhook-token"
  category = "password"
  tags     = ["terraform"]
  password_recipe {
    digits  = true
    symbols = false
    length  = 32
  }
}