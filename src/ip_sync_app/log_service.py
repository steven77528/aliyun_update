from __future__ import annotations

import datetime as dt
import ipaddress
import os
import time
from pathlib import Path
from typing import Optional


STOP_REQUESTED = False
LOG_DIR = Path(os.getenv("LOG_DIR", "/app-data/logs"))
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "7"))
LOG_VERBOSE_STRUCTURED = os.getenv("LOG_VERBOSE_STRUCTURED", "false").strip().lower() in {"1", "true", "yes", "on"}
_LAST_LOG_CLEANUP_DATE: Optional[str] = None


def _format_epoch(ts: object) -> str:
    try:
        return dt.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def set_log_retention_days(days: int) -> None:
    global LOG_RETENTION_DAYS
    LOG_RETENTION_DAYS = days


def is_stop_requested() -> bool:
    return STOP_REQUESTED


def reset_stop_requested() -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = False


def _json_log(level: str, event: str, **fields: object) -> None:
    if not LOG_VERBOSE_STRUCTURED:
        return

    ts = int(time.time())
    ts_text = dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

    def _fmt(k: str, v: object) -> str:
        if isinstance(v, int) and (k.endswith("_at") or k.endswith("_ts") or k == "ts"):
            return _format_epoch(v)
        if isinstance(v, str):
            return v.replace("\n", "\\n")
        return str(v)

    detail = "，".join([f"{k}: {_fmt(k, v)}" for k, v in fields.items()]) if fields else ""
    if detail:
        line = f"{ts_text}-{level}: {event}，记录时间: {ts_text}，{detail}"
    else:
        line = f"{ts_text}-{level}: {event}，记录时间: {ts_text}"

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

        if _LAST_LOG_CLEANUP_DATE != today_str:
            cutoff_ts = time.time() - LOG_RETENTION_DAYS * 86400
            for f in LOG_DIR.glob("ip_sync_*.log"):
                try:
                    if f.stat().st_mtime < cutoff_ts:
                        f.unlink(missing_ok=True)
                except Exception:
                    pass
            _LAST_LOG_CLEANUP_DATE = today_str

        log_file = LOG_DIR / f"ip_sync_{today.strftime('%Y%m%d')}.log"
        with log_file.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")
    except Exception:
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
