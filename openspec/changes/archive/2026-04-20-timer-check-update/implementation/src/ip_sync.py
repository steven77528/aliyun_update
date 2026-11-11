#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import ipaddress
import json
import os
import signal
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen


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

STOP_REQUESTED = False
LOG_DIR = Path(os.getenv("LOG_DIR", "/app-data/logs"))
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "7"))
LOG_VERBOSE_STRUCTURED = os.getenv("LOG_VERBOSE_STRUCTURED", "false").strip().lower() in {"1", "true", "yes", "on"}
_LAST_LOG_CLEANUP_DATE: Optional[str] = None


def _json_log(level: str, event: str, **fields: object) -> None:
    if not LOG_VERBOSE_STRUCTURED:
        return

    ts = int(time.time())
    ts_text = dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

    def _fmt(v: object) -> str:
        if isinstance(v, str):
            # 避免多行日志破坏按行检索
            return v.replace("\n", "\\n")
        return str(v)

    detail = "，".join([f"{k}: {_fmt(v)}" for k, v in fields.items()]) if fields else ""
    if detail:
        line = f"{ts_text}-{level}: {event}，时间戳: {ts}，{detail}"
    else:
        line = f"{ts_text}-{level}: {event}，时间戳: {ts}"

    print(line, flush=True)
    _persist_log_line(line)


def _log_line(level: str, message: str) -> None:
    ts_text = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts_text}-{level}: {message}"
    print(line, flush=True)
    _persist_log_line(line)


def _persist_log_line(line: str) -> None:
    global _LAST_LOG_CLEANUP_DATE
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        today = dt.date.today()
        today_str = today.isoformat()

        # 每个进程每天只做一次清理
        if _LAST_LOG_CLEANUP_DATE != today_str:
            cutoff_ts = time.time() - LOG_RETENTION_DAYS * 86400
            for f in LOG_DIR.glob("ip-sync-*.log"):
                try:
                    if f.stat().st_mtime < cutoff_ts:
                        f.unlink(missing_ok=True)
                except Exception:
                    pass
            _LAST_LOG_CLEANUP_DATE = today_str

        log_file = LOG_DIR / f"ip-sync-{today_str}.log"
        with log_file.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")
    except Exception:
        # 日志持久化失败不应影响主流程
        pass


def _redact(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    if len(s) <= 6:
        return "***"
    return f"{s[:3]}***{s[-3:]}"


def _handle_stop_signal(signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True
    _json_log("INFO", "run.signal_received", signal=signum)


def _validate_ip(value: str) -> str:
    return str(ipaddress.ip_address(value.strip()))


@dataclass
class Target:
    security_group_id: str
    rule_identifier: str

    def key(self) -> str:
        return f"{self.security_group_id}:{self.rule_identifier}"


@dataclass
class AccountConfig:
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
    accounts: List[AccountConfig]

    @staticmethod
    def from_env() -> "AppConfig":
        run_mode = os.getenv("RUN_MODE", "once").strip().lower()
        if run_mode not in {"once", "loop"}:
            raise ValueError("RUN_MODE 仅支持 once/loop")

        check_interval_seconds = int(os.getenv("CHECK_INTERVAL_SECONDS", "3600"))
        ip_sources_raw = os.getenv("IP_SOURCES", "")
        ip_sources = [x.strip() for x in ip_sources_raw.split(",") if x.strip()] or DEFAULT_IP_SOURCES

        state_file = Path(os.getenv("STATE_FILE", "./.ip_sync_state.json")).resolve()
        alert_state_file = Path(os.getenv("ALERT_STATE_FILE", "./.ip_sync_alert_state.json")).resolve()
        lock_file = Path(os.getenv("LOCK_FILE", "./.ip_sync.lock")).resolve()
        request_timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "6"))
        retry_count = int(os.getenv("RETRY_COUNT", "2"))
        retry_backoff_seconds = float(os.getenv("RETRY_BACKOFF_SECONDS", "1.0"))
        alert_webhook_url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
        alert_rate_limit_seconds = int(os.getenv("ALERT_RATE_LIMIT_SECONDS", "300"))

        accounts = parse_accounts_from_env()
        if not accounts:
            raise ValueError("缺少账号配置：请设置 ACCOUNTS，或设置单账号必填环境变量")

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
            accounts=accounts,
        )


