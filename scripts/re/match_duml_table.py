#!/usr/bin/env python3
"""Locate the APK SIMPLE table in local artifacts; print offsets, never table bytes.

Requires pyelftools. No device access or protocol transmission.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import log  # noqa: E402

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection


def apk_table(path):
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        symbols = elf.get_section_by_name('.dynsym')

        def symbol(name):
            found = symbols.get_symbol_by_name(name)
            if not found or len(found) != 1:
                raise ValueError(f'Expected one {name} symbol')
            return found[0]['st_value']

        def read_va(address, size):
            for segment in elf.iter_segments():
                start = segment['p_vaddr']
                if segment['p_type'] == 'PT_LOAD' and start <= address and address + size <= start + segment['p_filesz']:
                    stream.seek(segment['p_offset'] + address - start)
                    return stream.read(size)
            raise ValueError(f'No file-backed segment at {address:#x}')

        order = 'little' if elf.little_endian else 'big'
        length = int.from_bytes(read_va(symbol('simple_key_len'), 4), order)
        pointer = symbol('simple_key')
        address = int.from_bytes(read_va(pointer, elf.elfclass // 8), order)
        for section in elf.iter_sections():
            if isinstance(section, RelocationSection) and section.is_RELA():
                for relocation in section.iter_relocations():
                    if relocation['r_offset'] == pointer:
                        # The reviewed AArch64 artifact uses R_AARCH64_RELATIVE.
                        if elf['e_machine'] != 'EM_AARCH64' or relocation['r_info_type'] != 1027:
                            raise ValueError('Unsupported table pointer relocation')
                        address = relocation['r_addend']
        if not 8 <= length <= 4096:
            raise ValueError(f'Unexpected table length {length}')
        return read_va(address, length), address


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk-library', type=Path, default=Path('tmp/apk/raw/lib/arm64-v8a/libGroudStation.so'))
    parser.add_argument('--roots', nargs='+', type=Path, default=[Path('firmware/unpacked'), Path('tmp/air')])
    args = parser.parse_args()
    needle, address = apk_table(args.apk_library)
    result = {'apk_library': str(args.apk_library), 'table_va': hex(address),
              'table_length': len(needle), 'table_sha256': hashlib.sha256(needle).hexdigest(),
              'roots': [str(root) for root in args.roots], 'files_scanned': 0,
              'bytes_scanned': 0, 'matches': [], 'errors': []}
    seen = set()
    for root in args.roots:
        if not root.exists():
            result['errors'].append({'path': str(root), 'error': 'missing root'})
            continue
        candidates = [root] if root.is_file() else sorted(root.rglob('*'))
        for path in candidates:
            if path.is_symlink() or not path.is_file() or path.resolve() in seen:
                continue
            seen.add(path.resolve())
            try:
                data = path.read_bytes()
            except OSError as exc:
                result['errors'].append({'path': str(path), 'error': str(exc)})
                continue
            result['files_scanned'] += 1
            result['bytes_scanned'] += len(data)
            offsets = []
            offset = data.find(needle)
            while offset >= 0:
                offsets.append(hex(offset))
                offset = data.find(needle, offset + 1)
            if offsets:
                result['matches'].append({'path': str(path), 'offsets': offsets,
                                          'sha256': hashlib.sha256(data).hexdigest()})
    print(json.dumps(result, indent=2))
    log(f"{len(result['matches'])} matches, {len(result['errors'])} errors")
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
