# Release Radar

[![CI](https://github.com/devrimgunduz/releasetracker.me/actions/workflows/ci.yml/badge.svg)](https://github.com/devrimgunduz/releasetracker.me/actions/workflows/ci.yml)

Self-hosted watchtower for software releases. Register repositories from
**GitHub, GitLab, Gitea/Forgejo, Bitbucket, SourceForge, PyPI, or a plain web
directory index**; a poller checks them on a
schedule and sends **Telegram** notifications the moment something new appears,
plus a **daily summary email**. Multiple Telegram bots are supported, so
different repositories can post to different channels.

Built for a bare-Linux host with **PostgreSQL** and **systemd**. Multi-user with
a shared workspace (everyone sees the same repositories, bots, and routes;
admins additionally manage users).

---

## How it works

Three parts, one codebase:

| Part | Process | Job |
|------|---------|-----|
| Web UI | `uvicorn app.main:app` | Login, manage repositories / bots / routes, browse releases. |
| Worker | `python -m app.worker` | Owns the schedule: polls every N minutes, emails the digest daily. |
| Database | PostgreSQL | Shared state. |

The web and worker run as **separate systemd services** on purpose — the worker
holds the schedule, so the web tier can scale to multiple workers without the
poll firing more than once.

**Providers** are pluggable. Each forge is one file in `app/providers/`
implementing `list_releases()` / `list_tags()` and registering itself. Adding a
new forge later touches nothing else. (Bitbucket has no releases API, so it is
tags-only. SourceForge has no git releases/tags at all — its file-release RSS
feed is used instead, with each top-level version folder treated as one release;
paste the project URL, e.g. `https://sourceforge.net/projects/proftpd`. PyPI has no git releases/tags either — its per-project releases RSS feed is
used, one release per published version; paste the package URL, e.g.
`https://pypi.org/project/requests`. For projects that publish tarballs on a plain web page instead of a
forge — like `https://www.haproxy.org/download/3.4/src/` — pick **Web
directory index** and paste the listing URL; each archive file becomes a
release, with the version parsed from the filename and the date from the
listing.)

**First poll seeds silently.** When you add a repository, its existing releases
are recorded as a baseline with no notifications, so you aren't flooded with its
whole history. You get notified from the next new release onward.

**Rate-limit friendly.** The poller sends conditional requests (`ETag` /
`If-None-Match`); unchanged repositories return a `304` that, when authenticated,
costs nothing against the rate limit. It also backs off a host for the rest of a
sweep once that host reports its quota is exhausted, polls least-recently-polled
repos first, and can be capped per sweep. Set `DEFAULT_GITHUB_TOKEN` — GitHub
allows only 60 requests/hour per IP unauthenticated versus 5,000 with a token.

**Secrets** (forge tokens, bot tokens) are encrypted at rest with a key derived
from `SECRET_KEY`. (`DEFAULT_GITHUB_TOKEN`, being an env var, is the exception —
it lives in `.env` as plain text, so keep it read-only.)

---

## Requirements

- Linux with systemd
- Python 3.11+
- PostgreSQL 13+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather)) per channel you want to post to
- An SMTP account for the daily email (optional — leave `SMTP_HOST` blank to disable)

---

## Install

Run as a dedicated user; these steps assume `/opt/releaseradar`.

```bash
sudo useradd --system --home /opt/releaseradar --shell /usr/sbin/nologin radar

# Copy the project into /opt/releaseradar, then give the service user ownership:
sudo chown -R radar:radar /opt/releaseradar
cd /opt/releaseradar
sudo -u radar python3 -m venv .venv
sudo -u radar .venv/bin/pip install -r requirements.txt
```

> **Note.** The app is *not* served as files by Apache — Apache only
> reverse-proxies to it on `127.0.0.1:8080` (see below). Living under `/opt`
> (outside any web `DocumentRoot`) keeps the Python source and `.env` — which
> holds `SECRET_KEY` and the DB password — off the web entirely.

### Database

```bash
sudo -u postgres psql -c "CREATE USER radar WITH PASSWORD 'choose-a-password';"
sudo -u postgres psql -c "CREATE DATABASE radar OWNER radar;"
```

### Configure

```bash
sudo -u radar cp .env.example .env
sudo -u radar python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
sudo -u radar nano .env    # set SECRET_KEY, DATABASE_URL, schedule, SMTP
```

`DATABASE_URL` uses the async driver, e.g.
`postgresql+asyncpg://radar:choose-a-password@localhost:5432/radar`.