def parse_accounts_from_env() -> List[AccountConfig]:
    raw_accounts = os.getenv("ACCOUNTS", "").strip()
    if raw_accounts:
        try:
            data = json.loads(raw_accounts)
        except Exception as e:
            raise ValueError(f"ACCOUNTS 不是合法 JSON: {e}")

        if not isinstance(data, list) or not data:
            raise ValueError("ACCOUNTS 必须是非空数组")

        accounts: List[AccountConfig] = []
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError("ACCOUNTS 内元素必须是对象")
            name = str(item.get("name", f"account-{idx+1}"))
            region_id = str(item.get("region_id", "")).strip()
            access_key_id = str(item.get("access_key_id", "")).strip()
            access_key_secret = str(item.get("access_key_secret", "")).strip()

            targets_data = item.get("security_groups", [])
            if not isinstance(targets_data, list) or not targets_data:
                raise ValueError(f"账号 {name} 的 security_groups 必须是非空数组")

            targets: List[Target] = []
            for t in targets_data:
                if not isinstance(t, dict):
                    raise ValueError(f"账号 {name} 的 security_groups 元素必须是对象")
                sg = str(t.get("security_group_id", "")).strip()
                rule = str(t.get("rule_identifier", "")).strip()
                if not sg or not rule:
                    raise ValueError(f"账号 {name} 的 target 缺少 security_group_id/rule_identifier")
                targets.append(Target(security_group_id=sg, rule_identifier=rule))

            if not region_id or not access_key_id or not access_key_secret:
                raise ValueError(f"账号 {name} 缺少 region_id/access_key_id/access_key_secret")
            accounts.append(
                AccountConfig(
                    name=name,
                    region_id=region_id,
                    access_key_id=access_key_id,
                    access_key_secret=access_key_secret,
                    targets=targets,
                )
            )
        return accounts

    # 向后兼容单账号配置
    region_id = os.getenv("ALIYUN_REGION", "").strip()
    access_key_id = os.getenv("ACCESS_KEY_ID", "").strip()
    access_key_secret = os.getenv("ACCESS_KEY_SECRET", "").strip()

    targets = parse_targets_for_single_account()
    if not (region_id and access_key_id and access_key_secret and targets):
        return []

    return [
        AccountConfig(
            name="default",
            region_id=region_id,
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            targets=targets,
        )
    ]


def parse_targets_for_single_account() -> List[Target]:
    # 首选 SECURITY_GROUPS JSON
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
            if not sg or not rule:
                raise ValueError("SECURITY_GROUPS 元素缺少 security_group_id/rule_identifier")
            targets.append(Target(security_group_id=sg, rule_identifier=rule))
        return targets

    # 向后兼容单目标
    security_group_id = os.getenv("SECURITY_GROUP_ID", "").strip()
    rule_identifier = os.getenv("RULE_IDENTIFIER", "").strip()
    if security_group_id and rule_identifier:
        return [Target(security_group_id=security_group_id, rule_identifier=rule_identifier)]
    return []


def resolve_ip_consensus(sources: List[str], timeout_seconds: int) -> Tuple[Optional[str], str, Dict[str, str]]:
    success_ips: List[str] = []
    errors: Dict[str, str] = {}

    for source in sources:
        started = time.time()
        try:
            req = Request(source, headers={"User-Agent": "aliyun-ip-sync/2.0"})
            with urlopen(req, timeout=timeout_seconds) as resp:
                raw = resp.read().decode("utf-8", errors="ignore").strip()
            ip = _validate_ip(raw)
            success_ips.append(ip)
            duration_ms = int((time.time() - started) * 1000)
            _log_line(
                "INFO",
                f"获取公网ip地址，url: {source}，结果: {ip}，耗时: {duration_ms}ms",
            )
            _json_log(
                "INFO",
                "ip.source.result",
                source=source,
                success=True,
                resolved_ip=ip,
                fetched_at=int(time.time()),
            )
        except (URLError, TimeoutError, ValueError, OSError) as e:
            errors[source] = str(e)
            duration_ms = int((time.time() - started) * 1000)
            _log_line(
                "WARN",
                f"获取公网ip地址，url: {source}，结果: 失败({type(e).__name__})，耗时: {duration_ms}ms",
            )
            _json_log(
                "WARN",
                "ip.source.result",
                source=source,
                success=False,
                error_type=type(e).__name__,
                error=str(e),
                fetched_at=int(time.time()),
                stack=traceback.format_exc(),
            )

    if not success_ips:
        return None, "all_sources_failed", errors

    counts: Dict[str, int] = {}
    for ip in success_ips:
        counts[ip] = counts.get(ip, 0) + 1

    best_ip, best_count = max(counts.items(), key=lambda kv: kv[1])
    if best_count > len(success_ips) / 2:
        return best_ip, "majority", errors

    return None, "inconsistent", errors


