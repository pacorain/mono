# Lab CLI

A command-line tool for managing homelab infrastructure on Proxmox VE using Infrastructure as Code (IaC) with Pulumi.

## Overview

Lab CLI bridges YAML-based service definitions with Pulumi automation to provision and manage containerized environments on Proxmox VE.

## Installation

```bash
# From the monorepo root
pip install -e .

# Or using uv
uv pip install -e .
```

## Usage

```bash
# List available services
lab list

# Preview changes for a service
lab preview my-service

# Preview all services
lab preview --all

# Deploy a service
lab deploy my-service

# Deploy without confirmation prompt
lab deploy my-service -y

# Deploy all services
lab deploy --all -y

# Destroy a service
lab destroy my-service
```

## Commands

| Command | Description |
|---------|-------------|
| `lab list` | Discover and list all available services |
| `lab preview [SERVICE]` | Preview infrastructure changes without applying |
| `lab deploy [SERVICE]` | Deploy infrastructure to Proxmox VE |
| `lab destroy SERVICE` | Tear down deployed infrastructure |

Use `--all` with `preview` and `deploy` to operate on all discovered services.

## Configuration

### Homelab Config

Create `homelab/config.yaml` with your credentials (supports 1Password `op://` references):

```yaml
secrets:
  ssh_public_key: "op://vault/item/field"

proxmox:
  host: "op://vault/proxmox/host"
  api_token_id: "op://vault/proxmox/token-id"
  api_token: "op://vault/proxmox/token"

pulumi:
  backend: "op://vault/pulumi/backend"
  aws_access_key_id: "op://vault/aws/access-key-id"
  aws_secret_access_key: "op://vault/aws/secret-access-key"
```

### Service Definition

Create `homelab/service/<name>/service.yaml`:

```yaml
id: my-service
description: My container service

resources:
  - id: my-container
    type: proxmox:container
    properties:
      hostname: my-host
      template:
        name: alpine-3.*  # Glob pattern matching
      resource_pool: my-pool
      disks:
        rootfs:
          size: 4G
      cpu:
        cores: 2
      memory:
        size: 1G
        swap: 512M
      network_interfaces:
        eth0:
          ipv4:
            address: 10.0.0.2/24
            gateway: 10.0.0.1
```

## Requirements

- Python >= 3.14
- 1Password CLI (`op` command)
- Proxmox VE with API access
- AWS S3 bucket for Pulumi state

## Architecture

```
lab_cli/
├── cli.py              # Click CLI commands
├── models.py           # Data models
├── credentials.py      # 1Password integration
├── deployer.py         # Pulumi orchestration
├── service_loader.py   # YAML service parser
├── template_resolver.py # Proxmox template resolution
└── mappers/
    └── container.py    # Proxmox container mapper
```

## How It Works

1. Services are discovered from `homelab/service/*/service.yaml`
2. Credentials are resolved via 1Password CLI
3. YAML definitions are parsed into typed models
4. Template patterns are resolved against Proxmox
5. Pulumi generates and executes infrastructure changes
6. State is stored in AWS S3
