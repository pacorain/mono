"""Pulumi Automation API orchestration for deploying services."""

import os
from pathlib import Path
from typing import Callable

import pulumi
from pulumi import automation as auto
import pulumi_proxmoxve as proxmox

from .credentials import get_proxmox_credentials, get_pulumi_config, ProxmoxCredentials, PulumiConfig
from .service_loader import load_service, SERVICES_BASE_PATH
from .mappers.container import create_container
from .models import Service

# Pulumi project configuration
PROJECT_NAME = "lab-homelab"

# Working directory for Pulumi operations
WORK_DIR = Path(__file__).parent.parent.parent.parent / "homelab" / ".pulumi-work"


class DeployerError(Exception):
    """Raised when deployment operations fail."""

    pass


def _ensure_work_dir() -> None:
    """Ensure the Pulumi working directory exists."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)


def _create_pulumi_program(
    service: Service,
    credentials: ProxmoxCredentials,
    service_dir: Path,
) -> Callable[[], None]:
    """Create a Pulumi program function for the given service.

    Args:
        service: Parsed service definition
        credentials: Proxmox credentials
        service_dir: Service directory for accessing startup scripts

    Returns:
        A callable that defines the Pulumi infrastructure
    """

    def pulumi_program() -> None:
        # Create the Proxmox provider with API token credentials
        # Format: USER@REALM!TOKENID=SECRET
        api_token = f"{credentials.username}={credentials.password}"
        provider = proxmox.Provider(
            "proxmox-provider",
            endpoint=credentials.endpoint,
            api_token=api_token,
            insecure=True,  # Skip TLS verification for self-signed certs
        )

        # Create resources for each container in the service
        for resource in service.resources:
            if resource.type == "proxmox:container":
                container = create_container(
                    resource,
                    provider,
                    credentials,
                    service_dir=service_dir,
                )

                # Export useful outputs
                pulumi.export(f"{resource.id}_id", container.vm_id)

    return pulumi_program


def _get_or_create_stack(
    service: Service,
    proxmox_credentials: ProxmoxCredentials,
    pulumi_config: PulumiConfig,
    service_dir: Path,
) -> auto.Stack:
    """Get or create a Pulumi stack for the service.

    Args:
        service: Parsed service definition
        proxmox_credentials: Proxmox credentials
        pulumi_config: Pulumi backend and AWS configuration
        service_dir: Service directory for accessing startup scripts

    Returns:
        Pulumi Stack instance
    """
    _ensure_work_dir()

    # Create project settings with backend from config
    project_settings = auto.ProjectSettings(
        name=PROJECT_NAME,
        runtime="python",
        backend=auto.ProjectBackend(url=pulumi_config.backend),
    )

    # Build environment variables for Pulumi workspace
    env_vars = {
        # Passphrase for encrypting secrets in state
        # Can be empty string if not using encrypted secrets
        "PULUMI_CONFIG_PASSPHRASE": os.environ.get("PULUMI_CONFIG_PASSPHRASE", ""),
        # AWS credentials for S3 backend access
        "AWS_ACCESS_KEY_ID": pulumi_config.aws.access_key_id,
        "AWS_SECRET_ACCESS_KEY": pulumi_config.aws.secret_access_key,
        # Default region for S3
        "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1"),
    }

    # Create the stack with inline program
    # Each service gets its own stack for isolation
    stack = auto.create_or_select_stack(
        stack_name=service.id,
        project_name=PROJECT_NAME,
        program=_create_pulumi_program(service, proxmox_credentials, service_dir),
        opts=auto.LocalWorkspaceOptions(
            work_dir=str(WORK_DIR),
            project_settings=project_settings,
            env_vars=env_vars,
        ),
    )

    return stack


def preview_service(service_name: str, on_output: Callable[[str], None] = print) -> auto.PreviewResult:
    """Preview changes for a service without applying them.

    Args:
        service_name: Name of the service to preview
        on_output: Callback for output messages (default: print)

    Returns:
        PreviewResult containing change summary

    Raises:
        DeployerError: If preview fails
    """
    # Load service definition
    service = load_service(service_name)

    # Get service directory
    service_dir = SERVICES_BASE_PATH / service_name

    # Get credentials from 1Password via config.yaml
    proxmox_credentials = get_proxmox_credentials()
    pulumi_config = get_pulumi_config()

    # Get or create the stack
    stack = _get_or_create_stack(service, proxmox_credentials, pulumi_config, service_dir)

    # Run preview
    return stack.preview(on_output=on_output)


def deploy_service(service_name: str, on_output: Callable[[str], None] = print) -> auto.UpResult:
    """Deploy a service to Proxmox.

    Args:
        service_name: Name of the service to deploy
        on_output: Callback for output messages (default: print)

    Returns:
        UpResult containing deployment outputs

    Raises:
        DeployerError: If deployment fails
    """
    # Load service definition
    service = load_service(service_name)

    # Get service directory
    service_dir = SERVICES_BASE_PATH / service_name

    # Get credentials from 1Password via config.yaml
    proxmox_credentials = get_proxmox_credentials()
    pulumi_config = get_pulumi_config()

    # Get or create the stack
    stack = _get_or_create_stack(service, proxmox_credentials, pulumi_config, service_dir)

    # Run deployment
    return stack.up(on_output=on_output)


def destroy_service(service_name: str, on_output: Callable[[str], None] = print) -> auto.DestroyResult:
    """Destroy a deployed service.

    Args:
        service_name: Name of the service to destroy
        on_output: Callback for output messages (default: print)

    Returns:
        DestroyResult from the operation

    Raises:
        DeployerError: If destruction fails
    """
    # Load service definition
    service = load_service(service_name)

    # Get service directory
    service_dir = SERVICES_BASE_PATH / service_name

    # Get credentials from 1Password via config.yaml
    proxmox_credentials = get_proxmox_credentials()
    pulumi_config = get_pulumi_config()

    # Get or create the stack
    stack = _get_or_create_stack(service, proxmox_credentials, pulumi_config, service_dir)

    # Run destroy
    return stack.destroy(on_output=on_output)
