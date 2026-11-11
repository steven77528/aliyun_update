import os
import sys
import tempfile
import time
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import ip_sync  # noqa: E402


class DummyResp:
    def __init__(self, text: str):
        self._text = text

    def read(self):
        return self._text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class TestIpConsensus(unittest.TestCase):
    def test_majority(self):
        values = {
            "https://a": "1.1.1.1",
            "https://b": "1.1.1.1",
            "https://c": "2.2.2.2",
        }

        def fake_urlopen(req, timeout):
            _ = timeout
            return DummyResp(values[req.full_url])

        with patch("ip_sync_app.ip_service.urlopen", side_effect=fake_urlopen):
            ip, status, errors = ip_sync.resolve_ip_consensus(list(values.keys()), 3)
            self.assertEqual("majority", status)
            self.assertEqual("1.1.1.1", ip)
            self.assertEqual({}, errors)

    def test_inconsistent(self):
        values = {
            "https://a": "1.1.1.1",
            "https://b": "2.2.2.2",
        }

        def fake_urlopen(req, timeout):
            _ = timeout
            return DummyResp(values[req.full_url])

        with patch("ip_sync_app.ip_service.urlopen", side_effect=fake_urlopen):
            ip, status, _ = ip_sync.resolve_ip_consensus(list(values.keys()), 3)
            self.assertIsNone(ip)
            self.assertEqual("inconsistent", status)

    def test_all_failed(self):
        def fake_urlopen(req, timeout):
            _ = (req, timeout)
            raise OSError("boom")

        with patch("ip_sync_app.ip_service.urlopen", side_effect=fake_urlopen):
            ip, status, errors = ip_sync.resolve_ip_consensus(["https://a", "https://b"], 3)
            self.assertIsNone(ip)
            self.assertEqual("all_sources_failed", status)
            self.assertEqual(2, len(errors))


class TestConfigAndRetry(unittest.TestCase):
    def test_parse_single_account_compat(self):
        env = {
            "ALIYUN_REGION": "cn-hangzhou",
            "ACCESS_KEY_ID": "id",
            "ACCESS_KEY_SECRET": "secret",
            "SECURITY_GROUP_ID": "sg-1",
            "RULE_IDENTIFIER": "sgr-1",
        }
        with patch.dict(os.environ, env, clear=True):
            accounts = ip_sync.parse_accounts_from_env()
            self.assertEqual(1, len(accounts))
            self.assertEqual("default", accounts[0].name)
            self.assertEqual("aliyun", accounts[0].provider)
            self.assertEqual(1, len(accounts[0].targets))

    def test_retry(self):
        calls = {"n": 0}

        def updater():
            calls["n"] += 1
            if calls["n"] < 3:
                return False, "x"
            return True, "ok"

        ok, attempts, msg = ip_sync.execute_update_with_retry(updater, retry_count=3, retry_backoff_seconds=0)
        self.assertTrue(ok)
        self.assertEqual(3, attempts)
        self.assertEqual("ok", msg)

    def test_cloud_rule_updater_rejects_unsupported_provider(self):
        account = ip_sync.AccountConfig(
            provider="other",
            name="acc",
            region_id="r",
            access_key_id="id",
            access_key_secret="secret",
            targets=[],
        )
        updater = ip_sync.CloudRuleUpdater(account)
        ok, msg = updater.update_rule_source_cidr(
            ip_sync.Target(provider="other", security_group_id="sg", rule_identifier="rid", rule_name="rule"),
            "1.2.3.4",
        )
        self.assertFalse(ok)
        self.assertIn("unsupported_provider", msg)

    @unittest.skipUnless(importlib.util.find_spec("yaml") is not None, "PyYAML 未安装，跳过 YAML 解析测试")
    def test_parse_accounts_from_yaml_file(self):
        yaml_text = """
accounts:
  - account: "acc-a"
    region_id: "cn-hangzhou"
    access_key_id: "id-a"
    access_key_secret: "secret-a"
    security_groups:
      - security_group_id: "sg-1"
        alias: "安全组A"
        rules:
          - rule_id: "sgr-1"
            alias: "规则A"
"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cloud.yaml"
            p.write_text(yaml_text, encoding="utf-8")
            accounts = ip_sync.parse_accounts_from_yaml_file(p)

        self.assertEqual(1, len(accounts))
        self.assertEqual("aliyun", accounts[0].provider)
        self.assertEqual("acc-a", accounts[0].name)
        self.assertEqual(1, len(accounts[0].targets))
        self.assertEqual("sgr-1", accounts[0].targets[0].rule_identifier)
        self.assertEqual("aliyun", accounts[0].targets[0].provider)
        self.assertEqual("规则A", accounts[0].targets[0].rule_name)

    @unittest.skipUnless(importlib.util.find_spec("yaml") is not None, "PyYAML 未安装，跳过 YAML 解析测试")
    def test_parse_accounts_from_unified_cloud_yaml_file(self):
        yaml_text = """
