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
    key = "lab/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "proxmox" {
  insecure = true
}