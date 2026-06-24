terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.92"
    }

    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.111.0"
    }
  }

  required_version = ">= 1.15"
}

provider "proxmox" {
  insecure = true
}