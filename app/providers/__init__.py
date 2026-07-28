"""Importing this package registers every bundled provider."""
from . import bitbucket, gitea, github, gitlab, pypi, sourceforge  # noqa: F401
from .base import (
    FetchResult,
    Provider,
    RateLimited,
    RepoRef,
    ReleaseItem,
    available_providers,
    get_provider,
    register,
)

__all__ = [
    "FetchResult",
    "Provider",
    "RateLimited",
    "RepoRef",
    "ReleaseItem",
    "available_providers",
    "get_provider",
    "register",
]
