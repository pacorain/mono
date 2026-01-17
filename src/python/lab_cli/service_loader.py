"""Service definition loader for YAML files."""

from pathlib import Path

import yaml

from .models import (
    ContainerProperties,
    CpuConfig,
    DiskConfig,
    IPv4Config,
    IPv6Config,
    MemoryConfig,
    NetworkInterface,
    Resource,
    Service,
    TemplateConfig,
)

# Base path for service definitions
SERVICES_BASE_PATH = Path(__file__).parent.parent.parent.parent / "homelab" / "service"


class ServiceNotFoundError(Exception):
    """Raised when a service cannot be found."""

    pass


class ServiceParseError(Exception):
    """Raised when a service.yaml is malformed."""

    pass


def discover_services() -> list[str]:
    """Return list of available service names.

    Returns:
        Sorted list of service directory names that contain service.yaml
    """
    services = []
    if not SERVICES_BASE_PATH.exists():
        return services

    for service_dir in SERVICES_BASE_PATH.iterdir():
        if service_dir.is_dir() and (service_dir / "service.yaml").exists():
            services.append(service_dir.name)
    return sorted(services)


def get_service_path(service_name: str) -> Path:
    """Get the path to a service's service.yaml file.

    Args:
        service_name: Name of the service directory

    Returns:
        Path to service.yaml

    Raises:
        ServiceNotFoundError: If service directory or service.yaml doesn't exist
    """
    path = SERVICES_BASE_PATH / service_name / "service.yaml"
    if not path.exists():
        raise ServiceNotFoundError(f"Service '{service_name}' not found at {path}")
    return path


def parse_size_to_gb(size_str: str) -> int:
    """Convert size string (e.g., '4G', '512M') to GB.

    Args:
        size_str: Size with unit suffix (G, M, T)

    Returns:
        Size in GB (minimum 1)
    """
    size_str = size_str.upper().strip()
    if size_str.endswith("G"):
        return int(size_str[:-1])
    elif size_str.endswith("M"):
        return max(1, int(size_str[:-1]) // 1024)
    elif size_str.endswith("T"):
        return int(size_str[:-1]) * 1024
    return int(size_str)


def parse_size_to_mb(size_str: str) -> int:
    """Convert size string to MB.

    Args:
        size_str: Size with unit suffix (G, M)

    Returns:
        Size in MB
    """
    size_str = size_str.upper().strip()
    if size_str.endswith("M"):
        return int(size_str[:-1])
    elif size_str.endswith("G"):
        return int(size_str[:-1]) * 1024
    return int(size_str)


def _parse_network_interface(name: str, data: dict) -> NetworkInterface:
    """Parse network interface configuration.

    Args:
        name: Interface name (e.g., "eth0")
        data: Interface configuration dict

    Returns:
        NetworkInterface dataclass
    """
    ipv4 = None
    ipv6 = None

    if "ipv4" in data:
        ipv4 = IPv4Config(
            address=data["ipv4"]["address"],
            gateway=data["ipv4"]["gateway"],
        )
    if "ipv6" in data:
        ipv6 = IPv6Config(
            address=data["ipv6"]["address"],
            gateway=data["ipv6"]["gateway"],
        )

    return NetworkInterface(name=name, ipv4=ipv4, ipv6=ipv6)


def _parse_container_properties(props: dict) -> ContainerProperties:
    """Parse container properties from YAML data.

    Args:
        props: Properties dict from service.yaml

    Returns:
        ContainerProperties dataclass
    """
    # Parse disks
    disks = {}
    if "disks" in props:
        for disk_name, disk_data in props["disks"].items():
            disks[disk_name] = DiskConfig(size=disk_data["size"])

    # Parse CPU
    cpu = CpuConfig()
    if "cpu" in props:
        cpu = CpuConfig(cores=props["cpu"].get("cores", 1))

    # Parse memory
    memory = MemoryConfig()
    if "memory" in props:
        memory = MemoryConfig(
            size=props["memory"].get("size", "512M"),
            swap=props["memory"].get("swap", "0M"),
        )

    # Parse network interfaces
    network_interfaces = {}
    if "network_interfaces" in props:
        for iface_name, iface_data in props["network_interfaces"].items():
            network_interfaces[iface_name] = _parse_network_interface(
                iface_name, iface_data
            )

    return ContainerProperties(
        hostname=props["hostname"],
        template=TemplateConfig(name=props["template"]["name"]),
        resource_pool=props.get("resource_pool"),
        disks=disks,
        cpu=cpu,
        memory=memory,
        network_interfaces=network_interfaces,
    )


def _parse_resource(resource_data: dict) -> Resource:
    """Parse a single resource definition.

    Args:
        resource_data: Resource dict from service.yaml

    Returns:
        Resource dataclass

    Raises:
        ServiceParseError: If resource type is not supported
    """
    if resource_data["type"] != "proxmox:container":
        raise ServiceParseError(
            f"Unsupported resource type: {resource_data['type']}. "
            "Only 'proxmox:container' is currently supported."
        )

    return Resource(
        id=resource_data["id"],
        type=resource_data["type"],
        properties=_parse_container_properties(resource_data["properties"]),
    )


def load_service(service_name: str) -> Service:
    """Load and parse a service definition.

    Args:
        service_name: Name of the service to load

    Returns:
        Service dataclass with parsed configuration

    Raises:
        ServiceNotFoundError: If service doesn't exist
        ServiceParseError: If YAML is invalid or malformed
    """
    path = get_service_path(service_name)

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ServiceParseError(f"Invalid YAML in {path}: {e}") from e

    resources = [_parse_resource(r) for r in data.get("resources", [])]

    return Service(
        id=data["id"],
        description=data.get("description", ""),
        resources=resources,
    )
