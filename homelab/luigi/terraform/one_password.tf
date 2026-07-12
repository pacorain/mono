data "onepassword_item" "services_ssh" {
  vault = "yu7fihprz6dmby76gpkpsh7rdy"
  uuid  = "32vl6nu353ofade3fr3d7cre5e"
}

locals {
  services_ssh_key = sensitive(data.onepassword_item.services_ssh.public_key)
}