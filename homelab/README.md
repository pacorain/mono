```markdown
# Homelab Infrastructure as Code

A custom Infrastructure as Code (IaC) system for managing homelab services across a Proxmox cluster. This system uses Python to provide a simplified, declarative configuration format while leveraging Pulumi's Automation API for deployment orchestration and state management.

## Status

This README.md is aspirational, in that it describes the intended design and features of the homelab IaC system. The implementation is a work in progress, with core functionality in place but many advanced features still under development.

## Overview

This project takes a "scenic route" approach to infrastructure management, providing:

- **Simplified service definitions** - Declarative YAML configs instead of imperative Pulumi code
- **Intelligent resource placement** - Template matching and tag-based host selection
- **Scoped deployments** - Deploy individual services or entire infrastructure
- **State management** - Pulumi handles state while our layer adds homelab-specific abstractions
- **CI/CD ready** - Designed for validation, protection, and automated deployments

## Architecture

The system consists of three layers:

1. **Service Definitions** (`services/*/service.yaml`) - Declarative configuration for each service
2. **Abstraction Layer** (`src/python/homelab/`) - Python tooling that translates configs into Pulumi resources
3. **Pulumi** - Handles actual provisioning, state management, and resource lifecycle

```
┌─────────────────────────┐
│  service.yaml configs   │
└───────────┬─────────────┘
            │
            ↓
┌─────────────────────────┐
│  Python Abstraction     │
│  - Template matching    │
│  - Host selection       │
│  - Config translation   │
└───────────┬─────────────┘
            │
            ↓
┌─────────────────────────┐
│  Pulumi Automation API  │
│  - Resource creation    │
│  - State management     │
│  - Deployment execution │
└─────────────────────────┘
```

## Directory Structure

```
monorepo/
├── homelab/
│   ├── pyproject.toml              # Python project configuration
│   ├── Pulumi.yaml                 # Pulumi project definition
│   ├── Pulumi.prod.yaml            # Production stack configuration
│   │
│   ├── src/python/homelab/         # Custom IaC tooling
│   │   ├── __init__.py
│   │   ├── cli.py                  # Command-line interface
│   │   ├── deployer.py             # Main deployment orchestration
│   │   ├── resolvers.py            # Template/host matching logic
│   │   ├── generators.py           # Cloud-init and script generation
│   │   └── monitoring.py           # Health checks and auto-remediation
│   │
│   └── services/                   # Service definitions
│       ├── peach/                  # Example service: Nginx Proxy Manager
│       │   ├── service.yaml        # Service definition
│       │   ├── docker-compose.yaml # Docker Compose configuration
│       │   ├── .secrets.example.yaml  # Template for required secrets
│       │   └── docker/             # Docker build contexts
│       │       └── reverse-proxy/
│       │           ├── Dockerfile
│       │           └── reverse_proxy.py
│       │
│       └── librechat/              # Another example service
│           ├── service.yaml
│           └── docker-compose.yaml
```

## Service Definition Format

Each service is defined in a `service.yaml` file with the following structure:

```yaml
name: peach
description: Nginx Proxy Manager for internal routing

resources:
  # Build a Docker image
  - id: peach_reverse_proxy_image
    type: docker:image
    registry: local_registry  # Optional: push to registry
    name: peach_reverse_proxy
    path: ./docker/reverse-proxy  # Relative to service.yaml

  # Deploy as Proxmox LXC container
  - id: peach_container
    type: proxmox:container
    image:
      name: "*debian*"  # Pattern matching for templates
      version: ">=12"
    host:
      tags:
        - tier:1  # Deploy to any host tagged as tier:1
      resources:
        memory: 2048
        cores: 2
    docker:
      compose: true  # Install Docker and deploy docker-compose.yaml
    depends_on:
      - peach_reverse_proxy_image  # Wait for image to build
```

### Supported Resource Types

#### `docker:image`
Builds Docker images from local Dockerfiles.

```yaml
- id: my_image
  type: docker:image
  name: my_service_name
  path: ./docker/service  # Directory containing Dockerfile
  registry: optional_registry_name  # Push to registry after build
```

#### `proxmox:container`
Deploys LXC containers on Proxmox hosts.

```yaml
- id: my_container
  type: proxmox:container
  image:
    name: "*debian*"  # Template name pattern
    version: ">=12"   # Optional version constraint
  host:
    tags:
      - tier:1  # Host selection by tags
    resources:
      memory: 2048  # RAM in MB
      cores: 2
      disk: 32      # Disk in GB
  docker:
    compose: true  # Install Docker and deploy compose file
    compose_files:  # Optional: specify multiple compose files
      - docker-compose.yaml
      - docker-compose.prod.yaml
  network:
    mode: bridge  # Or 'host' for direct network access
    ports:
      - "80:80"
      - "443:443"
  depends_on:
    - other_resource_id
```

## CLI Usage

### Deploy a Single Service

```bash
# Preview changes
python -m homelab deploy peach --dry-run

# Deploy service
python -m homelab deploy peach

# Deploy with verbose output
python -m homelab deploy peach --verbose
```

### Deploy All Services

```bash
# Preview all changes
python -m homelab deploy --all --dry-run

# Deploy entire infrastructure
python -m homelab deploy --all
```

### Destroy a Service

```bash
# Preview destruction
python -m homelab destroy peach --dry-run

# Destroy service
python -m homelab destroy peach
```

### List Services

```bash
# List all discovered services
python -m homelab list

# Show service details
python -m homelab show peach
```

## How It Works: Scoped Programs

The system uses Pulumi's Automation API with dynamically scoped programs. When you deploy a specific service:

1. **CLI invokes deployer** with service name
2. **Deployer creates Pulumi program** that only includes requested service's resources
3. **Pulumi executes program** against shared state
4. **Only specified service** is updated; other services remain untouched

```python
def deploy(self, service_name: str = None):
    def pulumi_program():
        if service_name:
            # Only load this service
            config = self.load_service_config(service_name)
            self.create_service_resources(service_name, config)
        else:
            # Load all services
            for service_path in self.services_dir.glob("*/service.yaml"):
                svc_name = service_path.parent.name
                config = self.load_service_config(svc_name)
                self.create_service_resources(svc_name, config)
    
    stack = auto.create_or_select_stack(
        project_name="homelab",
        stack_name=self.stack_name,
        program=pulumi_program,
    )
    
    return stack.up(on_output=print)
