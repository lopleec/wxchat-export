from __future__ import annotations

import unittest
from pathlib import Path

from wxchat_export.discovery import parse_vmmap_text_base, wechat_binary_candidates
from wxchat_export.macho import find_db_key_hook_candidates, select_primary_hook_candidate


WECHAT_BINARY = next((path for path in wechat_binary_candidates("Darwin") if path.exists()), None)


class MachOTests(unittest.TestCase):
    @unittest.skipUnless(WECHAT_BINARY is not None, "Local WeChat binary is required")
    def test_primary_hook_candidate_matches_current_machine(self) -> None:
        assert WECHAT_BINARY is not None
        candidates = find_db_key_hook_candidates(WECHAT_BINARY)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].file_offset, 0x142A0)
        self.assertEqual(candidates[0].vmaddr, 0x1000142A0)
        self.assertEqual(select_primary_hook_candidate(WECHAT_BINARY), candidates[0])

    def test_parse_vmmap_text_base(self) -> None:
        sample_binary = Path("/Applications/WeChat.app/Contents/MacOS/WeChat")
        sample = """
Path:            /Applications/WeChat.app/Contents/MacOS/WeChat
__TEXT                      102128000-10a430000    [131.0M  47.3M     0K     0K] r-x/r-x SM=COW          /Applications/WeChat.app/Contents/MacOS/WeChat
__DATA_CONST                10a430000-10a7cc000    [ 3696K  3120K     0K     0K] r--/rw- SM=COW          /Applications/WeChat.app/Contents/MacOS/WeChat
""".strip()
        base = parse_vmmap_text_base(sample, sample_binary)
        self.assertEqual(base, 0x102128000)


if __name__ == "__main__":
    unittest.main()
