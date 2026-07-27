"""Importing this package registers every bundled provider."""
from . import bitbucket, gitea, github, gitlab  # noqa: F401
from .base import (
    Provider,
    RepoRef,
    ReleaseItem,
    available_providers,
    get_provider,
    register,
)

__all__ = [
    "Provider",
    "RepoRef",
    "ReleaseItem",
    "available_providers",
    "get_provider",
    "register",
]
