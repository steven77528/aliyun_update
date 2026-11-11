from __future__ import annotations

import datetime as dt
import json
import smtplib
import time
from email.message import EmailMessage
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

from .log_service import _json_log
from .models import AppConfig
from .state_service import (
    _clear_notify_pending,
    _load_notify_pending,
    _set_notify_pending,
    _upsert_notify_pending,
    load_alert_state,
    save_alert_state,
)


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


def send_smtp_summary_email(cfg: AppConfig, subject: str, body: str, html_body: Optional[str] = None) -> Tuple[bool, str]:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.notify_email_from
    msg["To"] = ", ".join(cfg.notify_email_to)
    msg.set_content(body, charset="utf-8")
    if html_body:
        msg.add_alternative(html_body, subtype="html", charset="utf-8")

    try:
        if cfg.notify_smtp_use_tls and cfg.notify_smtp_port == 465:
            with smtplib.SMTP_SSL(cfg.notify_smtp_host, cfg.notify_smtp_port, timeout=cfg.request_timeout_seconds) as smtp:
                if cfg.notify_smtp_username:
                    smtp.login(cfg.notify_smtp_username, cfg.notify_smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(cfg.notify_smtp_host, cfg.notify_smtp_port, timeout=cfg.request_timeout_seconds) as smtp:
                if cfg.notify_smtp_use_tls:
                    smtp.starttls()
                if cfg.notify_smtp_username:
                    smtp.login(cfg.notify_smtp_username, cfg.notify_smtp_password)
                smtp.send_message(msg)
        return True, "ok"
    except Exception as e:
        return False, str(e)


def _fmt_ts(ts: object) -> str:
    try:
        return dt.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "-"


def _in_night_window(now: Optional[dt.datetime] = None) -> bool:
    now = now or dt.datetime.now()
    return now.hour >= 22 or now.hour < 7


def send_summary_notification(
    cfg: AppConfig,
    resolved_ip: str,
    items: List[Dict[str, object]],
) -> Tuple[str, int, str]:
    if not cfg.notify_enabled:
        return "skipped", 0, "disabled"
    if not items:
        return "skipped", 0, "no_items"
    if not cfg.notify_smtp_host or not cfg.notify_email_from or not cfg.notify_email_to:
        return "skipped", 0, "config_invalid"

    now = int(time.time())
    notify_key = "notify_summary_email"
    alert_state = load_alert_state(cfg.alert_state_file)
    last = int(alert_state.get(notify_key, 0))
    if now - last < cfg.notify_rate_limit_seconds:
        return "skipped", 0, "rate_limited"

    success_count = sum(1 for x in items if x.get("result") == "success")
    skipped_count = sum(1 for x in items if x.get("result") == "skipped")
    failed_count = len(items) - success_count - skipped_count
    subject = "[云安全组自动更新] ---- 更新通知"
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "公网 IP 发生变化，安全组规则变更汇总通知",
        f"生成时间：{generated_at}",
        f"当前公网 IP：{resolved_ip}",
        f"记录总数 {len(items)}，成功 {success_count}，失败 {failed_count}，跳过 {skipped_count}",
        "",
        "| 序号 | 修改时间 | 云厂商 | 账号 | 区域 | 安全组 | 规则 | 旧IP | 新IP | 结果 | 失败原因 |",
        "|---:|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, item in enumerate(items, start=1):
        sg_alias = str(item.get("security_group_alias") or "-")
        sg_id = str(item.get("security_group_id") or "-")
        rule_alias = str(item.get("rule_name") or item.get("rule_identifier") or "-")
        rule_id = str(item.get("rule_identifier") or "-")
        if item.get("result") == "success":
            result = "成功"
        elif item.get("result") == "skipped":
            result = "跳过"
        else:
            result = "失败"
        lines.append(
            "| {idx} | {mod_at} | {provider} | {account} | {region} | {sg} | {rule} | {prev} | {curr} | {result} | {err} |".format(
                idx=i,
                mod_at=_fmt_ts(item.get("occurred_at")),
                provider=item.get("provider", "-"),
                account=item.get("account", "-"),
                region=item.get("region", "-"),
                sg=f"{sg_alias} / {sg_id}",
                rule=f"{rule_alias} / {rule_id}",
                prev=item.get("previous_ip", "-"),
                curr=item.get("current_ip", "-"),
                result=result,
                err=item.get("error_summary", "-") if item.get("result") not in {"success", "skipped"} else "-",
            )
        )
    body = "\n".join(lines)

    html_rows: List[str] = []
    for i, item in enumerate(items, start=1):
        sg_alias = str(item.get("security_group_alias") or "-")
        sg_id = str(item.get("security_group_id") or "-")
        rule_alias = str(item.get("rule_name") or item.get("rule_identifier") or "-")
        rule_id = str(item.get("rule_identifier") or "-")
        if item.get("result") == "success":
            result = "成功"
        elif item.get("result") == "skipped":
            result = "跳过"
        else:
            result = "失败"
        html_rows.append(
            "<tr>"
            f"<td>{i}</td>"
            f"<td>{_fmt_ts(item.get('occurred_at'))}</td>"
            f"<td>{item.get('provider', '-')}</td>"
            f"<td>{item.get('account', '-')}</td>"
            f"<td>{item.get('region', '-')}</td>"
            f"<td><div>{sg_alias}</div><div>{sg_id}</div></td>"
            f"<td><div>{rule_alias}</div><div>{rule_id}</div></td>"
            f"<td>{item.get('previous_ip', '-')}</td>"
            f"<td>{item.get('current_ip', '-')}</td>"
            f"<td>{result}</td>"
            f"<td>{item.get('error_summary', '-') if item.get('result') not in {'success', 'skipped'} else '-'}</td>"
            "</tr>"
        )
    html_body = (
        "<html><body style='line-height:1.5;'>"
        "<p><strong><span style='color:#000;'>公网 IP 发生变化，安全组规则变更汇总通知</span></strong></p>"
        f"<p>生成时间：{generated_at}</p>"
        f"<p>当前公网 IP：{resolved_ip}</p>"
        f"<p>记录总数 {len(items)}，成功 {success_count}，失败 {failed_count}，跳过 {skipped_count}</p>"
        "<table border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse;text-align:center;'>"
        "<thead><tr>"
        "<th>序号</th><th>修改时间</th><th>云厂商</th><th>账号</th><th>区域</th><th>安全组</th><th>规则</th><th>旧IP</th><th>新IP</th><th>结果</th><th>失败原因</th>"
        "</tr></thead>"
        f"<tbody>{''.join(html_rows)}</tbody>"
        "</table>"
        "</body></html>"
    )

    attempts = 0
    max_attempts = max(1, cfg.notify_retry_count + 1)
    last_error = ""
    for i in range(max_attempts):
        attempts = i + 1
        ok, msg = send_smtp_summary_email(cfg, subject, body, html_body=html_body)
        if ok:
            alert_state[notify_key] = now
            save_alert_state(cfg.alert_state_file, alert_state)
            return "sent", attempts, "ok"
        last_error = msg
        if i < max_attempts - 1:
            _json_log("WARN", "notify.retry", attempt=attempts, error=msg)
            time.sleep(cfg.retry_backoff_seconds * (2**i))

    return "failed", attempts, last_error


def dispatch_summary_notification(
    cfg: AppConfig,
    resolved_ip: str,
    items: List[Dict[str, object]],
) -> Tuple[str, int, str, int]:
    pending_raw = _load_notify_pending(cfg.notify_pending_file).get("items", [])
    pending_items = [x for x in pending_raw if isinstance(x, dict)] if isinstance(pending_raw, list) else []

    now = dt.datetime.now()
    if _in_night_window(now):
        total = _upsert_notify_pending(cfg, items) if items else len(pending_items)
        if items:
            return "buffered", 0, "night_window_buffered", total
        return "skipped", 0, "night_window_no_new_items", total

    merged_items = pending_items + items
    if not merged_items:
        return "skipped", 0, "no_items", 0

    status, attempts, msg = send_summary_notification(cfg, resolved_ip, merged_items)
    if status == "sent":
        _clear_notify_pending(cfg)
        return status, attempts, msg, 0

    total = _set_notify_pending(cfg, merged_items)
    return status, attempts, msg, total
