"""Parse a repository URL into (forge, base_url, owner, name).

Accepts the forms people actually paste:
    https://github.com/owner/repo
    https://github.com/owner/repo/            (trailing slash)
    https://github.com/owner/repo.git         (clone URL)
    github.com/owner/repo                      (no scheme)
    git@github.com:owner/repo.git              (SSH)
    https://gitlab.com/group/subgroup/project  (GitLab subgroups)
    https://git.example.com/owner/repo         (self-hosted)

Known public hosts set the forge automatically. For any other (self-hosted)
host the forge can't be inferred, so the caller's dropdown selection is used as
a hint and the site root becomes the instance base_url.
"""
from __future__ import annotations

from urllib.parse import urlparse

# host -> (forge_key, base_url). Empty base_url means "use the provider default".
KNOWN_HOSTS: dict[str, tuple[str, str]] = {
    "github.com": ("github", ""),
    "gitlab.com": ("gitlab", ""),
    "bitbucket.org": ("bitbucket", ""),
    "codeberg.org": ("gitea", "https://codeberg.org"),  # public Forgejo
    "sourceforge.net": ("sourceforge", ""),
}


class RepoURLError(ValueError):
    """Raised with a user-facing message when a URL can't be parsed."""


def parse_repo_url(raw: str, forge_hint: str = "github") -> tuple[str, str, str, str]:
    raw = (raw or "").strip()
    if not raw:
        raise RepoURLError("Enter a repository URL.")

    # Extract scheme, host, and path across the accepted URL shapes.
    if raw.startswith("git@") and ":" in raw:
        userhost, _, path = raw.partition(":")
        host = userhost.split("@", 1)[-1]
        scheme = "https"
    else:
        if "://" not in raw:
            raw = "https://" + raw
        u = urlparse(raw)
        scheme = u.scheme or "https"
        host = u.netloc.split("@")[-1]  # drop any user:pass@
        path = u.path

    if not host:
        raise RepoURLError("That doesn't look like a URL with a host.")

    host_key = host.lower().split(":")[0]  # strip port for host matching
    if host_key.startswith("www."):
        host_key = host_key[4:]

    # Normalize the path into clean segments.
    p = path.strip("/")
    if p.endswith(".git"):
        p = p[:-4]
    segments = [s for s in p.split("/") if s]
    if not segments:
        raise RepoURLError("URL has no repository path — expected .../owner/repo.")

    # Determine the forge and instance base_url.
    if host_key in KNOWN_HOSTS:
        forge, base_url = KNOWN_HOSTS[host_key]
    else:
        forge = forge_hint  # self-hosted: trust the dropdown
        base_url = f"{scheme}://{host}"

    # Owner / name. GitLab allows nested groups and uses '/-/' before sub-pages.
    if forge == "sourceforge":
        # sourceforge.net/projects/<project> or /p/<project>; the project is a
        # single identifier. Store it in `name`, with a fixed pseudo-owner.
        if segments and segments[0] in ("projects", "p") and len(segments) >= 2:
            project = segments[1]
        else:
            project = segments[0]
        if not project:
            raise RepoURLError("SourceForge URL should look like .../projects/<project>.")
        owner, name = "sourceforge", project
    elif forge == "gitlab":
        if "-" in segments:
            segments = segments[: segments.index("-")]
        if len(segments) < 2:
            raise RepoURLError("GitLab URL needs at least group/project.")
        owner, name = "/".join(segments[:-1]), segments[-1]
    else:
        if len(segments) < 2:
            raise RepoURLError("URL should look like .../owner/repo.")
        owner, name = segments[0], segments[1]

    return forge, base_url, owner, name
