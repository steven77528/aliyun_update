from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import signal
import time
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]
    import msvcrt

from .ip_service import resolve_ip_consensus
from .log_service import (
    _handle_stop_signal,
    _json_log,
    _log_line,
    _redact,
    is_stop_requested,
    reset_stop_requested,
)
from .models import (
    EXIT_CONFIG_ERROR,
    EXIT_IP_INCONSISTENT,
    EXIT_IP_SOURCE_FAILED,
    EXIT_LOCKED,
    EXIT_OK,
    EXIT_UPDATE_FAILED,
    AccountConfig,
    AppConfig,
    Target,
)
from .notification_service import dispatch_summary_notification, send_webhook_alert
from .sg_service import CloudRuleUpdater, execute_update_with_retry
from .state_service import (
    _load_notify_pending,
    get_last_ip_for_target,
    get_rule_identifier_for_target,
    load_state,
    save_state,
    set_last_ip_for_target,
)


@contextlib.contextmanager
def file_lock(lock_file: Path):
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with lock_file.open("a+", encoding="utf-8") as fh:
        fh.seek(0)
        if fh.tell() == 0 and fh.read(1) == "":
            fh.write("0")
            fh.flush()
        try:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                fh.seek(0)
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as e:
                    raise BlockingIOError(*e.args) from e
            yield
        finally:
            try:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                else:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass


def _build_notify_item(
    account: AccountConfig,
    target: Target,
    last_ip: str | None,
    resolved_ip: str,
    result: str,
    error_summary: str | None = None,
) -> Dict[str, object]:
    item: Dict[str, object] = {
        "occurred_at": int(time.time()),
        "provider": account.provider,
        "account": account.name,
        "region": account.region_id,
        "security_group_alias": target.security_group_alias,
        "security_group_id": target.security_group_id,
        "rule_identifier": target.rule_identifier,
        "rule_name": target.rule_name or target.rule_identifier,
        "previous_ip": last_ip,
        "current_ip": resolved_ip,
        "reason": "public_ip_changed",
        "result": result,
    }
    if error_summary:
        item["error_summary"] = error_summary
    return item


