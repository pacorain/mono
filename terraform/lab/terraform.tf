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

  backend "s3" {
    key    = "lab/terraform.tfstate"
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

locals {
  nodes = ["rainbow-road", "peach-beach", "moo-moo-meadows", "toads-turnpike", "sherbert-land"]
}