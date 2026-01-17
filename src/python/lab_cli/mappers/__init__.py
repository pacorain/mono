"""Resource mappers for converting service definitions to Pulumi resources."""

from .container import create_container

__all__ = ["create_container"]
