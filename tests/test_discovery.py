from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wxchat_export.discovery import (
    clean_wxid,
    data_root_candidates,
    discover_accounts,
    parse_linux_ptrace_scope,
    parse_proc_maps_base,
    parse_devtoolssecurity_status,
    parse_sip_status,
    supports_automatic_key_capture,
    wechat_binary_candidates,
)


class DiscoveryTests(unittest.TestCase):
    def test_clean_wxid_strips_suffix(self) -> None:
        self.assertEqual(clean_wxid("wxid_demo_1234"), "wxid_demo")
        self.assertEqual(clean_wxid("gh_foobar"), "gh_foobar")

    def test_discover_accounts_ignores_non_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "WMPF").mkdir()
            (root / "all_users").mkdir()
            (root / "Backup").mkdir()
            (root / "wxid_good_1111" / "db_storage").mkdir(parents=True)
            (root / "wxid_other_2222" / "db_storage").mkdir(parents=True)
            (root / "random-dir").mkdir()

            accounts = discover_accounts(root)

        self.assertEqual([account.account_id for account in accounts], ["wxid_good_1111", "wxid_other_2222"])
        self.assertEqual(accounts[0].cleaned_wxid, "wxid_good")

    def test_parse_devtoolssecurity_status(self) -> None:
        self.assertEqual(
            parse_devtoolssecurity_status("Developer mode is currently enabled."),
            "enabled",
        )
        self.assertEqual(
            parse_devtoolssecurity_status("Developer mode is currently disabled."),
            "disabled",
        )
        self.assertEqual(parse_devtoolssecurity_status("something else"), "unknown")

    def test_parse_sip_status(self) -> None:
        self.assertEqual(
            parse_sip_status("System Integrity Protection status: enabled."),
            "enabled",
        )
        self.assertEqual(
            parse_sip_status("System Integrity Protection status: disabled."),
            "disabled",
        )
        self.assertEqual(parse_sip_status("csrutil unavailable"), "unknown")

    def test_supports_automatic_key_capture_for_supported_platforms(self) -> None:
        self.assertTrue(supports_automatic_key_capture("Darwin"))
        self.assertTrue(supports_automatic_key_capture("Linux"))
        self.assertFalse(supports_automatic_key_capture("Windows"))

    def test_wechat_binary_candidates_honor_env_override(self) -> None:
        with mock.patch.dict("os.environ", {"WXCHAT_EXPORT_WECHAT_BINARY": "/tmp/wechat-bin"}):
            self.assertEqual(wechat_binary_candidates("Linux"), [Path("/tmp/wechat-bin")])

    def test_data_root_candidates_include_platform_defaults(self) -> None:
        candidates = data_root_candidates("Linux")
        candidate_strings = {str(path) for path in candidates}
        self.assertIn(str(Path.home() / ".xwechat"), candidate_strings)
        self.assertIn(str(Path.home() / ".xwechat/xwechat_files"), candidate_strings)

    def test_parse_linux_ptrace_scope(self) -> None:
        self.assertEqual(parse_linux_ptrace_scope("0\n"), 0)
        self.assertEqual(parse_linux_ptrace_scope("2"), 2)
        self.assertIsNone(parse_linux_ptrace_scope("not-a-number"))

    def test_parse_proc_maps_base(self) -> None:
        binary = Path("/usr/bin/wechat")
        sample = """
7f1000000000-7f1000001000 r--p 00000000 08:01 12345 /usr/bin/wechat
7f1000001000-7f1000200000 r-xp 00001000 08:01 12345 /usr/bin/wechat
7f1000200000-7f1000210000 r--p 00200000 08:01 12345 /usr/bin/wechat
""".strip()
        self.assertEqual(parse_proc_maps_base(sample, binary), 0x7F1000000000)


if __name__ == "__main__":
    unittest.main()
