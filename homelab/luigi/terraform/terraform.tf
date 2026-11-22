terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.111.0"
    }

    onepassword = {
      source  = "1password/onepassword"
      version = "~> 3.3.1"
    }
  }

  required_version = ">= 1.15"

  backend "s3" {
    key    = "lab/luigi/terraform.tfstate"
    region = "us-east-1"

    # S3-native state locking (writes a .tflock object next to the state).
    # CI plan jobs run with -lock=false because the plan role is read-only;
    # apply takes the lock.
    use_lockfile = true
  }
}

provider "proxmox" {
  insecure = true
}

provider "onepassword" {} # Use environment variable

locals {
  pool = "terraform"
}
