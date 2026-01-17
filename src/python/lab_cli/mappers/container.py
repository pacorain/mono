"""Mapper for Proxmox container resources."""

import pulumi
import pulumi_proxmoxve as proxmox

from ..models import ProxmoxCredentials, Resource
from ..service_loader import parse_size_to_gb, parse_size_to_mb
from ..template_resolver import resolve_template

# Default configuration
DEFAULT_NODE = "rainbow-road"
DEFAULT_DATASTORE = "local-lvm"
DEFAULT_BRIDGE = "vmbr0"
DEFAULT_STORAGE = "local"


def create_container(
    resource: Resource,
    provider: proxmox.Provider,
    credentials: ProxmoxCredentials,
    node_name: str = DEFAULT_NODE,
) -> proxmox.ct.Container:
    """Create a Pulumi proxmoxve Container resource from a service Resource.

    Args:
        resource: Parsed resource definition from service.yaml
        provider: Proxmox provider instance
        credentials: Proxmox credentials for template resolution
        node_name: Proxmox node to deploy to

    Returns:
        Pulumi Container resource
    """
    props = resource.properties

    # Resolve template pattern to actual template file ID
    template_file_id = resolve_template(
        props.template.name,
        credentials,
        node=node_name,
        storage=DEFAULT_STORAGE,
    )

    # Parse disk size (default 4GB)
    rootfs_size = 4
    if "rootfs" in props.disks:
        rootfs_size = parse_size_to_gb(props.disks["rootfs"].size)

    # Parse memory
    memory_mb = parse_size_to_mb(props.memory.size)
    swap_mb = parse_size_to_mb(props.memory.swap)

    # Build network interfaces
    network_interfaces = _build_network_interfaces(props.network_interfaces)

    # Build initialization config (hostname, IP addresses)
    initialization = _build_initialization(props)

    # Create the container resource
    container = proxmox.ct.Container(
        resource.id,
        node_name=node_name,
        # Operating system template
        operating_system=proxmox.ct.ContainerOperatingSystemArgs(
            template_file_id=template_file_id,
            type="unmanaged",  # Let Proxmox detect OS type
        ),
        # CPU configuration
        cpu=proxmox.ct.ContainerCpuArgs(
            cores=props.cpu.cores,
        ),
        # Memory configuration
        memory=proxmox.ct.ContainerMemoryArgs(
            dedicated=memory_mb,
            swap=swap_mb,
        ),
        # Disk configuration
        disk=proxmox.ct.ContainerDiskArgs(
            datastore_id=DEFAULT_DATASTORE,
            size=rootfs_size,
        ),
        # Network interfaces
        network_interfaces=network_interfaces,
        # Initialization (hostname, IP config)
        initialization=initialization,
        # Resource pool (if specified)
        pool_id=props.resource_pool,
        # Start container after creation
        started=True,
        # Unprivileged container (safer default)
        unprivileged=True,
        # Use the explicit provider
        opts=pulumi.ResourceOptions(provider=provider),
    )

    return container


def _build_network_interfaces(
    interfaces: dict,
) -> list[proxmox.ct.ContainerNetworkInterfaceArgs]:
    """Build Pulumi network interface arguments.

    Args:
        interfaces: Dict of interface name -> NetworkInterface

    Returns:
        List of ContainerNetworkInterfaceArgs
    """
    result = []

    for iface_name, iface in interfaces.items():
        result.append(
            proxmox.ct.ContainerNetworkInterfaceArgs(
                name=iface_name,
                bridge=DEFAULT_BRIDGE,
            )
        )

    return result


def _build_initialization(props) -> proxmox.ct.ContainerInitializationArgs:
    """Build container initialization (cloud-init style) configuration.

    Args:
        props: ContainerProperties from service definition

    Returns:
        ContainerInitializationArgs with hostname and IP configs
    """
    ip_configs = []

    # Build IP configs for each network interface
    for iface_name, iface in props.network_interfaces.items():
        ipv4_args = None
        ipv6_args = None

        if iface.ipv4:
            ipv4_args = proxmox.ct.ContainerInitializationIpConfigIpv4Args(
                address=iface.ipv4.address,
                gateway=iface.ipv4.gateway,
            )

        if iface.ipv6:
            ipv6_args = proxmox.ct.ContainerInitializationIpConfigIpv6Args(
                address=iface.ipv6.address,
                gateway=iface.ipv6.gateway,
            )

        ip_configs.append(
            proxmox.ct.ContainerInitializationIpConfigArgs(
                ipv4=ipv4_args,
                ipv6=ipv6_args,
            )
        )

    return proxmox.ct.ContainerInitializationArgs(
        hostname=props.hostname,
        ip_configs=ip_configs if ip_configs else None,
    )
