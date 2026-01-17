"""Template resolver for Proxmox container templates."""

import fnmatch
import urllib.request
import urllib.error
import json
import ssl
from typing import Optional

from .models import ProxmoxCredentials


class TemplateResolverError(Exception):
    """Raised when template resolution fails."""

    pass


def _create_ssl_context() -> ssl.SSLContext:
    """Create SSL context that skips certificate verification for self-signed certs."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _get_auth_header(credentials: ProxmoxCredentials) -> str:
    """Build the Authorization header for API token authentication.

    Args:
        credentials: Proxmox connection credentials (username=token_id, password=secret)

    Returns:
        Authorization header value for PVEAPIToken
    """
    # Format: PVEAPIToken=USER@REALM!TOKENID=SECRET
    return f"PVEAPIToken={credentials.username}={credentials.password}"


def list_templates(
    credentials: ProxmoxCredentials,
    node: str = "rainbow-road",
    storage: str = "local",
) -> list[str]:
    """List available container templates from Proxmox storage.

    Args:
        credentials: Proxmox connection credentials
        node: Proxmox node name
        storage: Storage name where templates are stored

    Returns:
        List of template filenames (e.g., ["alpine-3.20-default_20240908_amd64.tar.xz"])

    Raises:
        TemplateResolverError: If template listing fails
    """
    # Query storage content for vztmpl type
    url = f"{credentials.endpoint}/api2/json/nodes/{node}/storage/{storage}/content"
    url += "?content=vztmpl"

    req = urllib.request.Request(url)
    req.add_header("Authorization", _get_auth_header(credentials))

    try:
        with urllib.request.urlopen(req, context=_create_ssl_context()) as response:
            result = json.loads(response.read().decode())
            templates = []
            for item in result.get("data", []):
                # volid format: "local:vztmpl/alpine-3.20-default_20240908_amd64.tar.xz"
                volid = item.get("volid", "")
                if "/" in volid:
                    templates.append(volid.split("/")[-1])
            return sorted(templates)
    except urllib.error.URLError as e:
        raise TemplateResolverError(f"Failed to list templates: {e}") from e
    except (KeyError, json.JSONDecodeError) as e:
        raise TemplateResolverError(
            f"Unexpected response from Proxmox storage endpoint: {e}"
        ) from e


def resolve_template(
    pattern: str,
    credentials: ProxmoxCredentials,
    node: str = "rainbow-road",
    storage: str = "local",
) -> str:
    """Resolve a template pattern to an actual template file ID.

    Args:
        pattern: Glob pattern to match (e.g., "alpine-3.*")
        credentials: Proxmox connection credentials
        node: Proxmox node name
        storage: Storage name where templates are stored

    Returns:
        Full template file ID (e.g., "local:vztmpl/alpine-3.20-default_20240908_amd64.tar.xz")

    Raises:
        TemplateResolverError: If no matching template is found
    """
    templates = list_templates(credentials, node, storage)

    # Find templates matching the pattern
    matches = [t for t in templates if fnmatch.fnmatch(t.lower(), pattern.lower())]

    if not matches:
        available = ", ".join(templates[:5])
        if len(templates) > 5:
            available += f", ... ({len(templates)} total)"
        raise TemplateResolverError(
            f"No template matching pattern '{pattern}' found. "
            f"Available templates: {available or 'none'}"
        )

    # Return the latest (last alphabetically, which typically means newest version)
    selected = matches[-1]
    return f"{storage}:vztmpl/{selected}"


def resolve_template_cached(
    pattern: str,
    credentials: ProxmoxCredentials,
    node: str = "rainbow-road",
    storage: str = "local",
    _cache: Optional[dict] = None,
) -> str:
    """Resolve template with caching to avoid repeated API calls.

    Args:
        pattern: Glob pattern to match
        credentials: Proxmox connection credentials
        node: Proxmox node name
        storage: Storage name
        _cache: Internal cache dict (auto-created if None)

    Returns:
        Full template file ID
    """
    if _cache is None:
        _cache = {}

    cache_key = (node, storage)
    if cache_key not in _cache:
        _cache[cache_key] = list_templates(credentials, node, storage)

    templates = _cache[cache_key]
    matches = [t for t in templates if fnmatch.fnmatch(t.lower(), pattern.lower())]

    if not matches:
        available = ", ".join(templates[:5])
        if len(templates) > 5:
            available += f", ... ({len(templates)} total)"
        raise TemplateResolverError(
            f"No template matching pattern '{pattern}' found. "
            f"Available templates: {available or 'none'}"
        )

    selected = matches[-1]
    return f"{storage}:vztmpl/{selected}"
