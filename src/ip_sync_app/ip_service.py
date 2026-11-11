from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

from .log_service import _json_log, _log_line, _validate_ip


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
            _log_line("INFO", f"获取公网ip地址，url: {source}，结果: {ip}，耗时: {duration_ms}ms")
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
            _log_line("WARN", f"获取公网ip地址，url: {source}，结果: 失败({type(e).__name__})，耗时: {duration_ms}ms")
            _json_log(
                "WARN",
                "ip.source.result",
                source=source,
                success=False,
                error_type=type(e).__name__,
                error=str(e),
                fetched_at=int(time.time()),
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
