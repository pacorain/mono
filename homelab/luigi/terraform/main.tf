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

  memory {
    dedicated = 512
    swap      = 256
  }

  operating_system {
    # TODO: Make this an imported resource
    template_file_id = "local:vztmpl/alpine-3.22-default_20250617_amd64.tar.xz"
    type             = "alpine"
  }

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