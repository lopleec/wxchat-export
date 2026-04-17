from __future__ import annotations

import unittest

from wxchat_export.elf import (
    ELFSection,
    find_linux_hook_candidates_in_sections,
)


class ELFScannerTests(unittest.TestCase):
    def test_find_linux_hook_candidates_in_sections(self) -> None:
        rodata = bytearray(b"\0" * 0x200)
        anchor = b"com.Tencent.WCDB.Config.Cipher\0"
        anchor_offset = 0x40
        rodata[anchor_offset : anchor_offset + len(anchor)] = anchor
        rodata_section = ELFSection(
            name=".rodata",
            addr=0x3000,
            offset=0,
            size=len(rodata),
            data=bytes(rodata),
        )

        text = bytearray(b"\x90" * 0x800)
        head_offset = 0x120
        text[head_offset : head_offset + 3] = b"\x55\x41\x57"

        first_ref_offset = 0x180
        unk_va = 0x5000
        first_lea_rdi_disp = unk_va - (0x1000 + first_ref_offset)
        text[first_ref_offset - 7 : first_ref_offset - 4] = b"\x48\x8D\x3D"
        text[first_ref_offset - 4 : first_ref_offset] = int(first_lea_rdi_disp).to_bytes(
            4, "little", signed=True
        )

        anchor_va = rodata_section.addr + anchor_offset
        first_lea_rsi_disp = anchor_va - (0x1000 + first_ref_offset + 7)
        text[first_ref_offset : first_ref_offset + 3] = b"\x48\x8D\x35"
        text[first_ref_offset + 3 : first_ref_offset + 7] = int(first_lea_rsi_disp).to_bytes(
            4, "little", signed=True
        )

        second_ref_offset = 0x260
        second_lea_rsi_disp = unk_va - (0x1000 + second_ref_offset + 7)
        text[second_ref_offset : second_ref_offset + 3] = b"\x48\x8D\x35"
        text[second_ref_offset + 3 : second_ref_offset + 7] = int(second_lea_rsi_disp).to_bytes(
            4, "little", signed=True
        )

        text_section = ELFSection(
            name=".text",
            addr=0x1000,
            offset=0,
            size=len(text),
            data=bytes(text),
        )

        candidates = find_linux_hook_candidates_in_sections(rodata_section, text_section)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].target_va, 0x1000 + head_offset)
        self.assertEqual(candidates[0].anchor_string_va, anchor_va)
        self.assertEqual(candidates[0].intermediate_va, unk_va)
        self.assertEqual(candidates[0].second_reference_va, 0x1000 + second_ref_offset)


if __name__ == "__main__":
    unittest.main()