def run_cycle(cfg: AppConfig) -> int:
    _log_line("INFO", "step1：获取当前公网ip")
    resolved_ip, consensus_status, source_errors = resolve_ip_consensus(cfg.ip_sources, cfg.request_timeout_seconds)
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
    notify_items: List[Dict[str, object]] = []
    skipped_notify_items: List[Dict[str, object]] = []
    updated_count = 0
    step3_index = 0

    _log_line("INFO", "step2：比较当前ip地址与之前记录的ip地址")
    _log_line("INFO", "step3：更新安全组规则")

    for account in cfg.accounts:
        updater = CloudRuleUpdater(account)
        for target in account.targets:
            step3_index += 1
            try:
                target_key = f"{account.provider}|{account.name}|{account.region_id}|{target.state_key()}"
                if account.provider == "huawei":
                    persisted_rule_identifier = get_rule_identifier_for_target(state, target_key)
                    if persisted_rule_identifier:
                        target.rule_identifier = persisted_rule_identifier
                last_ip = get_last_ip_for_target(state, target_key)
                changed = last_ip != resolved_ip

                security_group_name = target.security_group_alias or target.security_group_id
                security_rule_name = target.rule_name or target.rule_identifier
                provider_name = "阿里云" if account.provider == "aliyun" else ("华为云" if account.provider == "huawei" else account.provider)

                _log_line(
                    "INFO",
                    f"step3.{step3_index}：目标安全组：{provider_name} | {account.name} | {account.region_id} | {security_group_name} | {security_rule_name}",
                )

                _json_log(
                    "INFO",
                    "target.evaluate",
                    provider=account.provider,
                    account=account.name,
                    region=account.region_id,
                    security_group_id=target.security_group_id,
                    rule_identifier=target.rule_identifier,
                    rule_name=target.rule_name,
                    resolved_ip=resolved_ip,
                    last_ip=last_ip,
                    changed=changed,
                    access_key_id=_redact(account.access_key_id),
                )

                _json_log(
                    "INFO",
                    "ip.compare",
                    provider=account.provider,
                    account=account.name,
                    security_group_id=target.security_group_id,
                    rule_identifier=target.rule_identifier,
                    current_ip=resolved_ip,
                    previous_ip=last_ip,
                    changed=changed,
                )
                if not changed:
                    _json_log(
                        "INFO",
                        "target.skip_update",
                        provider=account.provider,
                        account=account.name,
                        security_group_id=target.security_group_id,
                        rule_identifier=target.rule_identifier,
                        reason="ip_unchanged",
                    )
                    _log_line(
                        "INFO",
                        f"当前ip地址: {resolved_ip}，之前记录的ip地址: {last_ip}，是否发生变化: {changed}，跳过更新安全组规则",
                    )
                    skipped_notify_items.append(_build_notify_item(account, target, last_ip, resolved_ip, "skipped", "ip_unchanged"))
                    continue

                _log_line(
                    "INFO",
                    f"当前ip地址: {resolved_ip}，之前记录的ip地址: {last_ip}，是否发生变化: {changed}，开始更新安全组规则",
                )

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
                    updated_count += 1
                    set_last_ip_for_target(
                        state,
                        target_key,
                        resolved_ip,
                        rule_identifier=target.rule_identifier,
                    )
                    _json_log(
                        "INFO",
                        "aliyun.update.success",
                        provider=account.provider,
                        account=account.name,
                        security_group_id=target.security_group_id,
                        rule_identifier=target.rule_identifier,
                        attempts=attempts,
                        new_ip=resolved_ip,
                        updated_at=int(time.time()),
                    )
                    _log_line("INFO", f"更新结果: 成功，耗时: {update_duration_ms}ms")
                    notify_items.append(_build_notify_item(account, target, last_ip, resolved_ip, "success"))
                else:
                    overall_failed = True
                    updated_count += 1
                    _json_log(
                        "ERROR",
                        "cloud.update.failed",
                        provider=account.provider,
                        account=account.name,
                        security_group_id=target.security_group_id,
                        rule_identifier=target.rule_identifier,
                        attempts=attempts,
                        error=error,
                        updated_at=int(time.time()),
                    )
                    _log_line("ERROR", f"更新结果: 失败，耗时: {update_duration_ms}ms")
                    send_webhook_alert(
                        cfg,
                        alert_key=f"update_failed:{account.name}:{target.state_key()}",
                        title="Aliyun rule update failed",
                        detail={
                            "provider": account.provider,
                            "account": account.name,
                            "region": account.region_id,
                            "security_group_id": target.security_group_id,
                            "rule_identifier": target.rule_identifier,
                            "error": error,
                        },
                    )
                    notify_items.append(_build_notify_item(account, target, last_ip, resolved_ip, "failed", error))
            except Exception as e:
                overall_failed = True
                _json_log(
                    "ERROR",
                    "target.exception",
                    provider=account.provider,
                    account=account.name,
                    security_group_id=target.security_group_id,
                    rule_identifier=target.rule_identifier,
                    rule_name=target.rule_name,
                    error_type=type(e).__name__,
                    error=str(e),
                    occurred_at=int(time.time()),
                )
                _log_line(
                    "ERROR",
                    f"执行异常，异常类型: {type(e).__name__}，异常时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，异常信息: {str(e)}",
                )

    pending_items_raw = _load_notify_pending(cfg.notify_pending_file).get("items", [])
    pending_count = len(pending_items_raw) if isinstance(pending_items_raw, list) else 0

    if updated_count > 0 or pending_count > 0:
        if updated_count > 0 and skipped_notify_items:
            notify_items.extend(skipped_notify_items)
        _log_line("INFO", "step4：发送变更通知")
        notify_started = time.time()
        notify_status, notify_attempts, notify_msg, pending_after = dispatch_summary_notification(cfg, resolved_ip, notify_items)
        notify_duration_ms = int((time.time() - notify_started) * 1000)
        notify_result_text = "成功" if notify_status == "sent" else ("失败" if notify_status == "failed" else ("缓冲" if notify_status == "buffered" else "跳过"))
        _log_line(
            "INFO" if notify_status != "failed" else "WARN",
            f"通知邮箱： {','.join(cfg.notify_email_to)}，通知结果: {notify_result_text}，耗时: {notify_duration_ms}ms",
        )
        if notify_status == "sent":
            _json_log("INFO", "notify.sent", count=len(notify_items), attempts=notify_attempts)
            _log_line("INFO", f"汇总通知结果: 成功，尝试次数: {notify_attempts}")
        elif notify_status == "failed":
            _json_log("WARN", "notify.failed", count=len(notify_items), attempts=notify_attempts, error=notify_msg)
            _log_line("WARN", f"汇总通知结果: 失败，尝试次数: {notify_attempts}，错误摘要: {notify_msg}")
            send_webhook_alert(
                cfg,
                alert_key="notify_summary_failed",
                title="Summary notify failed",
                detail={
                    "attempts": notify_attempts,
                    "error": notify_msg,
                    "count": len(notify_items),
                },
            )
        elif notify_status == "buffered":
            _json_log("INFO", "notify.buffered", count=len(notify_items), pending_count=pending_after, reason=notify_msg)
            _log_line("INFO", f"汇总通知结果: 缓冲，原因: {notify_msg}，待发送记录: {pending_after}")
        else:
            _json_log(
                "INFO",
                "notify.skipped",
                count=len(notify_items),
                reason=notify_msg,
                pending_count=pending_after,
            )
            _log_line("INFO", f"汇总通知结果: 跳过，原因: {notify_msg}，待发送记录: {pending_after}")

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
        _log_line("INFO", f"----------------------完成任务，总耗时: {int((ended_at - started_at) * 1000)}ms----------------------")


def run_loop(cfg: AppConfig) -> int:
    reset_stop_requested()
    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)

    last_code = EXIT_OK
    while not is_stop_requested():
        last_code = run_once(cfg)
        if is_stop_requested():
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
        _log_line("ERROR", f"配置无效: {str(e)}")
        return EXIT_CONFIG_ERROR

    if args.once and args.loop:
        _json_log("ERROR", "cli.invalid", error="--once 与 --loop 不能同时使用")
        _log_line("ERROR", "命令行参数无效: --once 与 --loop 不能同时使用")
        return EXIT_CONFIG_ERROR

    if args.once:
        cfg.run_mode = "once"
    elif args.loop:
        cfg.run_mode = "loop"

    if cfg.run_mode == "loop":
        return run_loop(cfg)
    return run_once(cfg)
