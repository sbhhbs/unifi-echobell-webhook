from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlparse


ECHOBELL_DIRECT_BASE_URL = "https://hook.echobell.one/d/"
ALLOWED_NOTIFICATION_TYPES = {"active", "time-sensitive", "calling"}


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    db_path: str
    echobell_direct_key: str
    echobell_base_url: str
    notification_type: str
    external_link: str
    echobell_timeout_seconds: float
    webhook_secret: str
    max_body_bytes: int
    unifi_host: str
    unifi_api_key: str
    unifi_site: str
    unifi_verify_ssl: bool
    unifi_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Config":
        config = cls(
            host=os.environ.get("HOST", "0.0.0.0"),
            port=_env_int("PORT", 8080),
            db_path=os.environ.get("DB_PATH", "/data/unifi-webhook.sqlite3"),
            echobell_direct_key=os.environ.get("ECHOBELL_DIRECT_KEY", "").strip(),
            echobell_base_url=os.environ.get("ECHOBELL_DIRECT_BASE_URL", ECHOBELL_DIRECT_BASE_URL).strip(),
            notification_type=os.environ.get("ECHOBELL_NOTIFICATION_TYPE", "time-sensitive").strip(),
            external_link=os.environ.get("ECHOBELL_EXTERNAL_LINK", "").strip(),
            echobell_timeout_seconds=_env_float("ECHOBELL_TIMEOUT_SECONDS", 5.0),
            webhook_secret=os.environ.get("WEBHOOK_SECRET", ""),
            max_body_bytes=_env_int("MAX_BODY_BYTES", 1_048_576),
            unifi_host=os.environ.get("UNIFI_HOST", "").strip(),
            unifi_api_key=os.environ.get("UNIFI_API_KEY", "").strip(),
            unifi_site=os.environ.get("UNIFI_SITE", "default").strip(),
            unifi_verify_ssl=_env_bool("UNIFI_VERIFY_SSL", True),
            unifi_timeout_seconds=_env_float("UNIFI_TIMEOUT_SECONDS", 15.0),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        if not self.db_path:
            raise ValueError("DB_PATH must not be empty")
        if not self.echobell_direct_key:
            raise ValueError("ECHOBELL_DIRECT_KEY is required")
        parsed_base_url = urlparse(self.echobell_base_url)
        if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
            raise ValueError("ECHOBELL_DIRECT_BASE_URL must be an http or https URL")
        if self.notification_type not in ALLOWED_NOTIFICATION_TYPES:
            choices = ", ".join(sorted(ALLOWED_NOTIFICATION_TYPES))
            raise ValueError(f"ECHOBELL_NOTIFICATION_TYPE must be one of: {choices}")
        if self.echobell_timeout_seconds <= 0:
            raise ValueError("ECHOBELL_TIMEOUT_SECONDS must be greater than zero")
        if self.max_body_bytes <= 0:
            raise ValueError("MAX_BODY_BYTES must be greater than zero")
        if bool(self.unifi_host) != bool(self.unifi_api_key):
            raise ValueError("UNIFI_HOST and UNIFI_API_KEY must be configured together")
        if self.unifi_host:
            raw_host = self.unifi_host if "://" in self.unifi_host else f"https://{self.unifi_host}"
            parsed_host = urlparse(raw_host)
            if parsed_host.scheme not in {"http", "https"} or not parsed_host.netloc:
                raise ValueError("UNIFI_HOST must be an http or https URL or hostname")
        if not self.unifi_site:
            raise ValueError("UNIFI_SITE must not be empty")
        if self.unifi_timeout_seconds <= 0:
            raise ValueError("UNIFI_TIMEOUT_SECONDS must be greater than zero")


def _env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _env_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")