### Migrate + create your admin

Run these straight from the project directory. The app and Alembic both read
`.env` on their own — don't wrap them in `source .env`, since the shell can
mangle passwords that contain special characters.

```bash
cd /opt/releaseradar
sudo -u radar .venv/bin/alembic upgrade head
sudo -u radar .venv/bin/python -m scripts.create_admin admin "your-password"
```

### Run under systemd

```bash
sudo cp deploy/release-radar-web.service /etc/systemd/system/
sudo cp deploy/release-radar-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now release-radar-web release-radar-worker
```

The web UI listens on `127.0.0.1:8080`. Put it behind Apache with TLS, then set
`SESSION_HTTPS_ONLY=true` in `.env` and restart the services.

### radarctl — operator helper

`radarctl` (in the project root) wraps the common tasks so you don't type venv
paths. It resolves its own location as the app directory and runs app commands as
the service user, so you can call it from anywhere:

```bash
sudo ln -s /opt/releaseradar/radarctl /usr/local/bin/radarctl   # optional, for PATH

radarctl migrate                     # alembic upgrade head
radarctl create-admin admin 's3cret' # create/promote an admin
radarctl poll                        # run one poll sweep now
radarctl summary                     # send the daily digest now
radarctl test-telegram               # send a test message down every Telegram route
radarctl config                      # print the resolved DATABASE_URL (debug .env)
radarctl status                      # systemd status of both services
radarctl logs worker                 # follow the worker journal (or: logs web)
radarctl restart                     # restart both services
```

App commands drop to the `radar` user via `sudo -u`; systemd commands use `sudo`.
Override the service user with `RADAR_USER=name radarctl …` if you didn't use `radar`.

### Apache reverse proxy

Enable the proxy modules once (Debian/Ubuntu shown — on Rocky/RHEL see the notes
below, where the modules load automatically and only `mod_ssl` needs installing):

```bash
sudo a2enmod proxy proxy_http headers ssl
sudo systemctl restart apache2   # or: httpd, on RHEL-family systems
```

Then a virtual host that proxies everything to the app and serves no files from
the directory:

```apache
<VirtualHost *:443>
    ServerName releasetracker.me
    ServerAlias www.releasetracker.me

    SSLEngine on
    SSLCertificateFile      /etc/letsencrypt/live/releasetracker.me/fullchain.pem
    SSLCertificateKeyFile   /etc/letsencrypt/live/releasetracker.me/privkey.pem

    # Proxy the whole site to the app. No DocumentRoot is served, so the
    # Python source and .env are never reachable over HTTP.
    ProxyPreserveHost On
    ProxyPass        / http://127.0.0.1:8080/
    ProxyPassReverse / http://127.0.0.1:8080/

    # Tell the app the original request was HTTPS (pairs with SESSION_HTTPS_ONLY=true).
    RequestHeader set X-Forwarded-Proto "https"

    ErrorLog  ${APACHE_LOG_DIR}/releaseradar-error.log
    CustomLog ${APACHE_LOG_DIR}/releaseradar-access.log combined
</VirtualHost>

# Redirect plain HTTP to HTTPS.
<VirtualHost *:80>
    ServerName releasetracker.me
    ServerAlias www.releasetracker.me
    Redirect permanent / https://releasetracker.me/
</VirtualHost>
```

---

## Rocky Linux / RHEL notes

Tested targets like Rocky Linux 10 differ from Debian/Ubuntu in a few places.
The Postgres unit is `postgresql-18.service` (matching the systemd units here),
and the web server service is `httpd`, not `apache2`.

