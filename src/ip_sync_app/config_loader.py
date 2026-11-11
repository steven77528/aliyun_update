from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from .log_service import set_log_retention_days
from .models import AccountConfig, AppConfig, DEFAULT_IP_SOURCES, Target


def _load_yaml(text: str) -> object:
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise ValueError(f"缺少 YAML 解析依赖，请安装 PyYAML: {e}")
    try:
        return yaml.safe_load(text)
    except Exception as e:
        raise ValueError(f"YAML 解析失败: {e}")


def _load_json_file(path: Path, label: str) -> Dict[str, Any]:
    if not path.exists():
        raise ValueError(f"{label} 文件不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"{label} JSON 解析失败: {e}")
    if not isinstance(data, dict):
        raise ValueError(f"{label} 根节点必须是对象")
    return data


def _cfg_get(cfg: Dict[str, Any], key: str, env_key: str, default: str = "") -> str:
    val = cfg.get(key)
    if val is not None:
        return str(val).strip()
    return os.getenv(env_key, default).strip()


def _parse_target_rules(
    provider: str,
    account_name: str,
    security_group_id: str,
    security_group_alias: str,
    rules: object,
) -> List[Target]:
    if not isinstance(rules, list) or not rules:
        raise ValueError(f"账号 {account_name} 的 security_group.rules 必须是非空数组")

    targets: List[Target] = []
    for rule_item in rules:
        if not isinstance(rule_item, dict):
            raise ValueError(f"账号 {account_name} 的 rules 元素必须是对象")
        rule_identifier = str(rule_item.get("rule_id") or rule_item.get("rule_identifier") or "").strip()
        rule_name = str(rule_item.get("name") or rule_item.get("alias") or "").strip()
        if not rule_identifier:
            raise ValueError(f"账号 {account_name} 的 rule 缺少 rule_id/rule_identifier")
        if not rule_name:
            raise ValueError(f"账号 {account_name} 的 rule 缺少展示名字字段(name/alias)")
        targets.append(
            Target(
                provider=provider,
                security_group_id=security_group_id,
                rule_identifier=rule_identifier,
                rule_name=rule_name,
                security_group_alias=security_group_alias,
            )
        )
    return targets


def _parse_provider_accounts(provider: str, accounts_data: object) -> List[AccountConfig]:
    if not isinstance(accounts_data, list) or not accounts_data:
        raise ValueError(f"{provider} 配置必须是非空数组")

    accounts: List[AccountConfig] = []
    for idx, item in enumerate(accounts_data):
        if not isinstance(item, dict):
            raise ValueError(f"{provider} 账号元素必须是对象")

        name = str(item.get("account") or item.get("name") or f"{provider}-account-{idx+1}").strip()
        region_id = str(item.get("region_id") or item.get("region") or os.getenv("ALIYUN_REGION", "")).strip()
        access_key_id = str(item.get("access_key_id", "")).strip()
        access_key_secret = str(item.get("access_key_secret", "")).strip()

        sgs = item.get("security_groups")
        if not isinstance(sgs, list) or not sgs:
            raise ValueError(f"账号 {name} 的 security_groups 必须是非空数组")

        targets: List[Target] = []
        for sg_item in sgs:
            if not isinstance(sg_item, dict):
                raise ValueError(f"账号 {name} 的 security_groups 元素必须是对象")
            security_group_id = str(sg_item.get("security_group_id", "")).strip()
            security_group_alias = str(sg_item.get("alias") or sg_item.get("name") or "").strip()
            if not security_group_id:
                raise ValueError(f"账号 {name} 的 security_group 缺少 security_group_id")

            rules = sg_item.get("rules")
            if isinstance(rules, list) and rules:
                targets.extend(_parse_target_rules(provider, name, security_group_id, security_group_alias, rules))
                continue

            rule_identifier = str(sg_item.get("rule_id") or sg_item.get("rule_identifier") or "").strip()
            rule_name = str(sg_item.get("name") or sg_item.get("alias") or "").strip()
            if not rule_identifier:
                raise ValueError(f"账号 {name} 的 security_group 缺少规则信息(rule_id/rule_identifier 或 rules[])")
            if not rule_name:
                raise ValueError(f"账号 {name} 的 security_group 缺少展示名字字段(name/alias)")
            targets.append(
                Target(
                    provider=provider,
                    security_group_id=security_group_id,
                    rule_identifier=rule_identifier,
                    rule_name=rule_name,
                    security_group_alias=security_group_alias,
                )
            )

        if not region_id or not access_key_id or not access_key_secret:
            raise ValueError(f"账号 {name} 缺少 region_id/access_key_id/access_key_secret")

        accounts.append(
            AccountConfig(
                provider=provider,
                name=name,
                region_id=region_id,
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                targets=targets,
            )
        )
    return accounts


def parse_accounts_from_env() -> List[AccountConfig]:
    yaml_file = os.getenv("CLOUD_CONFIG_FILE", "").strip() or os.getenv("ALIYUN_CONFIG_FILE", "").strip()
    if yaml_file:
        return parse_accounts_from_yaml_file(Path(yaml_file).expanduser())

    raw_accounts = os.getenv("ACCOUNTS", "").strip()
    if raw_accounts:
        try:
            data = json.loads(raw_accounts)
        except Exception as e:
            raise ValueError(f"ACCOUNTS 不是合法 JSON: {e}")
        return _parse_provider_accounts("aliyun", data)

    region_id = os.getenv("ALIYUN_REGION", "").strip()
    access_key_id = os.getenv("ACCESS_KEY_ID", "").strip()
    access_key_secret = os.getenv("ACCESS_KEY_SECRET", "").strip()

    targets = parse_targets_for_single_account()
    if not (region_id and access_key_id and access_key_secret and targets):
        return []

    return [
        AccountConfig(
            provider="aliyun",
            name="default",
            region_id=region_id,
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            targets=targets,
        )
    ]


def parse_accounts_from_yaml_file(path: Path) -> List[AccountConfig]:
    if not path.exists():
        raise ValueError(f"CLOUD_CONFIG_FILE/ALIYUN_CONFIG_FILE 不存在: {path}")

    data = _load_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("云厂商 YAML 配置根节点必须是对象")

    if "accounts" in data:
        return _parse_provider_accounts("aliyun", data.get("accounts"))

    accounts: List[AccountConfig] = []
    provider_found = False
    for provider in ("aliyun", "huawei"):
        provider_accounts = data.get(provider)
        if provider_accounts is None:
            continue
        provider_found = True
        accounts.extend(_parse_provider_accounts(provider, provider_accounts))

    if not provider_found:
        raise ValueError("云厂商 YAML 配置缺少 aliyun/huawei/accounts 入口")
    return accounts


def parse_targets_for_single_account() -> List[Target]:
    sg_json = os.getenv("SECURITY_GROUPS", "").strip()
    if sg_json:
        try:
            data = json.loads(sg_json)
        except Exception as e:
            raise ValueError(f"SECURITY_GROUPS 不是合法 JSON: {e}")
        if not isinstance(data, list) or not data:
            raise ValueError("SECURITY_GROUPS 必须是非空数组")
        targets: List[Target] = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("SECURITY_GROUPS 元素必须是对象")
            sg = str(item.get("security_group_id", "")).strip()
            rule = str(item.get("rule_identifier", "")).strip()
            rule_name = str(item.get("name") or item.get("alias") or "").strip()
            if not sg or not rule:
                raise ValueError("SECURITY_GROUPS 元素缺少 security_group_id/rule_identifier")
            targets.append(Target(provider="aliyun", security_group_id=sg, rule_identifier=rule, rule_name=rule_name or rule))
        return targets

    security_group_id = os.getenv("SECURITY_GROUP_ID", "").strip()
    rule_identifier = os.getenv("RULE_IDENTIFIER", "").strip()
    if security_group_id and rule_identifier:
        return [
            Target(
                provider="aliyun",
                security_group_id=security_group_id,
                rule_identifier=rule_identifier,
                rule_name=os.getenv("RULE_NAME", "").strip() or rule_identifier,
            )
        ]
    return []


def load_app_config_from_env() -> AppConfig:
    base_cfg: Dict[str, Any] = {}
    notify_cfg: Dict[str, Any] = {}

    base_cfg_file = os.getenv("BASE_CONFIG_FILE", "").strip()
    if base_cfg_file:
        base_cfg = _load_json_file(Path(base_cfg_file).expanduser(), "BASE_CONFIG_FILE")

    notify_cfg_file = os.getenv("NOTIFY_CONFIG_FILE", "").strip()
    if notify_cfg_file:
        notify_cfg = _load_json_file(Path(notify_cfg_file).expanduser(), "NOTIFY_CONFIG_FILE")

    run_mode = os.getenv("RUN_MODE", "once").strip().lower()
    if run_mode not in {"once", "loop"}:
        raise ValueError("RUN_MODE 仅支持 once/loop")

    check_interval_seconds = int(_cfg_get(base_cfg, "check_interval_seconds", "CHECK_INTERVAL_SECONDS", "3600"))

    ip_sources_val = base_cfg.get("ip_sources")
    if isinstance(ip_sources_val, list):
        ip_sources = [str(x).strip() for x in ip_sources_val if str(x).strip()]
    else:
        ip_sources_raw = _cfg_get(base_cfg, "ip_sources", "IP_SOURCES", "")
        ip_sources = [x.strip() for x in ip_sources_raw.split(",") if x.strip()]
    ip_sources = ip_sources or DEFAULT_IP_SOURCES

    log_retention_days = int(_cfg_get(base_cfg, "log_retention_days", "LOG_RETENTION_DAYS", os.getenv("LOG_RETENTION_DAYS", "7")))
    set_log_retention_days(log_retention_days)

    state_file = Path(os.getenv("STATE_FILE", "./.ip_sync_state.json")).resolve()
    alert_state_file = Path(os.getenv("ALERT_STATE_FILE", "./.ip_sync_alert_state.json")).resolve()
    lock_file = Path(os.getenv("LOCK_FILE", "./.ip_sync.lock")).resolve()
    request_timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "6"))
    retry_count = int(os.getenv("RETRY_COUNT", "2"))
    retry_backoff_seconds = float(os.getenv("RETRY_BACKOFF_SECONDS", "1.0"))
    alert_webhook_url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    alert_rate_limit_seconds = int(os.getenv("ALERT_RATE_LIMIT_SECONDS", "300"))
    notify_enabled = _cfg_get(notify_cfg, "enabled", "NOTIFY_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    notify_smtp_host = _cfg_get(notify_cfg, "smtp_host", "NOTIFY_SMTP_HOST", "")
    notify_smtp_port = int(_cfg_get(notify_cfg, "smtp_port", "NOTIFY_SMTP_PORT", "587"))
    notify_smtp_username = _cfg_get(notify_cfg, "smtp_username", "NOTIFY_SMTP_USERNAME", "")
    notify_smtp_password = _cfg_get(notify_cfg, "smtp_password", "NOTIFY_SMTP_PASSWORD", "")
    notify_smtp_use_tls = _cfg_get(notify_cfg, "smtp_use_tls", "NOTIFY_SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
    notify_email_from = _cfg_get(notify_cfg, "email_from", "NOTIFY_EMAIL_FROM", "")

    notify_email_to_val = notify_cfg.get("email_to")
    if isinstance(notify_email_to_val, list):
        notify_email_to = [str(x).strip() for x in notify_email_to_val if str(x).strip()]
    else:
        notify_email_to = [x.strip() for x in _cfg_get(notify_cfg, "email_to", "NOTIFY_EMAIL_TO", "").split(",") if x.strip()]

    notify_retry_count = int(_cfg_get(notify_cfg, "retry_count", "NOTIFY_RETRY_COUNT", "3"))
    notify_rate_limit_seconds = int(_cfg_get(notify_cfg, "rate_limit_seconds", "NOTIFY_RATE_LIMIT_SECONDS", str(alert_rate_limit_seconds)))
    notify_pending_file = Path(_cfg_get(notify_cfg, "pending_file", "NOTIFY_PENDING_FILE", "./.ip_sync_notify_pending.json")).resolve()

    accounts = parse_accounts_from_env()
    if not accounts:
        raise ValueError("缺少账号配置：请设置 CLOUD_CONFIG_FILE/ALIYUN_CONFIG_FILE/ACCOUNTS，或设置单账号必填环境变量")

    return AppConfig(
        run_mode=run_mode,
        check_interval_seconds=check_interval_seconds,
        ip_sources=ip_sources,
        state_file=state_file,
        alert_state_file=alert_state_file,
        lock_file=lock_file,
        request_timeout_seconds=request_timeout_seconds,
        retry_count=retry_count,
        retry_backoff_seconds=retry_backoff_seconds,
        alert_webhook_url=alert_webhook_url,
        alert_rate_limit_seconds=alert_rate_limit_seconds,
        notify_enabled=notify_enabled,
        notify_smtp_host=notify_smtp_host,
        notify_smtp_port=notify_smtp_port,
        notify_smtp_username=notify_smtp_username,
        notify_smtp_password=notify_smtp_password,
        notify_smtp_use_tls=notify_smtp_use_tls,
        notify_email_from=notify_email_from,
        notify_email_to=notify_email_to,
        notify_retry_count=notify_retry_count,
        notify_rate_limit_seconds=notify_rate_limit_seconds,
        notify_pending_file=notify_pending_file,
        accounts=accounts,
    )
