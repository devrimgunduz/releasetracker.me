import hashlib
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = Field(min_length=16)
    database_url: str

    poll_interval_minutes: int = Field(default=30, ge=1)
    summary_hour: int = Field(default=8, ge=0, le=23)
    summary_minute: int = Field(default=0, ge=0, le=59)
    timezone: str = "UTC"

    # Applied to any GitHub repo without its own token. Unauthenticated GitHub is
    # 60 requests/hour per IP; a token raises that to 5,000/hour.
    default_github_token: str = ""
    # Safety valves for large repo counts (0 = no cap). Least-recently-polled
    # repositories are polled first, so a cap rotates fairly across sweeps.
    max_repos_per_sweep: int = Field(default=0, ge=0)
    request_delay_seconds: float = Field(default=0.0, ge=0.0)

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from: str = "release-radar@releasetracker.me"
    smtp_recipients: str = ""

    session_https_only: bool = False

    # Comma-separated IPs of reverse proxies allowed to set X-Forwarded-For.
    # The client IP (for login logging / rate limiting / fail2ban) is only read
    # from XFF when the direct socket peer is one of these; otherwise the peer
    # address is used, so a client reaching the app directly can't spoof the
    # header. Default is the local Apache proxy the README describes.
    trusted_proxy_ips: str = "127.0.0.1,::1"

    @property
    def trusted_proxies(self) -> set[str]:
        return {ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()}

    @property
    def recipient_list(self) -> list[str]:
        return [addr.strip() for addr in self.smtp_recipients.split(",") if addr.strip()]

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.recipient_list)

    @property
    def session_signing_key(self) -> str:
        """A key derived from SECRET_KEY, distinct from the one crypto.py uses
        to encrypt stored tokens (key separation — see security review: reusing
        one secret for two different cryptographic purposes widens the blast
        radius of any future weakness in either one). Changing this on upgrade
        invalidates existing sessions, which is expected and harmless; it does
        NOT affect already-encrypted tokens, which still derive from
        SECRET_KEY directly in crypto.py."""
        return hashlib.sha256(f"{self.secret_key}|session-signing".encode()).hexdigest()


@lru_cache
def get_settings() -> Settings:
    return Settings()
