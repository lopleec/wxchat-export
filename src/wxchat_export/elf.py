from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

ANCHOR_STRING = b"com.Tencent.WCDB.Config.Cipher"
LEA_RSI = b"\x48\x8D\x35"
LEA_RDI = b"\x48\x8D\x3D"
FUNC_HEAD = b"\x55\x41\x57"
ELF_MAGIC = b"\x7fELF"
SHT_STRTAB = 3
EM_X86_64 = 62


@dataclass(frozen=True)
class ELFSection:
    name: str
    addr: int
    offset: int
    size: int
    data: bytes


@dataclass(frozen=True)
class LinuxHookCandidate:
    target_va: int
    anchor_string_va: int
    intermediate_va: int
    second_reference_va: int


def _read_c_string(table: bytes, start: int) -> str:
    end = table.find(b"\0", start)
    if end == -1:
        end = len(table)
    return table[start:end].decode("utf-8")


def load_elf_sections(binary_path: Path) -> dict[str, ELFSection]:
    data = binary_path.read_bytes()
    if data[:4] != ELF_MAGIC:
        raise RuntimeError(f"Unsupported ELF magic in {binary_path}")
    if data[4] != 2 or data[5] != 1:
        raise RuntimeError(f"Only ELF64 little-endian binaries are supported: {binary_path}")

    (
        _etype,
        machine,
        _version,
        _entry,
        _phoff,
        shoff,
        _flags,
        _ehsize,
        _phentsize,
        _phnum,
        shentsize,
        shnum,
        shstrndx,
    ) = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)

    if machine != EM_X86_64:
        raise RuntimeError(f"Only x86_64 ELF binaries are supported: {binary_path}")

    sections_raw: list[tuple[int, int, int, int, int]] = []
    for index in range(shnum):
        offset = shoff + (index * shentsize)
        sh_name, _sh_type, _flags, sh_addr, sh_offset, sh_size, _link, _info, _addralign, _entsize = (
            struct.unpack_from("<IIQQQQIIQQ", data, offset)
        )
        sections_raw.append((sh_name, sh_addr, sh_offset, sh_size, offset))

    if shstrndx >= len(sections_raw):
        raise RuntimeError(f"Invalid section string table index in {binary_path}")
    _name, _addr, shstr_offset, shstr_size, _section_offset = sections_raw[shstrndx]
    shstr_data = data[shstr_offset : shstr_offset + shstr_size]

    sections: dict[str, ELFSection] = {}
    for sh_name, sh_addr, sh_offset, sh_size, _offset in sections_raw:
        name = _read_c_string(shstr_data, sh_name)
        if not name:
            continue
        section_bytes = data[sh_offset : sh_offset + sh_size]
        sections[name] = ELFSection(
            name=name,
            addr=sh_addr,
            offset=sh_offset,
            size=sh_size,
            data=section_bytes,
        )
    return sections


def _iter_rip_relative_hits(text: ELFSection, opcode: bytes, target_va: int) -> list[int]:
    hits: list[int] = []
    limit = max(0, len(text.data) - 7)
    for offset in range(limit + 1):
        if text.data[offset : offset + 3] != opcode:
            continue
        disp = struct.unpack_from("<i", text.data, offset + 3)[0]
        resolved = text.addr + offset + 7 + disp
        if resolved == target_va:
            hits.append(offset)
    return hits


def find_linux_hook_candidates_in_sections(rodata: ELFSection, text: ELFSection) -> list[LinuxHookCandidate]:
    candidates: list[LinuxHookCandidate] = []
    search_from = 0
    while True:
        anchor_offset = rodata.data.find(ANCHOR_STRING, search_from)
        if anchor_offset == -1:
            break
        search_from = anchor_offset + 1
        anchor_va = rodata.addr + anchor_offset

        for first_ref_offset in _iter_rip_relative_hits(text, LEA_RSI, anchor_va):
            if first_ref_offset < 7:
                continue
            if text.data[first_ref_offset - 7 : first_ref_offset - 4] != LEA_RDI:
                continue

            unk_disp = struct.unpack_from("<i", text.data, first_ref_offset - 4)[0]
            unk_va = text.addr + first_ref_offset + unk_disp

            for second_ref_offset in _iter_rip_relative_hits(text, LEA_RSI, unk_va):
                head_offset: int | None = None
                scan_start = max(0, second_ref_offset - 0x500)
                for candidate_offset in range(second_ref_offset, scan_start - 1, -1):
                    if text.data[candidate_offset : candidate_offset + len(FUNC_HEAD)] == FUNC_HEAD:
                        head_offset = candidate_offset
                        break
                if head_offset is None:
                    continue
                candidates.append(
                    LinuxHookCandidate(
                        target_va=text.addr + head_offset,
                        anchor_string_va=anchor_va,
                        intermediate_va=unk_va,
                        second_reference_va=text.addr + second_ref_offset,
                    )
                )

    unique: dict[int, LinuxHookCandidate] = {}
    for candidate in candidates:
        unique[candidate.target_va] = candidate
    return sorted(unique.values(), key=lambda item: item.target_va)


def find_linux_db_key_hook_candidates(binary_path: Path) -> list[LinuxHookCandidate]:
    sections = load_elf_sections(binary_path)
    try:
        rodata = sections[".rodata"]
        text = sections[".text"]
    except KeyError as exc:
        raise RuntimeError(f"Missing required ELF section: {exc.args[0]}") from exc
    return find_linux_hook_candidates_in_sections(rodata, text)


def select_primary_linux_hook_candidate(binary_path: Path) -> LinuxHookCandidate:
    candidates = find_linux_db_key_hook_candidates(binary_path)
    if not candidates:
        raise RuntimeError("No Linux DB key hook candidate matched the expected pattern")
    return candidates[0]