```

**Key insight**: Resources not included in the current program are simply ignored by Pulumi, not deleted. This allows surgical updates to individual services within a monolithic state file.

## Intelligent Resource Resolution

### Template Matching

The system can find Proxmox templates using glob patterns:

```python
# In service.yaml
image:
  name: "*debian*"
  version: ">=12"

# Resolves to the best matching template:
# - debian-12-standard_12.2-1_amd64.tar.zst
```

### Host Selection by Tags

Hosts are selected based on Proxmox tags:

```python
# In service.yaml
host:
  tags:
    - tier:1
    - location:rack1

# Selects any Proxmox node with both tags
# Falls back gracefully if no hosts match
```

## Docker Compose Integration

Services with `docker.compose: true` automatically:

1. **Install Docker** via cloud-init script
2. **Copy docker-compose.yaml** to container
3. **Start services** with `docker-compose up -d`
4. **Configure systemd** to restart on boot

The compose file is read from the service directory (relative to `service.yaml`) and injected during container creation.

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy Homelab Services

on:
  push:
    branches: [main]
    paths:
      - 'homelab/services/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd homelab
          pip install -e .
      
      - name: Preview changes
        run: |
          cd homelab
          python -m homelab deploy --all --dry-run
        env:
          PULUMI_ACCESS_TOKEN: ${{ secrets.PULUMI_ACCESS_TOKEN }}
      
      - name: Deploy services
        if: github.ref == 'refs/heads/main'
        run: |
          cd homelab
          python -m homelab deploy --all
        env:
          PULUMI_ACCESS_TOKEN: ${{ secrets.PULUMI_ACCESS_TOKEN }}
```

### Protected Resources

Mark critical resources as protected in your service definitions:

```yaml
resources:
  - id: production_database
    type: proxmox:container
    protect: true  # Prevents accidental deletion
    # ... other config ...
```

### Deployment Guards

The deployer can enforce safety checks in CI mode:

