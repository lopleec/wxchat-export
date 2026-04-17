from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wxchat_export.exporters import write_manifest, write_session_exports
from wxchat_export.models import AccountRef, ExportMessage, SessionRef


class ExporterTests(unittest.TestCase):
    def test_write_markdown_and_jsonl(self) -> None:
        account = AccountRef("wxid_demo_1234", Path("/tmp/account"), "wxid_demo")
        session = SessionRef("friend_wxid", "Alice", False, 1710000000)
        messages = [
            ExportMessage("friend_wxid", 1, 1710000000, "wxid_demo", "我", "text", "hello"),
            ExportMessage("friend_wxid", 2, 1710000300, "friend_wxid", "Alice", "text", "world"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            outputs = write_session_exports(out_dir, account, session, messages, "both")
            manifest = write_manifest(out_dir, account, [(session, len(messages), outputs)])

            self.assertTrue(Path(outputs["md"]).exists())
            self.assertTrue(Path(outputs["jsonl"]).exists())
            self.assertTrue(manifest.exists())

            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest_payload["sessions"][0]["message_count"], 2)


if __name__ == "__main__":
    unittest.main()