aliyun:
  - account: "ali-a"
    region_id: "cn-hangzhou"
    access_key_id: "id-a"
    access_key_secret: "secret-a"
    security_groups:
      - security_group_id: "sg-1"
        alias: "安全组A"
        rules:
          - rule_id: "sgr-1"
            alias: "规则A"
huawei:
  - account: "hw-a"
    region_id: "cn-north-4"
    access_key_id: "id-h"
    access_key_secret: "secret-h"
    security_groups:
      - security_group_id: "sg-h1"
        alias: "安全组H"
        rules:
          - rule_id: "rule-h1"
            alias: "规则H"
"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cloud.yaml"
            p.write_text(yaml_text, encoding="utf-8")
            accounts = ip_sync.parse_accounts_from_yaml_file(p)

        self.assertEqual(2, len(accounts))
        self.assertEqual(["aliyun", "huawei"], [x.provider for x in accounts])
        self.assertEqual(["aliyun", "huawei"], [x.targets[0].provider for x in accounts])

    def test_state_read_write_for_target(self):
        state = {"targets": {}}
        key = "acc-a|cn-hangzhou|sg-1:sgr-1"
        self.assertIsNone(ip_sync.get_last_ip_for_target(state, key))

        ip_sync.set_last_ip_for_target(state, key, "1.2.3.4")
        self.assertEqual("1.2.3.4", ip_sync.get_last_ip_for_target(state, key))

    def test_state_stores_rule_identifier_for_target(self):
        state = {"targets": {}}
        key = "huawei|hw|cn-north-4|huawei:sg-h1:rule-1"

        ip_sync.set_last_ip_for_target(state, key, "1.2.3.4", rule_identifier="rule-2")

        self.assertEqual("rule-2", ip_sync.get_rule_identifier_for_target(state, key))

    def test_state_keeps_existing_rule_identifier_when_only_updating_ip(self):
        key = "huawei|hw|cn-north-4|huawei:sg-h1:rule-1"
        state = {
            "targets": {
                key: {
                    "last_ip": "1.1.1.1",
                    "rule_identifier": "rule-2",
                    "updated_at": 1,
                }
            }
        }

        ip_sync.set_last_ip_for_target(state, key, "2.2.2.2")

        self.assertEqual("rule-2", ip_sync.get_rule_identifier_for_target(state, key))
        self.assertEqual("2.2.2.2", ip_sync.get_last_ip_for_target(state, key))

    def test_get_last_ip_for_target_falls_back_to_legacy_state(self):
        state = {"targets": {"legacy": {"last_ip": "1.2.3.4", "updated_at": 1}}}
        key = "acc-a|cn-hangzhou|sg-1:sgr-1"

        self.assertEqual("1.2.3.4", ip_sync.get_last_ip_for_target(state, key))

    def test_load_alert_state_supports_readable_timestamp_payload(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "alert.json"
            p.write_text(
                '{"notify_summary_email": {"last_sent_at": 1710000000, "last_sent_at_text": "2024-03-09 16:00:00"}}',
                encoding="utf-8",
            )
            state = ip_sync.load_alert_state(p)

        self.assertEqual({"notify_summary_email": 1710000000}, state)

    def test_set_last_ip_for_target_writes_readable_time(self):
        state = {"targets": {}}
        ip_sync.set_last_ip_for_target(state, "target-a", "1.2.3.4")

        item = state["targets"]["target-a"]
        self.assertEqual("1.2.3.4", item["last_ip"])
        self.assertIn("updated_at_text", item)


class TestMainEntrypoint(unittest.TestCase):
    def test_main_logs_visible_message_when_config_invalid(self):
        with patch("ip_sync_app.orchestrator.AppConfig.from_env", side_effect=ValueError("bad config")), patch(
            "ip_sync_app.orchestrator._json_log"
        ), patch("ip_sync_app.orchestrator._log_line") as mock_log, patch.object(sys, "argv", ["ip_sync.py"]):
            code = ip_sync.main()

        self.assertEqual(ip_sync.EXIT_CONFIG_ERROR, code)
        self.assertTrue(any("配置无效: bad config" in str(c.args[1]) for c in mock_log.call_args_list))

    def test_main_logs_visible_message_when_cli_flags_conflict(self):
        cfg = ip_sync.AppConfig(
            run_mode="once",
            check_interval_seconds=3600,
            ip_sources=["https://a"],
            state_file=Path("./.tmp_state.json"),
            alert_state_file=Path("./.tmp_alert_state.json"),
            lock_file=Path("./.tmp.lock"),
            request_timeout_seconds=3,
            retry_count=0,
            retry_backoff_seconds=0,
            alert_webhook_url="",
            alert_rate_limit_seconds=1,
            notify_enabled=False,
            notify_smtp_host="",
            notify_smtp_port=587,
            notify_smtp_username="",
            notify_smtp_password="",
            notify_smtp_use_tls=True,
            notify_email_from="",
            notify_email_to=[],
            notify_retry_count=3,
            notify_rate_limit_seconds=1,
            notify_pending_file=Path("./.tmp_notify_pending.json"),
            accounts=[],
        )

        with patch("ip_sync_app.orchestrator.AppConfig.from_env", return_value=cfg), patch(
            "ip_sync_app.orchestrator._json_log"
        ), patch("ip_sync_app.orchestrator._log_line") as mock_log, patch.object(
            sys, "argv", ["ip_sync.py", "--once", "--loop"]
        ):
            code = ip_sync.main()

        self.assertEqual(ip_sync.EXIT_CONFIG_ERROR, code)
        self.assertTrue(any("命令行参数无效: --once 与 --loop 不能同时使用" in str(c.args[1]) for c in mock_log.call_args_list))


class TestNotifySummary(unittest.TestCase):
    def _build_cfg(self) -> ip_sync.AppConfig:
        return ip_sync.AppConfig(
            run_mode="once",
            check_interval_seconds=3600,
            ip_sources=["https://a"],
            state_file=Path("./.tmp_state.json"),
            alert_state_file=Path("./.tmp_alert_state.json"),
            lock_file=Path("./.tmp.lock"),
            request_timeout_seconds=3,
            retry_count=0,
            retry_backoff_seconds=0,
            alert_webhook_url="",
            alert_rate_limit_seconds=1,
            notify_enabled=True,
            notify_smtp_host="smtp.example.com",
            notify_smtp_port=587,
            notify_smtp_username="",
            notify_smtp_password="",
            notify_smtp_use_tls=True,
            notify_email_from="from@example.com",
            notify_email_to=["to@example.com"],
            notify_retry_count=3,
            notify_rate_limit_seconds=1,
            notify_pending_file=Path("./.tmp_notify_pending.json"),
            accounts=[],
        )

    def test_summary_disabled(self):
        cfg = self._build_cfg()
        cfg.notify_enabled = False
        status, attempts, msg = ip_sync.send_summary_notification(cfg, "1.1.1.1", [{"result": "success"}])
        self.assertEqual("skipped", status)
        self.assertEqual(0, attempts)
        self.assertEqual("disabled", msg)

    def test_summary_retry_then_success(self):
        cfg = self._build_cfg()
        calls = {"n": 0}

        def fake_send(_cfg, _subject, _body, **_kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                return False, "smtp down"
            return True, "ok"

        with patch("ip_sync_app.notification_service.send_smtp_summary_email", side_effect=fake_send), patch(
            "ip_sync_app.notification_service.time.sleep", return_value=None
        ), patch("ip_sync_app.notification_service.load_alert_state", return_value={}), patch(
            "ip_sync_app.notification_service.save_alert_state", return_value=None
        ):
            status, attempts, msg = ip_sync.send_summary_notification(
                cfg,
                "1.1.1.1",
                [
                    {"account": "a", "region": "r", "security_group_id": "sg", "rule_identifier": "rid", "previous_ip": "1.1.1.1", "current_ip": "2.2.2.2", "result": "success"}
                ],
            )
        self.assertEqual("sent", status)
        self.assertEqual(3, attempts)
        self.assertEqual("ok", msg)

    def test_summary_max_retry_failed(self):
        cfg = self._build_cfg()
        with patch("ip_sync_app.notification_service.send_smtp_summary_email", return_value=(False, "smtp error")), patch(
            "ip_sync_app.notification_service.time.sleep", return_value=None
        ), patch("ip_sync_app.notification_service.load_alert_state", return_value={}):
            status, attempts, msg = ip_sync.send_summary_notification(
                cfg,
                "1.1.1.1",
                [
                    {"account": "a", "region": "r", "security_group_id": "sg", "rule_identifier": "rid", "previous_ip": "1.1.1.1", "current_ip": "2.2.2.2", "result": "failed", "error_summary": "x"}
                ],
            )
        self.assertEqual("failed", status)
        self.assertEqual(4, attempts)
        self.assertIn("smtp", msg)

    def test_summary_body_contains_each_result(self):
        cfg = self._build_cfg()
        captured = {"subject": "", "body": ""}

        def fake_send(_cfg, subject, body, **_kwargs):
            captured["subject"] = subject
            captured["body"] = body
            return True, "ok"

        with patch("ip_sync_app.notification_service.send_smtp_summary_email", side_effect=fake_send), patch(
            "ip_sync_app.notification_service.load_alert_state", return_value={}
        ), patch("ip_sync_app.notification_service.save_alert_state", return_value=None):
            status, attempts, _ = ip_sync.send_summary_notification(
                cfg,
                "2.2.2.2",
                [
                    {
                        "account": "a",
                        "provider": "aliyun",
                        "region": "r1",
                        "security_group_alias": "安全组A",
                        "security_group_id": "sg-1",
                        "rule_identifier": "rid-1",
                        "rule_name": "规则1",
                        "previous_ip": "1.1.1.1",
                        "current_ip": "2.2.2.2",
                        "result": "success",
                    },
                    {
                        "account": "b",
                        "provider": "huawei",
                        "region": "r2",
                        "security_group_alias": "安全组B",
                        "security_group_id": "sg-2",
                        "rule_identifier": "rid-2",
                        "rule_name": "规则2",
                        "previous_ip": "1.1.1.1",
                        "current_ip": "2.2.2.2",
                        "result": "failed",
                        "error_summary": "api_error:boom",
                    },
                ],
            )
        self.assertEqual("sent", status)
        self.assertEqual(1, attempts)
        self.assertEqual("[云安全组自动更新] ---- 更新通知", captured["subject"])
        self.assertIn("公网 IP 发生变化，安全组规则变更汇总通知", captured["body"])
        self.assertIn("| 序号 | 修改时间 | 云厂商 | 账号 | 区域 | 安全组 | 规则 | 旧IP | 新IP | 结果 | 失败原因 |", captured["body"])
        self.assertIn("| aliyun | a | r1 |", captured["body"])
        self.assertIn("| 安全组A / sg-1 |", captured["body"])
        self.assertIn("| 规则1 / rid-1 | 1.1.1.1 | 2.2.2.2 | 成功 | - |", captured["body"])
        self.assertIn("| huawei | b | r2 |", captured["body"])
        self.assertIn("| 安全组B / sg-2 |", captured["body"])
        self.assertIn("| 规则2 / rid-2 | 1.1.1.1 | 2.2.2.2 | 失败 | api_error:boom |", captured["body"])

    def test_summary_body_shows_success_rows_when_all_success(self):
        cfg = self._build_cfg()
        captured = {"body": ""}

        def fake_send(_cfg, _subject, body, **_kwargs):
            captured["body"] = body
            return True, "ok"

        with patch("ip_sync_app.notification_service.send_smtp_summary_email", side_effect=fake_send), patch(
            "ip_sync_app.notification_service.load_alert_state", return_value={}
        ), patch("ip_sync_app.notification_service.save_alert_state", return_value=None):
            status, attempts, _ = ip_sync.send_summary_notification(
                cfg,
                "2.2.2.2",
                [
                    {
                        "account": "a",
                        "provider": "aliyun",
                        "region": "r1",
                        "security_group_id": "sg-1",
                        "rule_identifier": "rid-1",
                        "rule_name": "规则1",
                        "previous_ip": "1.1.1.1",
                        "current_ip": "2.2.2.2",
                        "result": "success",
                    }
                ],
            )
        self.assertEqual("sent", status)
        self.assertEqual(1, attempts)
        self.assertIn("| aliyun | a | r1 |", captured["body"])
        self.assertIn("| 规则1 / rid-1 | 1.1.1.1 | 2.2.2.2 | 成功 | - |", captured["body"])

    def test_summary_body_contains_skipped_rows(self):
        cfg = self._build_cfg()
        captured = {"body": ""}

        def fake_send(_cfg, _subject, body, **_kwargs):
            captured["body"] = body
            return True, "ok"

        with patch("ip_sync_app.notification_service.send_smtp_summary_email", side_effect=fake_send), patch(
            "ip_sync_app.notification_service.load_alert_state", return_value={}
        ), patch("ip_sync_app.notification_service.save_alert_state", return_value=None):
            status, attempts, _ = ip_sync.send_summary_notification(
                cfg,
                "2.2.2.2",
                [
                    {
                        "account": "a",
                        "provider": "aliyun",
                        "region": "r1",
                        "security_group_id": "sg-1",
                        "rule_identifier": "rid-1",
                        "rule_name": "规则1",
                        "previous_ip": "1.1.1.1",
                        "current_ip": "2.2.2.2",
                        "result": "success",
                    },
                    {
                        "account": "h",
                        "provider": "huawei",
                        "region": "r2",
                        "security_group_id": "sg-2",
                        "rule_identifier": "rid-2",
                        "rule_name": "规则H",
                        "previous_ip": "2.2.2.2",
                        "current_ip": "2.2.2.2",
                        "result": "skipped",
                        "error_summary": "ip_unchanged",
                    },
                ],
            )

        self.assertEqual("sent", status)
        self.assertEqual(1, attempts)
        self.assertIn("记录总数 2，成功 1，失败 0，跳过 1", captured["body"])
        self.assertIn("| huawei | h | r2 |", captured["body"])
        self.assertIn("| 规则H / rid-2 | 2.2.2.2 | 2.2.2.2 | 跳过 | - |", captured["body"])

    def test_send_smtp_summary_email_supports_html(self):
        cfg = self._build_cfg()
        cfg.notify_smtp_port = 465
        with patch("ip_sync_app.notification_service.smtplib.SMTP_SSL") as mock_ssl:
            ok, msg = ip_sync.send_smtp_summary_email(
                cfg,
                "subject",
                "plain-body",
                html_body="<html><body><table><tr><td>1</td></tr></table></body></html>",
            )
        self.assertTrue(ok)
        self.assertEqual("ok", msg)
        smtp = mock_ssl.return_value.__enter__.return_value
        sent_msg = smtp.send_message.call_args.args[0]
        self.assertTrue(sent_msg.is_multipart())

    def test_summary_rate_limited(self):
        cfg = self._build_cfg()
        cfg.notify_rate_limit_seconds = 300
        with patch("ip_sync_app.notification_service.load_alert_state", return_value={"notify_summary_email": int(time.time())}), patch(
            "ip_sync_app.notification_service.send_smtp_summary_email"
        ) as mock_send:
            status, attempts, msg = ip_sync.send_summary_notification(
                cfg,
                "2.2.2.2",
                [{"result": "success", "account": "a", "region": "r", "security_group_id": "sg", "rule_identifier": "rid", "previous_ip": "1.1.1.1", "current_ip": "2.2.2.2"}],
            )
        self.assertEqual("skipped", status)
        self.assertEqual(0, attempts)
        self.assertEqual("rate_limited", msg)
        mock_send.assert_not_called()

    def test_run_cycle_logs_step4_when_changed(self):
        cfg = self._build_cfg()
        cfg.accounts = [
            ip_sync.AccountConfig(
                provider="aliyun",
                name="acc",
                region_id="cn-hangzhou",
                access_key_id="id",
                access_key_secret="secret",
                targets=[
                    ip_sync.Target(
                        provider="aliyun",
                        security_group_id="sg-1",
                        rule_identifier="sgr-1",
                        rule_name="规则A",
                        security_group_alias="安全组A",
                    )
                ],
            )
        ]

        with patch("ip_sync_app.orchestrator.resolve_ip_consensus", return_value=("2.2.2.2", "majority", {})), patch(
            "ip_sync_app.orchestrator.load_state", return_value={"targets": {"aliyun|acc|cn-hangzhou|aliyun:sg-1:sgr-1": {"last_ip": "1.1.1.1", "updated_at": 1}}}
        ), patch("ip_sync_app.orchestrator.save_state", return_value=None), patch(
            "ip_sync_app.orchestrator.execute_update_with_retry", return_value=(True, 1, "ok")
        ), patch("ip_sync_app.orchestrator.dispatch_summary_notification", return_value=("sent", 1, "ok", 0)), patch(
            "ip_sync_app.orchestrator._load_notify_pending", return_value={"items": []}
        ), patch("ip_sync_app.orchestrator._log_line"
        ) as mock_log:
            code = ip_sync.run_cycle(cfg)

        self.assertEqual(ip_sync.EXIT_OK, code)
        self.assertTrue(any("step4：发送变更通知" in str(c.args[1]) for c in mock_log.call_args_list))
        self.assertTrue(any("step3.1：目标安全组：阿里云 | acc | cn-hangzhou | 安全组A | 规则A" in str(c.args[1]) for c in mock_log.call_args_list))
        self.assertTrue(
            any(
                "当前ip地址: 2.2.2.2，之前记录的ip地址: 1.1.1.1，是否发生变化: True，开始更新安全组规则" in str(c.args[1])
                for c in mock_log.call_args_list
            )
        )

    def test_run_cycle_logs_step3_index_and_skip_branch(self):
        cfg = self._build_cfg()
        cfg.accounts = [
            ip_sync.AccountConfig(
                provider="aliyun",
                name="acc",
                region_id="cn-hangzhou",
                access_key_id="id",
                access_key_secret="secret",
                targets=[
                    ip_sync.Target(
                        provider="aliyun",
                        security_group_id="sg-1",
                        rule_identifier="sgr-1",
                        rule_name="规则A",
                        security_group_alias="安全组A",
                    ),
                    ip_sync.Target(
                        provider="aliyun",
                        security_group_id="sg-2",
                        rule_identifier="sgr-2",
                        rule_name="规则B",
                        security_group_alias="安全组B",
                    ),
                ],
            )
        ]

        state = {
                "targets": {
                "aliyun|acc|cn-hangzhou|aliyun:sg-1:sgr-1": {"last_ip": "1.1.1.1", "updated_at": 1},
                "aliyun|acc|cn-hangzhou|aliyun:sg-2:sgr-2": {"last_ip": "2.2.2.2", "updated_at": 1},
            }
        }

        with patch("ip_sync_app.orchestrator.resolve_ip_consensus", return_value=("2.2.2.2", "majority", {})), patch(
            "ip_sync_app.orchestrator.load_state", return_value=state
        ), patch("ip_sync_app.orchestrator.save_state", return_value=None), patch(
            "ip_sync_app.orchestrator.execute_update_with_retry", return_value=(True, 1, "ok")
        ), patch("ip_sync_app.orchestrator.dispatch_summary_notification", return_value=("sent", 1, "ok", 0)), patch(
            "ip_sync_app.orchestrator._load_notify_pending", return_value={"items": []}
        ), patch("ip_sync_app.orchestrator._log_line"
        ) as mock_log:
            code = ip_sync.run_cycle(cfg)

        self.assertEqual(ip_sync.EXIT_OK, code)
        self.assertTrue(any("step3.1：目标安全组：阿里云 | acc | cn-hangzhou | 安全组A | 规则A" in str(c.args[1]) for c in mock_log.call_args_list))
        self.assertTrue(any("step3.2：目标安全组：阿里云 | acc | cn-hangzhou | 安全组B | 规则B" in str(c.args[1]) for c in mock_log.call_args_list))
        step3_lines = [i for i, c in enumerate(mock_log.call_args_list) if "step3：更新安全组规则" in str(c.args[1])]
        step31_lines = [i for i, c in enumerate(mock_log.call_args_list) if "step3.1：目标安全组：阿里云 | acc | cn-hangzhou | 安全组A | 规则A" in str(c.args[1])]
        self.assertEqual(1, len(step3_lines))
        self.assertEqual(1, len(step31_lines))
        self.assertLess(step3_lines[0], step31_lines[0])
        self.assertTrue(
            any(
                "当前ip地址: 2.2.2.2，之前记录的ip地址: 2.2.2.2，是否发生变化: False，跳过更新安全组规则" in str(c.args[1])
                for c in mock_log.call_args_list
            )
        )

    def test_dispatch_notification_buffers_in_night_window(self):
        cfg = self._build_cfg()
        items = [{"account": "a", "result": "success", "occurred_at": 1710000000}]

        with patch("ip_sync_app.notification_service._in_night_window", return_value=True), patch(
            "ip_sync_app.notification_service._load_notify_pending", return_value={"items": []}
        ), patch("ip_sync_app.notification_service._upsert_notify_pending", return_value=1
        ):
            status, attempts, msg, pending = ip_sync.dispatch_summary_notification(cfg, "1.1.1.1", items)

        self.assertEqual("buffered", status)
        self.assertEqual(0, attempts)
        self.assertEqual("night_window_buffered", msg)
        self.assertEqual(1, pending)

    def test_dispatch_notification_merges_pending_and_sends_in_daytime(self):
        cfg = self._build_cfg()
        pending = [{"account": "p", "result": "success", "occurred_at": 1710000000}]
        current = [{"account": "c", "result": "failed", "occurred_at": 1710000100, "error_summary": "x"}]

        with patch("ip_sync_app.notification_service._in_night_window", return_value=False), patch(
            "ip_sync_app.notification_service._load_notify_pending", return_value={"items": pending}
        ), patch("ip_sync_app.notification_service.send_summary_notification", return_value=("sent", 1, "ok")) as mock_send, patch(
            "ip_sync_app.notification_service._clear_notify_pending", return_value=None
        ):
            status, attempts, msg, pending_after = ip_sync.dispatch_summary_notification(cfg, "1.1.1.1", current)

        self.assertEqual("sent", status)
        self.assertEqual(1, attempts)
        self.assertEqual("ok", msg)
        self.assertEqual(0, pending_after)
        sent_items = mock_send.call_args.args[2]
        self.assertEqual(2, len(sent_items))

    def test_dispatch_notification_send_failed_keeps_pending(self):
        cfg = self._build_cfg()
        pending = [{"account": "p", "result": "success", "occurred_at": 1710000000}]
        current = [{"account": "c", "result": "failed", "occurred_at": 1710000100, "error_summary": "x"}]

        with patch("ip_sync_app.notification_service._in_night_window", return_value=False), patch(
            "ip_sync_app.notification_service._load_notify_pending", return_value={"items": pending}
        ), patch("ip_sync_app.notification_service.send_summary_notification", return_value=("failed", 2, "smtp err")), patch(
            "ip_sync_app.notification_service._set_notify_pending", return_value=2
        ) as mock_set:
            status, attempts, msg, pending_after = ip_sync.dispatch_summary_notification(cfg, "1.1.1.1", current)

        self.assertEqual("failed", status)
        self.assertEqual(2, attempts)
        self.assertEqual("smtp err", msg)
        self.assertEqual(2, pending_after)
        self.assertTrue(mock_set.called)


class TestHuaweiUpdater(unittest.TestCase):
    def test_run_cycle_restores_huawei_rule_identifier_from_state(self):
        cfg = TestNotifySummary()._build_cfg()
        target = ip_sync.Target(
            provider="huawei",
            security_group_id="sg-h1",
            rule_identifier="rule-1",
            rule_name="规则H",
            security_group_alias="安全组H",
        )
        cfg.accounts = [
            ip_sync.AccountConfig(
                provider="huawei",
                name="hw",
                region_id="cn-north-4",
                access_key_id="id",
                access_key_secret="secret",
                targets=[target],
            )
        ]

        state = {
            "targets": {
                "huawei|hw|cn-north-4|huawei:sg-h1:rule-1": {
                    "last_ip": "1.1.1.1",
                    "rule_identifier": "rule-2",
                    "updated_at": 1,
                }
            }
        }
        observed = {"rule_identifier": None}

        class FakeUpdater:
            def update_rule_source_cidr(self, target_obj, new_ip):
                observed["rule_identifier"] = target_obj.rule_identifier
                if new_ip != "2.2.2.2":
                    raise AssertionError(f"unexpected ip: {new_ip}")
                target_obj.rule_identifier = "rule-3"
                return True, "ok"

        def fake_retry(updater, retry_count, retry_backoff_seconds):
            _ = (retry_count, retry_backoff_seconds)
            ok, msg = updater()
            return ok, 1, msg

        with patch("ip_sync_app.orchestrator.resolve_ip_consensus", return_value=("2.2.2.2", "majority", {})), patch(
            "ip_sync_app.orchestrator.load_state", return_value=state
        ), patch("ip_sync_app.orchestrator.save_state", return_value=None), patch(
            "ip_sync_app.orchestrator.execute_update_with_retry", side_effect=fake_retry
        ), patch("ip_sync_app.orchestrator.dispatch_summary_notification", return_value=("skipped", 0, "disabled", 0)), patch(
            "ip_sync_app.orchestrator._load_notify_pending", return_value={"items": []}
        ), patch("ip_sync_app.orchestrator.CloudRuleUpdater", return_value=FakeUpdater()):
            code = ip_sync.run_cycle(cfg)

        self.assertEqual(ip_sync.EXIT_OK, code)
        self.assertEqual("rule-2", observed["rule_identifier"])
        state_item = state["targets"]["huawei|hw|cn-north-4|huawei:sg-h1:rule-1"]
        self.assertEqual("2.2.2.2", state_item["last_ip"])
        self.assertEqual("rule-3", state_item["rule_identifier"])
        self.assertEqual("rule-3", target.rule_identifier)

    def test_huawei_updater_recreates_and_deletes_rule(self):
        account = ip_sync.AccountConfig(
            provider="huawei",
            name="hw",
            region_id="cn-north-4",
            access_key_id="id",
            access_key_secret="secret",
            targets=[],
        )
        target = ip_sync.Target(provider="huawei", security_group_id="sg-h1", rule_identifier="rule-1", rule_name="规则H")
        updater = ip_sync.HuaweiRuleUpdater(account)

        class Rule:
            id = "rule-1"
            security_group_id = "sg-h1"
            direction = "ingress"
            ethertype = "IPv4"
            protocol = "tcp"
            port_range_min = 22
            port_range_max = 22
            description = "ssh"
            remote_group_id = None
            action = "allow"
            priority = None

        class SecurityGroup:
            security_group_rules = [Rule()]

        class ShowResp:
            security_group = SecurityGroup()

        class FakeClient:
            def __init__(self):
                self.calls = []

            def show_security_group(self, request):
                self.calls.append(("show", request.security_group_id))
                return ShowResp()

            def create_security_group_rule(self, request):
                self.calls.append(("create", request.body.security_group_rule.remote_ip_prefix))
                return type("CreateResp", (), {"security_group_rule": type("CreatedRule", (), {"id": "rule-2"})()})()

            def delete_security_group_rule(self, request):
                self.calls.append(("delete", request.security_group_rule_id))
                return object()

        client = FakeClient()

        with patch.object(ip_sync.HuaweiRuleUpdater, "_build_client", return_value=client), patch.object(
            ip_sync.HuaweiRuleUpdater,
            "_build_show_request",
            side_effect=lambda security_group_id: type("ShowReq", (), {"security_group_id": security_group_id})(),
        ), patch.object(
            ip_sync.HuaweiRuleUpdater,
            "_build_create_request",
            side_effect=lambda body: type("CreateReq", (), {"body": body})(),
        ), patch.object(
            ip_sync.HuaweiRuleUpdater,
            "_build_delete_request",
            side_effect=lambda security_group_rule_id: type("DeleteReq", (), {"security_group_rule_id": security_group_rule_id})(),
        ), patch.object(
            ip_sync.HuaweiRuleUpdater, "_build_rule_body", return_value=type("Body", (), {"security_group_rule": type("Opt", (), {"remote_ip_prefix": "2.2.2.2/32"})()})()
        ):
            ok, msg = updater.update_rule_source_cidr(target, "2.2.2.2")

        self.assertTrue(ok)
        self.assertEqual("ok", msg)
        self.assertEqual(
            [("show", "sg-h1"), ("create", "2.2.2.2/32"), ("delete", "rule-1")],
            client.calls,
        )
        self.assertEqual("rule-2", target.rule_identifier)

    @unittest.skipUnless(importlib.util.find_spec("huaweicloudsdkvpc") is not None, "华为云 SDK 未安装，跳过请求体测试")
    def test_huawei_rule_body_uses_multiport_for_current_sdk(self):
        account = ip_sync.AccountConfig(
            provider="huawei",
            name="hw",
            region_id="cn-north-4",
            access_key_id="id",
            access_key_secret="secret",
            targets=[],
        )
        updater = ip_sync.HuaweiRuleUpdater(account)

        class Rule:
            security_group_id = "sg-h1"
            direction = "ingress"
            ethertype = "IPv4"
            protocol = "tcp"
            multiport = "22"
            description = "ssh"
            remote_group_id = None
            remote_ip_prefix = "1.1.1.1/32"
            action = "allow"
            priority = 1
            enabled = True

        body = updater._build_rule_body(Rule(), "2.2.2.2", "sg-h1")
        option = body.security_group_rule

        self.assertEqual("sg-h1", option.security_group_id)
        self.assertEqual("22", option.multiport)
        self.assertEqual("2.2.2.2/32", option.remote_ip_prefix)
        self.assertFalse(hasattr(option, "port_range_min"))
        self.assertFalse(hasattr(option, "port_range_max"))

    def test_huawei_updater_treats_same_remote_ip_as_success(self):
        account = ip_sync.AccountConfig(
            provider="huawei",
            name="hw",
            region_id="cn-north-4",
            access_key_id="id",
            access_key_secret="secret",
            targets=[],
        )
        target = ip_sync.Target(provider="huawei", security_group_id="sg-h1", rule_identifier="rule-1", rule_name="规则H")
        updater = ip_sync.HuaweiRuleUpdater(account)

        class Rule:
            id = "rule-1"
            security_group_id = "sg-h1"
            remote_ip_prefix = "2.2.2.2/32"

        class SecurityGroup:
            security_group_rules = [Rule()]

        class ShowResp:
            security_group = SecurityGroup()

        class FakeClient:
            def __init__(self):
                self.calls = []

            def show_security_group(self, request):
                self.calls.append(("show", request.security_group_id))
                return ShowResp()

            def create_security_group_rule(self, request):
                self.calls.append(("create", request))
                return object()

            def delete_security_group_rule(self, request):
                self.calls.append(("delete", request))
                return object()

        client = FakeClient()

        with patch.object(ip_sync.HuaweiRuleUpdater, "_build_client", return_value=client), patch.object(
            ip_sync.HuaweiRuleUpdater,
            "_build_show_request",
            side_effect=lambda security_group_id: type("ShowReq", (), {"security_group_id": security_group_id})(),
        ):
            ok, msg = updater.update_rule_source_cidr(target, "2.2.2.2")

        self.assertTrue(ok)
        self.assertEqual("ok", msg)
        self.assertEqual([("show", "sg-h1")], client.calls)


if __name__ == "__main__":
    unittest.main()