```python
def deploy(self, service_name: str, ci_mode=False):
    if ci_mode:
        preview = stack.preview(on_output=print)
        
        # Prevent deletions without manual approval
        if preview.change_summary.get('delete', 0) > 0:
            raise Exception("Deletions require manual approval in CI")
        
        # Prevent unprotected production deployments
        if config.get('environment') == 'production' and not config.get('protect'):
            raise Exception("Production resources must be protected")
    
    return stack.up(on_output=print)
```

## Health Monitoring & Auto-Remediation

The system supports health-check-triggered redeployment:

```python
# monitoring.py
class ServiceMonitor:
    async def monitor_loop(self):
        while True:
            for service, checks in self.health_checks.items():
                if not await self.run_checks(service, checks):
                    # Tiered response
                    if checks.get('restart_first'):
                        await self.restart_service(service)
                    else:
                        await self.deployer.destroy_service(service)
                        await self.deployer.deploy_service(service)
            
            await asyncio.sleep(60)
```

Configure health checks in `service.yaml`:

```yaml
monitoring:
  health_checks:
    - type: http
      url: http://localhost:80
      interval: 60
      timeout: 5
      retries: 3
  auto_remediate: true
  restart_first: true  # Try restart before full redeploy
```

## Development Setup

```bash
# Clone repository
git clone <repo-url>
cd homelab

# Install in development mode
pip install -e .

# Run tests
pytest

# Type checking
mypy src/python/homelab

# Linting
ruff check src/python/homelab
```

## Configuration Management

### Secrets

Never commit secrets to git. Use one of these approaches:

**Option 1: Local secrets file (gitignored)**
```yaml
# services/peach/.secrets.yaml (gitignored)
database_password: "super_secret"
api_key: "another_secret"
```

**Option 2: Environment variables**
```bash
export PEACH_DB_PASSWORD="super_secret"
python -m homelab deploy peach
```

**Option 3: Pulumi ESC (recommended for CI/CD)**
```yaml
# Pulumi.prod.yaml
config:
  pulumi-esc:
    environments:
      - homelab/prod
```

### Stack Configuration

Configure Pulumi stacks in `Pulumi.<stack>.yaml`:

```yaml
# Pulumi.prod.yaml
config:
  homelab:cluster_name: production
  homelab:default_memory: 2048
  homelab:tier1_hosts:
    - pve-01
    - pve-02
```

## Extending the System

### Adding New Resource Types

1. Define resource schema in your service format
2. Add handler in `deployer.py`:

```python
def create_service_resources(self, service_name: str, config: dict):
    for resource_def in config['resources']:
        if resource_def['type'] == 'proxmox:vm':
            self.create_proxmox_vm(resource_def)
        elif resource_def['type'] == 'custom:new_type':
            self.create_new_resource_type(resource_def)
```

### Custom Resolvers

Add new resolution strategies in `resolvers.py`:

```python
class CustomHostSelector:
    def select_host(self, criteria: dict) -> str:
        # Your custom logic
        # e.g., least loaded, geographic location, etc.
        pass
```

## Troubleshooting

### Service discovery fails
- Ensure `service.yaml` exists in each service directory
- Check YAML syntax with `yamllint services/*/service.yaml`

### Template not found
- Verify template exists: `pvesh get /nodes/<node>/storage/<storage>/content --content vztmpl`
- Check pattern matching logic in service definition

### Docker Compose deployment fails
- Verify compose file syntax: `docker-compose -f services/peach/docker-compose.yaml config`
- Check container logs: `pct exec <vmid> -- journalctl -u docker`

### Pulumi state conflicts
- Check for locked state: `pulumi stack --show-urns`
- Cancel stuck operations: `pulumi cancel`
- Force unlock (last resort): `pulumi stack export | pulumi stack import`

## Philosophy

This system embraces the "scenic route" approach to homelab infrastructure:

- **Learning over convenience** - Complex setups provide educational value
- **Flexibility over opinionation** - Support multiple deployment patterns
- **Observability over magic** - Make infrastructure changes explicit and auditable
- **Iteration over perfection** - Start simple, add complexity as needs emerge

The goal is not to compete with production-grade tools like Kubernetes or Terraform, but to provide a customized system that fits the unique constraints and learning objectives of a homelab environment.

