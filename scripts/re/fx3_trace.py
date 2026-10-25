#!/usr/bin/env python3
"""Read-only ARM disassembly of sectioned Cypress CY boot images (requires capstone).

Addresses are loaded virtual addresses, not container file offsets.
"""
import argparse
import struct
from pathlib import Path

from capstone import CS_ARCH_ARM, CS_MODE_ARM, Cs
from capstone.arm import ARM_OP_IMM

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import log  # noqa: E402


def sections(data):
    if data[:2] != b'CY' or data[3:4] != b'\xb0':
        raise ValueError('Expected executable CY boot image')
    offset = 4
    while offset + 8 <= len(data):
        words, address = struct.unpack_from('<II', data, offset)
        if words == 0:
            return
        start = offset + 8
        end = start + words * 4
        if end > len(data):
            raise ValueError('Truncated CY section')
        yield address, start, data[start:end]
        offset = end
    raise ValueError('Missing CY entry record')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--address', type=lambda x: int(x, 0))
    group.add_argument('--callers', type=lambda x: int(x, 0))
    parser.add_argument('--count', type=int, default=40)
    args = parser.parse_args()
    log(f"disassemble {args.image} ({'address ' + hex(args.address) if args.address is not None else 'callers of ' + hex(args.callers)})")
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    md.detail = True
    md.skipdata = True
    image_sections = list(sections(args.image.read_bytes()))
    for base, file_offset, code in image_sections:
        if args.address is not None:
            offset = args.address - base
            if not 0 <= offset < len(code):
                continue
            print(f'# section VA {base:#x}, file offset {file_offset:#x}')
            for index, insn in enumerate(md.disasm(code[offset:], args.address)):
                if index >= args.count:
                    break
                print(f'{insn.address:#010x}: {insn.mnemonic:8} {insn.op_str}')
            return 0
        for insn in md.disasm(code, base):
            if insn.id and insn.mnemonic in ('bl', 'b', 'blx') and any(
                op.type == ARM_OP_IMM and op.imm == args.callers for op in insn.operands
            ):
                print(f'{insn.address:#010x}: {insn.mnemonic:8} {insn.op_str}')
    if args.address is not None:
        parser.error('Address is outside file-backed sections')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
