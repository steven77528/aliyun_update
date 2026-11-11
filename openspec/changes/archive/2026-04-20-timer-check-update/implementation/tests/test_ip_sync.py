import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "src"))

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

        with patch("ip_sync.urlopen", side_effect=fake_urlopen):
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

        with patch("ip_sync.urlopen", side_effect=fake_urlopen):
            ip, status, _ = ip_sync.resolve_ip_consensus(list(values.keys()), 3)
            self.assertIsNone(ip)
            self.assertEqual("inconsistent", status)

    def test_all_failed(self):
        def fake_urlopen(req, timeout):
            _ = (req, timeout)
            raise OSError("boom")

        with patch("ip_sync.urlopen", side_effect=fake_urlopen):
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
        with patch.dict(os.environ, env, clear=False):
            accounts = ip_sync.parse_accounts_from_env()
            self.assertEqual(1, len(accounts))
            self.assertEqual("default", accounts[0].name)
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

    def test_state_read_write_for_target(self):
        state = {"targets": {}}
        key = "acc-a|cn-hangzhou|sg-1:sgr-1"
        self.assertIsNone(ip_sync.get_last_ip_for_target(state, key))

        ip_sync.set_last_ip_for_target(state, key, "1.2.3.4")
        self.assertEqual("1.2.3.4", ip_sync.get_last_ip_for_target(state, key))


if __name__ == "__main__":
    unittest.main()
