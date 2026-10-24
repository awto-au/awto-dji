#!/usr/bin/env python3
"""Generate SIMPLE fixtures from the matching APK/firmware protocol table.

The transform is independently expressed from the native disassembly, not executed
vendor code. Output is golden test data; no device access or secret provisioning.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from match_duml_table import apk_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    library = Path('tmp/apk/raw/lib/arm64-v8a/libGroudStation.so')
    firmware = Path('firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin')
    table, address = apk_table(library)
    assert len(table) == 21
    # This reviewed ELF's .rodata VA equals file offset.
    assert library.read_bytes()[address:address + 22] == table + b'\0'
    assert firmware.read_bytes()[0x10920:0x10920 + 22] == table + b'\0'
    table += b'\0'
    vectors = []
    for sequence, data in [(0, b''), (0x34eb, b'\x06\x01'),
                           (0x1234, bytes(range(128))),
                           (0xffff, bytes(i & 255 for i in range(1012)))]:
        state = 0
        mask = []
        for i in range(len(data)):
            candidate = (i % 16) ^ (state + 1)
            state = candidate if candidate <= 21 else 0
            seq_byte = (sequence // (256 if i % 2 else 1)) % 256
            mask.append(table[state] ^ seq_byte)
        encoded = bytes(a ^ b for a, b in zip(data, mask))
        vectors.append({'sequence': sequence, 'plain': data.hex(), 'protected': encoded.hex()})
    result = {'reference': 'Native disassembly: APK 0x3438 and C1 m1601 0x400042e4; independently computed vectors, not live captures',
              'table_sha256': hashlib.sha256(table[:-1]).hexdigest(), 'vectors': vectors}
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
