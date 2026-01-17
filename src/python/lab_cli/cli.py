"""Click CLI commands for lab_cli."""

import sys

import click

from .service_loader import discover_services, ServiceNotFoundError, ServiceParseError
from .deployer import preview_service, deploy_service, destroy_service
from .credentials import CredentialsError


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """Lab CLI for managing homelab infrastructure on Proxmox."""
    pass


@cli.command()
@click.argument("service", required=False)
@click.option("--all", "preview_all", is_flag=True, help="Preview all services")
def preview(service: str | None, preview_all: bool) -> None:
    """Preview changes to lab infrastructure.

    If SERVICE is provided, preview only that service.
    Use --all to preview all discovered services.
    """
    if preview_all:
        services = discover_services()
        if not services:
            click.echo("No services found.", err=True)
            sys.exit(1)

        click.echo(f"Previewing {len(services)} services...\n")
        for svc in services:
            click.echo(f"=== {svc} ===")
            try:
                result = preview_service(svc)
                _print_change_summary(result)
            except Exception as e:
                click.echo(f"Error: {e}", err=True)
            click.echo()
        return

    if not service:
        # List available services
        services = discover_services()
        if services:
            click.echo("Available services:")
            for svc in services:
                click.echo(f"  - {svc}")
            click.echo("\nRun: lab preview <service> to preview a specific service")
        else:
            click.echo("No services found in homelab/service/")
        return

    try:
        click.echo(f"Previewing service: {service}")
        result = preview_service(service)
        _print_change_summary(result)
    except ServiceNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ServiceParseError as e:
        click.echo(f"Parse error: {e}", err=True)
        sys.exit(1)
    except CredentialsError as e:
        click.echo(f"Credentials error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Preview failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("service", required=False)
@click.option("--all", "deploy_all", is_flag=True, help="Deploy all services")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def deploy(service: str | None, deploy_all: bool, yes: bool) -> None:
    """Deploy lab infrastructure to Proxmox.

    If SERVICE is provided, deploy only that service.
    Use --all to deploy all discovered services.
    """
    if deploy_all:
        services = discover_services()
        if not services:
            click.echo("No services found.", err=True)
            sys.exit(1)

        if not yes:
            click.confirm(f"Deploy {len(services)} services?", abort=True)

        for svc in services:
            click.echo(f"\n=== Deploying {svc} ===")
            try:
                result = deploy_service(svc)
                _print_deploy_result(result)
            except Exception as e:
                click.echo(f"Error deploying {svc}: {e}", err=True)
        return

    if not service:
        services = discover_services()
        if services:
            click.echo("Available services:")
            for svc in services:
                click.echo(f"  - {svc}")
            click.echo("\nRun: lab deploy <service> to deploy a specific service")
        else:
            click.echo("No services found in homelab/service/")
        return

    if not yes:
        click.confirm(f"Deploy service '{service}'?", abort=True)

    try:
        click.echo(f"Deploying service: {service}")
        result = deploy_service(service)
        _print_deploy_result(result)
    except ServiceNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ServiceParseError as e:
        click.echo(f"Parse error: {e}", err=True)
        sys.exit(1)
    except CredentialsError as e:
        click.echo(f"Credentials error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Deployment failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("service", required=False)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def destroy(service: str | None, yes: bool) -> None:
    """Destroy deployed lab infrastructure.

    If SERVICE is provided, destroy only that service.
    """
    if not service:
        services = discover_services()
        if services:
            click.echo("Available services:")
            for svc in services:
                click.echo(f"  - {svc}")
            click.echo("\nRun: lab destroy <service> to destroy a specific service")
        else:
            click.echo("No services found in homelab/service/")
        return

    if not yes:
        click.confirm(
            f"Destroy service '{service}'? This cannot be undone.", abort=True
        )

    try:
        click.echo(f"Destroying service: {service}")
        result = destroy_service(service)
        click.echo("\nDestruction complete.")
        if result.summary.result == "succeeded":
            click.echo("All resources have been removed.")
    except ServiceNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except CredentialsError as e:
        click.echo(f"Credentials error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Destruction failed: {e}", err=True)
        sys.exit(1)


@cli.command("list")
def list_services() -> None:
    """List all discovered services."""
    services = discover_services()
    if services:
        click.echo("Discovered services:")
        for svc in services:
            click.echo(f"  - {svc}")
    else:
        click.echo("No services found in homelab/service/")


def _print_change_summary(result) -> None:
    """Print a summary of changes from preview."""
    summary = result.change_summary
    if summary:
        click.echo("\nChange summary:")
        for change_type, count in summary.items():
            if count > 0:
                click.echo(f"  {change_type}: {count}")
    else:
        click.echo("No changes detected.")


def _print_deploy_result(result) -> None:
    """Print deployment result."""
    if result.outputs:
        click.echo("\nOutputs:")
        for key, value in result.outputs.items():
            click.echo(f"  {key}: {value.value}")
    else:
        click.echo("\nDeployment complete.")
