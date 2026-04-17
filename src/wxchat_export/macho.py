from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from .models import HookCandidate

CPU_TYPE_ARM64 = 0x0100000C
FAT_MAGIC = 0xCAFEBABE
LC_SEGMENT_64 = 0x19
ANCHOR_BYTES = bytes.fromhex("E30302AAE20301AA")
MOV_X3_X2 = 0xAA0203E3
MOV_X2_X1 = 0xAA0103E2
MOV_X1_X0 = 0xAA0003E1


@dataclass(frozen=True)
class MachOSlice:
    path: Path
    data: bytes
    slice_offset: int
    text_vmaddr: int
    text_fileoff: int

    def file_offset_to_vmaddr(self, file_offset: int) -> int:
        return self.text_vmaddr + (file_offset - self.text_fileoff)


def load_arm64_slice(binary_path: Path) -> MachOSlice:
    data = binary_path.read_bytes()
    magic_be = struct.unpack_from(">I", data, 0)[0]
    slice_offset = 0
    slice_size = len(data)
    slice_data = data

    if magic_be == FAT_MAGIC:
        _, count = struct.unpack_from(">II", data, 0)
        cursor = 8
        selected: tuple[int, int] | None = None
        for _ in range(count):
            cputype, _cpusubtype, offset, size, _align = struct.unpack_from(
                ">IIIII", data, cursor
            )
            if cputype == CPU_TYPE_ARM64:
                selected = (offset, size)
                break
            cursor += 20
        if selected is None:
            raise RuntimeError(f"No arm64 slice found in {binary_path}")
        slice_offset, slice_size = selected
        slice_data = data[slice_offset : slice_offset + slice_size]

    magic = struct.unpack_from("<I", slice_data, 0)[0]
    if magic != 0xFEEDFACF:
        raise RuntimeError(f"Unsupported Mach-O slice magic: {hex(magic)}")

    _magic, _cpu, _subcpu, _filetype, ncmds, _sizeofcmds, _flags, _reserved = (
        struct.unpack_from("<IiiIIIII", slice_data, 0)
    )
    cursor = 32
    text_vmaddr: int | None = None
    text_fileoff: int | None = None
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", slice_data, cursor)
        if cmd == LC_SEGMENT_64:
            segname = (
                slice_data[cursor + 8 : cursor + 24].split(b"\0", 1)[0].decode("utf-8")
            )
            vmaddr, _vmsize, fileoff, _filesize, _maxprot, _initprot, _nsects, _flags = (
                struct.unpack_from("<QQQQiiii", slice_data, cursor + 24)
            )
            if segname == "__TEXT":
                text_vmaddr = vmaddr
                text_fileoff = fileoff
        cursor += cmdsize

    if text_vmaddr is None or text_fileoff is None:
        raise RuntimeError(f"Missing __TEXT segment in {binary_path}")

    return MachOSlice(
        path=binary_path,
        data=slice_data,
        slice_offset=slice_offset,
        text_vmaddr=text_vmaddr,
        text_fileoff=text_fileoff,
    )


def _read_u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def _reg(word: int, shift: int) -> int:
    return (word >> shift) & 0x1F


def _is_adrp(word: int) -> bool:
    return (word & 0x9F000000) == 0x90000000


def _is_ldr_unsigned_64(word: int) -> bool:
    return (word & 0xFFC00000) == 0xF9400000


def _is_cbz_x(word: int, register: int | None = None) -> bool:
    if (word & 0xFF000000) != 0xB4000000:
        return False
    return register is None or _reg(word, 0) == register


def _is_br(word: int) -> bool:
    return (word & 0xFFFFFC1F) == 0xD61F0000


def _is_b(word: int) -> bool:
    return (word & 0x7C000000) == 0x14000000


def _has_preceding_branch(data: bytes, candidate_offset: int) -> tuple[int, ...]:
    hits: list[int] = []
    start = max(0, candidate_offset - 0x80)
    for offset in range(start, candidate_offset, 4):
        word = _read_u32(data, offset)
        if _is_b(word):
            hits.append(offset)
    return tuple(hits)


def find_db_key_hook_candidates(binary_path: Path) -> list[HookCandidate]:
    image = load_arm64_slice(binary_path)
    candidates: list[HookCandidate] = []
    search_start = 0
    while True:
        anchor_offset = image.data.find(ANCHOR_BYTES, search_start)
        if anchor_offset == -1:
            break
        search_start = anchor_offset + 1
        candidate_offset = anchor_offset - 0x10
        if candidate_offset < 0:
            continue

        words = [_read_u32(image.data, candidate_offset + (i * 4)) for i in range(12)]
        if not (
            _is_adrp(words[0])
            and _is_ldr_unsigned_64(words[1])
            and _is_cbz_x(words[2])
            and _is_br(words[3])
        ):
            continue

        resolver_register = _reg(words[0], 0)
        if not (
            _reg(words[1], 0) == resolver_register
            and _reg(words[1], 5) == resolver_register
            and _reg(words[2], 0) == resolver_register
            and _reg(words[3], 5) == resolver_register
        ):
            continue

        if words[4] != MOV_X3_X2 or words[5] != MOV_X2_X1:
            continue
        if not (_is_cbz_x(words[6], 1) and _is_cbz_x(words[7], 3)):
            continue
        if words[8] != MOV_X1_X0:
            continue
        if not (
            _is_adrp(words[9])
            and _reg(words[9], 0) == 0
            and _is_ldr_unsigned_64(words[10])
            and _reg(words[10], 0) == 0
            and _reg(words[10], 5) == 0
            and _is_b(words[11])
        ):
            continue

        preceding_branches = _has_preceding_branch(image.data, candidate_offset)
        if not preceding_branches:
            continue

        candidates.append(
            HookCandidate(
                file_offset=candidate_offset,
                vmaddr=image.file_offset_to_vmaddr(candidate_offset),
                register=resolver_register,
                preceding_branch_offsets=preceding_branches,
            )
        )

    return candidates


def select_primary_hook_candidate(binary_path: Path) -> HookCandidate:
    candidates = find_db_key_hook_candidates(binary_path)
    if not candidates:
        raise RuntimeError("No macOS DB key hook candidate matched the expected pattern")
    if len(candidates) > 1:
        candidates.sort(key=lambda candidate: (len(candidate.preceding_branch_offsets), -candidate.file_offset), reverse=True)
        return candidates[0]
    return candidates[0]
