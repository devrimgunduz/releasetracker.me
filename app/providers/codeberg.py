from __future__ import annotations

from .base import register
from .gitea import GiteaProvider


@register
class CodebergProvider(GiteaProvider):
    """codeberg.org runs Forgejo, so the Gitea API applies unchanged; this just
    pins the public instance so it needs no base_url and gets its own label."""

    key = "codeberg"
    label = "Codeberg"
    default_base_url = "https://codeberg.org"
    requires_base_url = False
