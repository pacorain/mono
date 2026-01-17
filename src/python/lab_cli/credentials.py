"""Credential management via 1Password CLI and config.yaml."""

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .models import ProxmoxCredentials

# Path to config.yaml
CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "homelab" / "config.yaml"


class CredentialsError(Exception):
    """Raised when credential retrieval fails."""

    pass


@dataclass
class AWSCredentials:
    """AWS credentials for S3 backend access."""

    access_key_id: str
    secret_access_key: str


@dataclass
class PulumiConfig:
    """Pulumi backend configuration."""

    backend: str
    aws: AWSCredentials


@lru_cache
def _load_config() -> dict:
    """Load and cache config.yaml.

    Returns:
        Parsed config dictionary

    Raises:
        CredentialsError: If config file cannot be loaded
    """
    if not CONFIG_PATH.exists():
        raise CredentialsError(f"Config file not found at {CONFIG_PATH}")

    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise CredentialsError(f"Invalid YAML in {CONFIG_PATH}: {e}") from e


def _op_read(reference: str) -> str:
    """Execute 'op read' to fetch a secret from 1Password.

    Args:
        reference: 1Password secret reference (e.g., "op://vault/item/field")

    Returns:
        The secret value

    Raises:
        CredentialsError: If the op command fails or is not found
    """
    try:
        result = subprocess.run(
            ["op", "read", reference],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise CredentialsError(
            f"Failed to read 1Password reference '{reference}': {e.stderr}"
        ) from e
    except FileNotFoundError:
        raise CredentialsError(
            "1Password CLI (op) not found. Please install it: "
            "https://developer.1password.com/docs/cli/get-started/"
        ) from None


def _resolve_value(value: str) -> str:
    """Resolve a value, fetching from 1Password if it's an op:// reference.

    Args:
        value: Either a literal value or an op:// reference

    Returns:
        The resolved value
    """
    if value.startswith("op://"):
        return _op_read(value)
    return value


def get_proxmox_credentials() -> ProxmoxCredentials:
    """Retrieve Proxmox credentials from config.yaml and 1Password.

    Returns:
        ProxmoxCredentials with endpoint, username, and password

    Raises:
        CredentialsError: If credentials cannot be retrieved
    """
    config = _load_config()
    proxmox_config = config.get("proxmox", {})

    host = _resolve_value(proxmox_config.get("host", ""))
    api_token = _resolve_value(proxmox_config.get("api_token", ""))

    # The api_token from 1Password contains "user@realm!tokenid=secret"
    # We need to parse this for the provider
    # For now, assume it's in the format needed by the provider
    # If it's a full token, extract user and token parts
    if "!" in api_token and "=" in api_token:
        # Format: user@realm!tokenid=secret
        user_part, token_part = api_token.split("!", 1)
        token_id, token_secret = token_part.split("=", 1)
        return ProxmoxCredentials(
            endpoint=f"https://{host}:8006" if not host.startswith("http") else host,
            username=f"{user_part}!{token_id}",
            password=token_secret,
        )
    
    elif "api_token_id" in proxmox_config:
        # Separate api_token_id and api_token (secret)
        api_token_id = _resolve_value(proxmox_config.get("api_token_id", ""))
        return ProxmoxCredentials(
            endpoint=f"https://{host}:8006" if not host.startswith("http") else host,
            username=api_token_id,
            password=api_token,
        )

    # Fallback: treat api_token as password with separate username
    return ProxmoxCredentials(
        endpoint=f"https://{host}:8006" if not host.startswith("http") else host,
        username=proxmox_config.get("username", "root@pam"),
        password=api_token,
    )


def get_pulumi_config() -> PulumiConfig:
    """Retrieve Pulumi configuration from config.yaml and 1Password.

    Returns:
        PulumiConfig with backend URL and AWS credentials

    Raises:
        CredentialsError: If configuration cannot be retrieved
    """
    config = _load_config()
    pulumi_config = config.get("pulumi", {})

    backend = _resolve_value(pulumi_config.get("backend", ""))
    access_key_id = _resolve_value(pulumi_config.get("aws_access_key_id", ""))
    secret_access_key = _resolve_value(pulumi_config.get("aws_secret_access_key", ""))

    return PulumiConfig(
        backend=backend,
        aws=AWSCredentials(
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
        ),
    )


def get_ssh_public_key() -> str:
    """Retrieve SSH public key from config.yaml and 1Password.

    Returns:
        SSH public key string

    Raises:
        CredentialsError: If key cannot be retrieved
    """
    config = _load_config()
    secrets = config.get("secrets", {})
    return _resolve_value(secrets.get("ssh_public_key", ""))
