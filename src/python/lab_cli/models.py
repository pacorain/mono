"""Data models for lab_cli."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProxmoxCredentials:
    """Credentials for connecting to Proxmox API."""

    endpoint: str
    username: str
    password: str


@dataclass
class IPv4Config:
    """IPv4 network configuration."""

    address: str  # e.g., "10.11.1.2/22"
    gateway: str  # e.g., "10.11.0.1"


@dataclass
class IPv6Config:
    """IPv6 network configuration."""

    address: str  # e.g., "fd00:11:1::2/64"
    gateway: str  # e.g., "fd00:11::1"


@dataclass
class NetworkInterface:
    """Network interface configuration."""

    name: str  # e.g., "eth0"
    ipv4: Optional[IPv4Config] = None
    ipv6: Optional[IPv6Config] = None


@dataclass
class DiskConfig:
    """Disk configuration."""

    size: str  # e.g., "4G"


@dataclass
class CpuConfig:
    """CPU configuration."""

    cores: int = 1


@dataclass
class MemoryConfig:
    """Memory configuration."""

    size: str = "512M"  # e.g., "512M"
    swap: str = "0M"


@dataclass
class TemplateConfig:
    """Container template configuration."""

    name: str  # Pattern like "alpine-3.*"


@dataclass
class ContainerProperties:
    """Properties for a Proxmox container."""

    hostname: str
    template: TemplateConfig
    resource_pool: Optional[str] = None
    disks: dict[str, DiskConfig] = field(default_factory=dict)
    cpu: CpuConfig = field(default_factory=CpuConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    network_interfaces: dict[str, NetworkInterface] = field(default_factory=dict)


@dataclass
class Resource:
    """A resource definition from service.yaml."""

    id: str
    type: str  # e.g., "proxmox:container"
    properties: ContainerProperties


@dataclass
class Service:
    """A service definition from service.yaml."""

    id: str
    description: str
    resources: list[Resource]
