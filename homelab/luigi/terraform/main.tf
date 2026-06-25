resource "proxmox_virtual_environment_container" "luigi" {
  description = "DNS Server for Homelab"

  pool_id   = local.pool
  node_name = "rainbow-road"

  unprivileged = true

  initialization {
    hostname = "luigi"
    ip_config {
      ipv4 {
        address = "10.11.0.67/22"
        gateway = "10.11.0.1"
      }
    }
    user_account {
      keys     = [local.services_ssh_key]
      password = resource.onepassword_item.luigi_root_password.password
    }
  }

  disk {
    datastore_id = "local-lvm"
    size         = 8
  }

  console {
    type = "shell"
  }

  cpu {
    cores = 1
  }

  operating_system {
    template_file_id = proxmox_download_file.alpine_template.id
    type             = "alpine"
  }

}

resource "proxmox_download_file" "alpine_template" {
  content_type = "vztmpl"
  datastore_id = "local"
  node_name    = "rainbow-road"
  url          = "https://dl-cdn.alpinelinux.org/alpine/v3.22/releases/x86_64/alpine-3.22-default_20250617_amd64.tar.xz" # Will be managed by import for now
}

resource "onepassword_item" "luigi_root_password" {
  vault    = "adcbsm44sq5jkjf5hh7jmhdtg4"
  title    = "luigi-root-password"
  category = "password"
  tags     = ["root", "terraform"]
  password_recipe {
    digits  = true
    symbols = true
    length  = 16
  }
}