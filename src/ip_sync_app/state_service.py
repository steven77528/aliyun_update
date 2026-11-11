from __future__ import annotations

import json
import time
import datetime as dt
from pathlib import Path
from typing import Dict, List, Optional

from .log_service import _validate_ip
from .models import AppConfig


def load_state(state_file: Path) -> Dict[str, object]:
    if not state_file.exists():
        return {"targets": {}}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if "targets" not in data:
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


def _fmt_epoch(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _get_ip_from_state_item(item: object) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    ip = item.get("last_ip")
    if not ip:
        return None
    try:
        return _validate_ip(str(ip))
    except Exception:
        return None


def _get_rule_identifier_from_state_item(item: object) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    rule_identifier = str(item.get("rule_identifier") or "").strip()
    return rule_identifier or None


def get_last_ip_for_target(state: Dict[str, object], target_key: str) -> Optional[str]:
    targets = state.get("targets", {})
    if not isinstance(targets, dict):
        return None
    item = targets.get(target_key)
    if item is not None:
        return _get_ip_from_state_item(item)
    return _get_ip_from_state_item(targets.get("legacy"))


def get_rule_identifier_for_target(state: Dict[str, object], target_key: str) -> Optional[str]:
    targets = state.get("targets", {})
    if not isinstance(targets, dict):
        return None
    return _get_rule_identifier_from_state_item(targets.get(target_key))


def set_last_ip_for_target(
    state: Dict[str, object],
    target_key: str,
    ip: str,
    rule_identifier: Optional[str] = None,
) -> None:
    targets = state.setdefault("targets", {})
    if not isinstance(targets, dict):
        state["targets"] = {}
        targets = state["targets"]
    assert isinstance(targets, dict)
    now = int(time.time())
    item = {
        "last_ip": ip,
        "updated_at": now,
        "updated_at_text": _fmt_epoch(now),
    }
    preserved_rule_identifier = _get_rule_identifier_from_state_item(targets.get(target_key))
    if rule_identifier:
        item["rule_identifier"] = rule_identifier
    elif preserved_rule_identifier:
        item["rule_identifier"] = preserved_rule_identifier
    targets[target_key] = item


def load_alert_state(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            parsed: Dict[str, int] = {}
            for k, v in data.items():
                if isinstance(v, dict):
                    raw_ts = v.get("last_sent_at", 0)
                else:
                    raw_ts = v
                parsed[str(k)] = int(raw_ts)
            return parsed
    except Exception:
        pass
    return {}


def save_alert_state(path: Path, state: Dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {str(k): {"last_sent_at": int(v), "last_sent_at_text": _fmt_epoch(int(v))} for k, v in state.items()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_notify_pending(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            items = data.get("items")
            if isinstance(items, list):
                return {"items": items}
    except Exception:
        pass
    return {"items": []}


def _save_notify_pending(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    items = payload.get("items")
    if isinstance(items, list):
        normalized: List[object] = []
        for item in items:
            if isinstance(item, dict):
                item = dict(item)
                occurred_at = item.get("occurred_at")
                if occurred_at is not None and "occurred_at_text" not in item:
                    try:
                        item["occurred_at_text"] = _fmt_epoch(int(occurred_at))
                    except Exception:
                        pass
            normalized.append(item)
        payload = dict(payload)
        payload["items"] = normalized
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _upsert_notify_pending(cfg: AppConfig, appended_items: List[Dict[str, object]]) -> int:
    pending = _load_notify_pending(cfg.notify_pending_file)
    old_items = pending.get("items", [])
    merged: List[Dict[str, object]] = []
    if isinstance(old_items, list):
        merged.extend([x for x in old_items if isinstance(x, dict)])
    merged.extend(appended_items)
    _save_notify_pending(cfg.notify_pending_file, {"items": merged})
    return len(merged)


def _set_notify_pending(cfg: AppConfig, items: List[Dict[str, object]]) -> int:
    _save_notify_pending(cfg.notify_pending_file, {"items": items})
    return len(items)


def _clear_notify_pending(cfg: AppConfig) -> None:
    _save_notify_pending(cfg.notify_pending_file, {"items": []})