**Initialize the database cluster** (PGDG packages don't auto-init):

```bash
sudo /usr/pgsql-18/bin/postgresql-18-setup initdb
sudo systemctl enable --now postgresql-18
```

**Enable password auth for the app user.** PGDG defaults to `ident`/`peer` for
local connections, but the app authenticates with a password. In
`/var/lib/pgsql/18/data/pg_hba.conf`, ensure the local/host lines use
`scram-sha-256`, e.g.:

```
host    radar    radar    127.0.0.1/32    scram-sha-256
```

Then `sudo systemctl reload postgresql-18`. (This is what causes the
`password authentication failed` error if it's still on `ident`.)

**Apache modules.** There's no `a2enmod` on RHEL — `mod_proxy`,
`mod_proxy_http`, and `mod_headers` load automatically, but `mod_ssl` ships in a
separate package:

```bash
sudo dnf install -y httpd mod_ssl
sudo systemctl enable --now httpd
```

**SELinux.** Rocky runs SELinux in enforcing mode, and httpd is not allowed to
open outbound connections by default — so the reverse proxy returns **503** until
you flip the boolean:

```bash
sudo setsebool -P httpd_can_network_connect on
```

**firewalld.** Open the public web ports (leave 8080 closed — only Apache reaches
the app, over localhost):

```bash
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --reload
```

---

## Exposing it to the internet

The app binds `127.0.0.1:8080` and should stay there — **do not** change it to
`0.0.0.0`. What faces the internet is Apache, which terminates TLS and proxies to
the app on loopback. Serving the app directly would put logins and session
cookies on the network in plaintext.

To go public with **releasetracker.me**:

1. **DNS** — add records pointing at the server's public IP:
   `releasetracker.me` (A, and AAAA if you have IPv6) and `www.releasetracker.me`.
2. **Firewall** — open 80/443 in firewalld (above) **and** in your cloud
   provider's security group.
3. **TLS certificate** — use certbot's Apache plugin. On Rocky it comes from
   EPEL; confirm the current command at certbot.eff.org, then:

   ```bash
   sudo dnf install -y certbot python3-certbot-apache
   sudo certbot --apache -d releasetracker.me -d www.releasetracker.me
   ```

   certbot writes the cert to `/etc/letsencrypt/live/releasetracker.me/`, which
   matches the vhost paths above, and sets up auto-renewal.

   > Order matters: Apache won't start if a `:443` vhost points at a cert file
   > that doesn't exist yet. Easiest path is to let `certbot --apache` obtain
   > *and* install it (it creates the SSL vhost for you). If you prefer the
   > hand-written vhost above, get the cert first with
   > `sudo certbot certonly --apache -d releasetracker.me -d www.releasetracker.me`,
   > then enable the `:443` vhost and reload.
4. **Mark the cookie Secure** — set `SESSION_HTTPS_ONLY=true` in `.env` and
   `radarctl restart`.

### Restrict who can reach it (recommended)

This is an admin tool whose only gate is the login form. If it's for you or a
small team, restrict it at the proxy so the login page isn't even visible to the
public. Add inside the `:443` VirtualHost:

```apache
<Location "/">
    Require ip 203.0.113.0/24 198.51.100.5
</Location>
```

Everyone else gets 403 before reaching the app at all.

### Brute-force protection with fail2ban

If it must be broadly reachable, back the login with fail2ban. The app logs
failed logins to the journal in a fixed shape (`failed login for '<user>' from
<ip>`), using the real client IP from Apache's `X-Forwarded-For`. Two config
files are provided:

```bash
sudo cp deploy/fail2ban-filter.conf /etc/fail2ban/filter.d/release-radar.conf
sudo cp deploy/fail2ban-jail.conf   /etc/fail2ban/jail.d/release-radar.conf
sudo systemctl enable --now fail2ban
sudo systemctl restart fail2ban
sudo fail2ban-client status release-radar     # verify the jail loaded
```

The jail reads the `release-radar-web` journal (`backend = systemd`), bans after
5 failures in 10 minutes for 1 hour, and enforces via firewalld
(`firewallcmd-rich-rules`) on Rocky. Tune `maxretry` / `findtime` / `bantime` in
the jail file. Test it by failing a login a few times from a throwaway IP and
watching `fail2ban-client status release-radar`.

> The client IP is read as the **last** hop of `X-Forwarded-For`, which is the
> address Apache actually saw — correct for a single reverse proxy. If you place
> additional proxies (a CDN, a second load balancer) in front, adjust
> `client_ip()` in `app/web/auth.py` accordingly, or an attacker could spoof the
> header to get an arbitrary address banned.

---

## Using it

1. **Telegram bots** — create a bot with @BotFather, add it to your channel as an
   admin, and register its token here. Give it a default chat/channel ID (looks
   like `-1001234567890`) or set one per route.
2. **Repositories** — paste a repository URL (e.g.
   `https://github.com/owner/repo`); the forge, owner, and name are parsed out,
   and public hosts are detected automatically. Choose whether to watch releases
   and/or tags and whether to exclude pre-releases, and tick which bots (and the
   email digest) to notify — all on the add form. A per-repo token is optional but
   recommended for private repos; for public GitHub at scale, set a shared
   `DEFAULT_GITHUB_TOKEN` instead (60 req/hr unauthenticated vs 5,000 with a token).
3. **Notifications** — a repository notifies no one until it has a route. Manage a
   repo's routing any time via the **Notifications** button on its row (check the
   bots and/or daily email), or use the **Notifications** page for per-channel chat
   overrides and pausing individual routes. Toggle **pre-releases** per repo right
   on the Repositories page.
4. **Dashboard** — one card per repository listing its releases inline, newest
   first, with a **more…** link to expand a repo's full history. Sort by *recently
   updated*, *recently added*, or *name*. An amber dot marks a release still
   awaiting Telegram delivery; a **pre** tag marks a pre-release. **Poll now**
   triggers a sweep without waiting for the schedule.

---

## Configuration reference

All settings live in `.env` (see `.env.example`). Notable ones:

- `POLL_INTERVAL_MINUTES` — how often the worker sweeps (default 30).
- `SUMMARY_HOUR` / `SUMMARY_MINUTE` / `TIMEZONE` — when the daily email goes out.
- `SMTP_*` — daily digest delivery; blank `SMTP_HOST` disables email.
- `DEFAULT_GITHUB_TOKEN` — applied to any GitHub repo without its own token.
  Strongly recommended: raises the limit from 60 to 5,000 requests/hour and makes
  conditional `304`s free. A read-only, public-repos fine-grained token is enough.
- `MAX_REPOS_PER_SWEEP` — cap repos polled per sweep (0 = all). When capped,
  least-recently-polled repos go first, rotating fairly across sweeps.
- `REQUEST_DELAY_SECONDS` — pause between requests to avoid secondary rate limits
  on large batches (default 0).

The daily email goes to `SMTP_RECIPIENTS` (a shared list). Telegram is where
per-repository, per-channel routing lives. If you later want per-recipient email
routing, the `notification_routes` table already carries `channel_type='email'`
rows per repository — extend the digest query to group by recipient.

---

## Extending: add a forge

Create `app/providers/yourforge.py`:

```python
from .base import FetchResult, Provider, RepoRef, ReleaseItem, register

@register
class YourForgeProvider(Provider):
    key = "yourforge"
    label = "Your Forge"
    default_base_url = "https://api.yourforge.com"

    def headers(self, repo: RepoRef) -> dict[str, str]:
        return {"Authorization": f"Bearer {repo.token}"} if repo.token else {}

    async def list_releases(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        # _fetch does the conditional GET: returns (json, new_etag, not_modified)
        # and raises RateLimited on an exhausted quota.
        data, new_etag, not_modified = await self._fetch(f"{self.api_base(repo)}/...", repo, etag)
        if not_modified:
            return FetchResult([], new_etag, True)
        items = [ReleaseItem(kind="release", external_key=str(r["id"]),
                             name=r["name"], tag_name=r["tag"], url=r["url"]) for r in data]
        return FetchResult(items, new_etag, False)

    async def list_tags(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        ...
```

Import it in `app/providers/__init__.py`. It now appears in the UI dropdown and
the poller uses it — conditional requests and rate-limit backoff come for free
via `_fetch`. Nothing else changes.

---

## Project layout

```
app/
  main.py            FastAPI app, middleware, routers
  config.py          env-backed settings
  models.py          SQLAlchemy models
  db.py              async engine + session
  crypto.py          token encryption at rest
  security.py        password hashing
  poller.py          detect / dedup / seed / dispatch  ← the engine
  scheduler.py       APScheduler jobs
  worker.py          standalone worker entrypoint
  providers/         github, gitlab, gitea, bitbucket, sourceforge, pypi, webindex + registry
  notifiers/         telegram (multi-bot), email digest
  web/               auth, repos, bots, routes, releases, users
  templates/         Jinja2 + HTMX
  static/            style.css
migrations/          Alembic
deploy/              systemd units + fail2ban filter/jail
scripts/             create_admin, run (one-off poll/summary)
tests/               pytest suite (URL parser, provider HTTP layer)
radarctl             operator helper (migrate, poll, logs, …)
```

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

The suite covers the repository-URL parser (`app/repo_url.py`) — every accepted
URL shape and the error cases — and the provider HTTP layer (conditional `304`
handling, ETag capture, and rate-limit detection via a mock transport). All are
pure unit tests with no database or network, so they run anywhere, including CI.

## Notes

- Run the worker as **exactly one** instance. The web service can scale.
- API endpoint shapes and rate limits change over time; verify against each
  forge's current API docs if a provider starts returning errors (the repo's
  `last error` is shown on the Repositories page).

## License

Released under the [PostgreSQL License](LICENSE) — a permissive, OSI-approved
license (functionally similar to MIT/BSD). Copyright (c) 2026, Devrim Gunduz.
