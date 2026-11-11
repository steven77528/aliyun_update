from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


EXIT_OK = 0
EXIT_IP_SOURCE_FAILED = 10
EXIT_IP_INCONSISTENT = 11
EXIT_UPDATE_FAILED = 20
EXIT_CONFIG_ERROR = 30
EXIT_LOCKED = 40

DEFAULT_IP_SOURCES = [
    "https://api64.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
]


@dataclass
class Target:
    security_group_id: str
    rule_identifier: str
    rule_name: str = ""
    security_group_alias: str = ""
    provider: str = "aliyun"
    config_rule_identifier: str = ""

    def __post_init__(self) -> None:
        if not self.config_rule_identifier:
            self.config_rule_identifier = self.rule_identifier

    def key(self) -> str:
        return f"{self.provider}:{self.security_group_id}:{self.rule_identifier}"

    def state_key(self) -> str:
        return f"{self.provider}:{self.security_group_id}:{self.config_rule_identifier}"


@dataclass
class AccountConfig:
    provider: str
    name: str
    region_id: str
    access_key_id: str
    access_key_secret: str
    targets: List[Target]


@dataclass
class AppConfig:
    run_mode: str
    check_interval_seconds: int
    ip_sources: List[str]
    state_file: Path
    alert_state_file: Path
    lock_file: Path
    request_timeout_seconds: int
    retry_count: int
    retry_backoff_seconds: float
    alert_webhook_url: str
    alert_rate_limit_seconds: int
    notify_enabled: bool
    notify_smtp_host: str
    notify_smtp_port: int
    notify_smtp_username: str
    notify_smtp_password: str
    notify_smtp_use_tls: bool
    notify_email_from: str
    notify_email_to: List[str]
    notify_retry_count: int
    notify_rate_limit_seconds: int
    notify_pending_file: Path
    accounts: List[AccountConfig]

    @staticmethod
    def from_env() -> "AppConfig":
        from .config_loader import load_app_config_from_env

        return load_app_config_from_env()
