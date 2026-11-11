#!/usr/bin/env python3
from __future__ import annotations

import sys

from ip_sync_app import (
    DEFAULT_IP_SOURCES,
    EXIT_CONFIG_ERROR,
    EXIT_IP_INCONSISTENT,
    EXIT_IP_SOURCE_FAILED,
    EXIT_LOCKED,
    EXIT_OK,
    EXIT_UPDATE_FAILED,
    AccountConfig,
    AliyunRuleUpdater,
    AppConfig,
    CloudRuleUpdater,
    HuaweiRuleUpdater,
    Target,
    _clear_notify_pending,
    _fmt_ts,
    _handle_stop_signal,
    _in_night_window,
    _json_log,
    _load_notify_pending,
    _log_line,
    _persist_log_line,
    _redact,
    _save_notify_pending,
    _set_notify_pending,
    _upsert_notify_pending,
    _validate_ip,
    dispatch_summary_notification,
    execute_update_with_retry,
    file_lock,
    get_last_ip_for_target,
    get_rule_identifier_for_target,
    load_alert_state,
    load_state,
    main,
    parse_accounts_from_env,
    parse_accounts_from_yaml_file,
    parse_targets_for_single_account,
    resolve_ip_consensus,
    run_cycle,
    run_loop,
    run_once,
    save_alert_state,
    save_state,
    send_smtp_summary_email,
    send_summary_notification,
    send_webhook_alert,
    set_last_ip_for_target,
)


if __name__ == "__main__":
    sys.exit(main())
