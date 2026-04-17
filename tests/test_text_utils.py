from __future__ import annotations

import unittest

from wxchat_export.text_utils import classify_message, clean_system_message, extract_appmsg_type, sanitize_filename_component


class TextUtilsTests(unittest.TestCase):
    def test_extract_appmsg_type(self) -> None:
        xml = "<msg><appmsg><type>57</type></appmsg></msg>"
        self.assertEqual(extract_appmsg_type(xml), 57)

    def test_clean_system_message_strips_markup(self) -> None:
        raw = "<sysmsg>Hello<br/>World</sysmsg>"
        self.assertEqual(clean_system_message(raw), "Hello\nWorld")

    def test_classify_message_appmsg(self) -> None:
        kind, text = classify_message(49, "<msg><appmsg><type>6</type></appmsg></msg>")
        self.assertEqual(kind, "file")
        self.assertEqual(text, "[文件]")

    def test_sanitize_filename_component(self) -> None:
        self.assertEqual(sanitize_filename_component('A/B:C*D?'), "A_B_C_D_")


if __name__ == "__main__":
    unittest.main()
