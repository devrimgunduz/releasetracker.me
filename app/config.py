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

    @property
    def recipient_list(self) -> list[str]:
        return [addr.strip() for addr in self.smtp_recipients.split(",") if addr.strip()]

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.recipient_list)


@lru_cache
def get_settings() -> Settings:
    return Settings()