def load_state(state_file: Path) -> Dict[str, object]:
    if not state_file.exists():
        return {"targets": {}}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if "targets" not in data:
                # 兼容旧格式
                last_ip = data.get("last_ip")
                if last_ip:
                    return {
                        "targets": {
                            "legacy": {
                                "last_ip": _validate_ip(str(last_ip)),
                                "updated_at": int(data.get("updated_at", int(time.time()))),
                            }
                        }
                    }
            return data
    except Exception:
        pass
    return {"targets": {}}


def save_state(state_file: Path, state: Dict[str, object]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_last_ip_for_target(state: Dict[str, object], target_key: str) -> Optional[str]:
    targets = state.get("targets", {})
    if not isinstance(targets, dict):
        return None
    item = targets.get(target_key)
    if not isinstance(item, dict):
        return None
    ip = item.get("last_ip")
    if not ip:
        return None
    try:
        return _validate_ip(str(ip))
    except Exception:
        return None


def set_last_ip_for_target(state: Dict[str, object], target_key: str, ip: str) -> None:
    targets = state.setdefault("targets", {})
    if not isinstance(targets, dict):
        state["targets"] = {}
        targets = state["targets"]
    assert isinstance(targets, dict)
    targets[target_key] = {
        "last_ip": ip,
        "updated_at": int(time.time()),
    }


def load_alert_state(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): int(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def save_alert_state(path: Path, state: Dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def send_webhook_alert(cfg: AppConfig, alert_key: str, title: str, detail: Dict[str, object]) -> None:
    if not cfg.alert_webhook_url:
        return

    now = int(time.time())
    alert_state = load_alert_state(cfg.alert_state_file)
    last = int(alert_state.get(alert_key, 0))
    if now - last < cfg.alert_rate_limit_seconds:
        _json_log("INFO", "alert.rate_limited", alert_key=alert_key)
        return

    payload = {
        "title": title,
        "ts": now,
        "detail": detail,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        cfg.alert_webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=cfg.request_timeout_seconds) as resp:
            _ = resp.read()
        alert_state[alert_key] = now
        save_alert_state(cfg.alert_state_file, alert_state)
        _json_log("INFO", "alert.sent", alert_key=alert_key)
    except Exception as e:
        _json_log("WARN", "alert.failed", alert_key=alert_key, error=str(e))


@contextlib.contextmanager
def file_lock(lock_file: Path):
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with lock_file.open("w", encoding="utf-8") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass


class AliyunRuleUpdater:
    def __init__(self, account: AccountConfig):
        self.account = account

    def update_rule_source_cidr(self, target: Target, new_ip: str) -> Tuple[bool, str]:
        try:
            from aliyunsdkcore.client import AcsClient  # type: ignore
            from aliyunsdkecs.request.v20140526.ModifySecurityGroupRuleRequest import (  # type: ignore
                ModifySecurityGroupRuleRequest,
            )
        except Exception as e:
            return False, f"sdk_import_failed:{e}"

        request = ModifySecurityGroupRuleRequest()
        request.set_SecurityGroupRuleId(target.rule_identifier)
        request.set_SourceCidrIp(f"{new_ip}/32")
        request.set_SecurityGroupId(target.security_group_id)

        client = AcsClient(self.account.access_key_id, self.account.access_key_secret, self.account.region_id)
        try:
            _ = client.do_action_with_exception(request)
            return True, "ok"
        except Exception as e:
            return False, f"api_error:{e}"


def execute_update_with_retry(
    updater: Callable[[], Tuple[bool, str]],
    retry_count: int,
    retry_backoff_seconds: float,
) -> Tuple[bool, int, str]:
    last_error = ""
    for i in range(retry_count + 1):
        ok, msg = updater()
        if ok:
            return True, i + 1, "ok"
        last_error = msg
        if i < retry_count:
            time.sleep(retry_backoff_seconds * (2**i))
    return False, retry_count + 1, last_error


def run_cycle(cfg: AppConfig) -> int:
    _log_line("INFO", "step1：获取当前公网ip")
    resolved_ip, consensus_status, source_errors = resolve_ip_consensus(
        cfg.ip_sources, cfg.request_timeout_seconds
    )
    if source_errors:
        _json_log("WARN", "ip.source.partial_error", source_errors=source_errors)

    if consensus_status == "all_sources_failed":
        _json_log("ERROR", "ip.resolve.failed", reason="all_sources_failed")
        send_webhook_alert(
            cfg,
            alert_key="ip_all_sources_failed",
            title="IP resolve failed",
            detail={"reason": "all_sources_failed", "source_errors": source_errors},
        )
        return EXIT_IP_SOURCE_FAILED
    if consensus_status == "inconsistent":
        _json_log("ERROR", "ip.resolve.inconsistent", reason="no_majority")
        send_webhook_alert(
            cfg,
            alert_key="ip_inconsistent",
            title="IP resolve inconsistent",
            detail={"reason": "no_majority", "source_errors": source_errors},
        )
        return EXIT_IP_INCONSISTENT

    assert resolved_ip is not None
    state = load_state(cfg.state_file)
    overall_failed = False

    _log_line("INFO", "step2：比较当前ip地址与之前记录的ip地址")

    for account in cfg.accounts:
        updater = AliyunRuleUpdater(account)
        for target in account.targets:
            try:
                target_key = f"{account.name}|{account.region_id}|{target.key()}"
                last_ip = get_last_ip_for_target(state, target_key)
                changed = last_ip != resolved_ip

                _json_log(
                    "INFO",
                    "target.evaluate",
                    account=account.name,
                    region=account.region_id,
                    security_group_id=target.security_group_id,
                    rule_identifier=target.rule_identifier,
                    resolved_ip=resolved_ip,
                    last_ip=last_ip,
                    changed=changed,
                    access_key_id=_redact(account.access_key_id),
                )

                _json_log(
                    "INFO",
                    "ip.compare",
                    account=account.name,
                    security_group_id=target.security_group_id,
                    rule_identifier=target.rule_identifier,
                    current_ip=resolved_ip,
                    previous_ip=last_ip,
                    changed=changed,
                )
                _log_line(
                    "INFO",
                    f"当前ip地址: {resolved_ip}，之前记录的ip地址: {last_ip}，是否发生变化: {changed}",
                )

                _log_line("INFO", "step3：更新阿里云安全组规则")

                if not changed:
                    _json_log(
                        "INFO",
                        "target.skip_update",
                        account=account.name,
                        security_group_id=target.security_group_id,
                        rule_identifier=target.rule_identifier,
                        reason="ip_unchanged",
                    )
                    _log_line("INFO", "ip地址未发生变化，跳过更新安全组规则")
                    continue

                _log_line("INFO", "ip地址发生变化，开始更新安全组规则")

                def _do_update() -> Tuple[bool, str]:
                    return updater.update_rule_source_cidr(target, resolved_ip)

                update_started = time.time()
                ok, attempts, error = execute_update_with_retry(
                    updater=_do_update,
                    retry_count=cfg.retry_count,
                    retry_backoff_seconds=cfg.retry_backoff_seconds,
                )
                update_duration_ms = int((time.time() - update_started) * 1000)
                if ok:
                    set_last_ip_for_target(state, target_key, resolved_ip)
                    _json_log(
                        "INFO",
                        "aliyun.update.success",
                        account=account.name,
                        security_group_id=target.security_group_id,
                        rule_identifier=target.rule_identifier,
                        attempts=attempts,
                        new_ip=resolved_ip,
                        updated_at=int(time.time()),
                    )
                    _log_line(
                        "INFO",
                        f"更新安全组规则，目标安全组: {target.security_group_id}，规则ID: {target.rule_identifier}，规则名称: -，更新结果: 成功，耗时: {update_duration_ms}ms",
                    )
                else:
                    overall_failed = True
                    _json_log(
                        "ERROR",
                        "aliyun.update.failed",
                        account=account.name,
                        security_group_id=target.security_group_id,
                        rule_identifier=target.rule_identifier,
                        attempts=attempts,
                        error=error,
                        updated_at=int(time.time()),
                    )
                    _log_line(
                        "ERROR",
                        f"更新安全组规则，目标安全组: {target.security_group_id}，规则ID: {target.rule_identifier}，规则名称: -，更新结果: 失败，耗时: {update_duration_ms}ms",
                    )
                    send_webhook_alert(
                        cfg,
                        alert_key=f"update_failed:{account.name}:{target.key()}",
                        title="Aliyun rule update failed",
                        detail={
                            "account": account.name,
                            "region": account.region_id,
                            "security_group_id": target.security_group_id,
                            "rule_identifier": target.rule_identifier,
                            "error": error,
                        },
                    )
            except Exception as e:
                overall_failed = True
                _json_log(
                    "ERROR",
                    "target.exception",
                    account=account.name,
                    security_group_id=target.security_group_id,
                    rule_identifier=target.rule_identifier,
                    error_type=type(e).__name__,
                    error=str(e),
                    occurred_at=int(time.time()),
                    stack=traceback.format_exc(),
                )
                _log_line(
                    "ERROR",
                    f"执行异常，异常类型: {type(e).__name__}，异常时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，异常信息: {str(e)}",
                )

    save_state(cfg.state_file, state)
    return EXIT_UPDATE_FAILED if overall_failed else EXIT_OK


def run_once(cfg: AppConfig) -> int:
    started_at = time.time()
    code = EXIT_OK
    try:
        with file_lock(cfg.lock_file):
            _log_line("INFO", "----------------------开始任务----------------------")
            _json_log(
                "INFO",
                "run.start",
                run_mode=cfg.run_mode,
                check_interval_seconds=cfg.check_interval_seconds,
                accounts=len(cfg.accounts),
                ip_sources=cfg.ip_sources,
                started_at=int(started_at),
            )
            code = run_cycle(cfg)
            return code
    except BlockingIOError:
        _json_log("WARN", "run.locked", lock_file=str(cfg.lock_file))
        code = EXIT_LOCKED
        return code
    except Exception as e:
        _json_log(
            "ERROR",
            "run.exception",
            error_type=type(e).__name__,
            error=str(e),
            occurred_at=int(time.time()),
            stack=traceback.format_exc(),
        )
        _log_line(
            "ERROR",
            f"执行异常，异常类型: {type(e).__name__}，异常时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，异常信息: {str(e)}",
        )
        code = EXIT_UPDATE_FAILED
        return code
    finally:
        ended_at = time.time()
        _json_log(
            "INFO",
            "run.complete",
            ended_at=int(ended_at),
            duration_seconds=round(ended_at - started_at, 3),
            exit_code=code,
        )
        _log_line(
            "INFO",
            f"----------------------完成任务，总耗时: {int((ended_at - started_at) * 1000)}ms----------------------",
        )


def run_loop(cfg: AppConfig) -> int:
    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)

    last_code = EXIT_OK
    while not STOP_REQUESTED:
        last_code = run_once(cfg)
        if STOP_REQUESTED:
            break
        _json_log("INFO", "run.sleep", seconds=cfg.check_interval_seconds)
        time.sleep(cfg.check_interval_seconds)

    _json_log("INFO", "run.stopped", code=last_code)
    return last_code


def main() -> int:
    parser = argparse.ArgumentParser(description="定时检查公网IP并更新阿里云安全组规则")
    parser.add_argument("--once", action="store_true", help="强制单次执行")
    parser.add_argument("--loop", action="store_true", help="强制循环执行")
    args = parser.parse_args()

    try:
        cfg = AppConfig.from_env()
    except Exception as e:
        _json_log("ERROR", "config.invalid", error=str(e))
        return EXIT_CONFIG_ERROR

    if args.once and args.loop:
        _json_log("ERROR", "cli.invalid", error="--once 与 --loop 不能同时使用")
        return EXIT_CONFIG_ERROR

    if args.once:
        cfg.run_mode = "once"
    elif args.loop:
        cfg.run_mode = "loop"

    if cfg.run_mode == "loop":
        return run_loop(cfg)
    return run_once(cfg)


if __name__ == "__main__":
    sys.exit(main())
