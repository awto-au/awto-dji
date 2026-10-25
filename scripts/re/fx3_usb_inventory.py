#!/usr/bin/env python3
"""Inventory USB descriptor candidates and ARM literal references in a CY image.

Static analysis only; descriptor presence does not prove an active hardware mode.
Requires capstone. Does not access USB devices.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

from capstone import CS_ARCH_ARM, CS_MODE_ARM, Cs
from capstone.arm import ARM_OP_MEM, ARM_REG_PC

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fx3_trace import sections
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import log  # noqa: E402


def config_at(data, offset):
    if data[offset:offset + 2] != b'\x09\x02':
        return None
    total = int.from_bytes(data[offset + 2:offset + 4], 'little')
    if not 18 <= total <= 512 or not 1 <= data[offset + 4] <= 8:
        return None
    end = offset + total
    if end > len(data):
        return None
    result = {'total_length': total, 'interface_count': data[offset + 4],
              'configuration_value': data[offset + 5], 'attributes': hex(data[offset + 7]),
              'interfaces': []}
    pos = offset + 9
    interface = None
    while pos + 2 <= end:
        size, kind = data[pos:pos + 2]
        if size < 2 or pos + size > end:
            return None
        record = data[pos:pos + size]
        if kind == 4 and size >= 9:
            interface = {'number': record[2], 'alternate': record[3],
                         'endpoint_count': record[4], 'class': hex(record[5]),
                         'subclass': hex(record[6]), 'protocol': hex(record[7]), 'endpoints': []}
            result['interfaces'].append(interface)
        elif kind == 5 and size >= 7:
            if interface is None:
                return None
            interface['endpoints'].append({'address': hex(record[2]),
                                          'transfer_type': record[3] & 3,
                                          'max_packet': int.from_bytes(record[4:6], 'little')})
        pos += size
    if pos != end or not result['interfaces']:
        return None
    if len({i['number'] for i in result['interfaces']}) != result['interface_count']:
        return None
    if any(len(i['endpoints']) != i['endpoint_count'] for i in result['interfaces']):
        return None
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, type=Path)
    args = parser.parse_args()
    data = args.image.read_bytes()
    image_sections = list(sections(data))
    result = {'image': str(args.image), 'sha256': hashlib.sha256(data).hexdigest(),
              'device_descriptors': [], 'configuration_descriptors': []}
    for base, file_offset, code in image_sections:
        for offset in range(len(code) - 17):
            device = code[offset:offset + 18]
            location = {'file_offset': hex(file_offset + offset), 'va': hex(base + offset)}
            if device[:2] == b'\x12\x01' and device[2:4] in (b'\x10\x01', b'\x00\x02', b'\x00\x03'):
                result['device_descriptors'].append(dict(location,
                    usb_version=hex(int.from_bytes(device[2:4], 'little')),
                    device_class=hex(device[4]),
                    vid_pid=f'{int.from_bytes(device[8:10], "little"):04x}:{int.from_bytes(device[10:12], "little"):04x}',
                    configuration_count=device[17]))
            config = config_at(code, offset)
            if config:
                result['configuration_descriptors'].append(dict(location, **config))

    # Candidate references: absolute words pointing at a descriptor, then ARM
    # PC-relative loads of those words. Linear sweep may include data-as-code.
    descriptors = result['device_descriptors'] + result['configuration_descriptors']
    pools = {}
    for descriptor in descriptors:
        pointer = struct.pack('<I', int(descriptor['va'], 16))
        descriptor['pointer_locations'] = []
        descriptor['literal_loads'] = []
        for base, _, code in image_sections:
            offset = code.find(pointer)
            while offset >= 0:
                address = base + offset
                descriptor['pointer_locations'].append(hex(address))
                pools.setdefault(address, []).append(descriptor)
                offset = code.find(pointer, offset + 1)
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    md.detail = True
    md.skipdata = True
    for base, _, code in image_sections:
        for insn in md.disasm(code, base):
            if not insn.id or not insn.mnemonic.startswith('ldr'):
                continue
            for op in insn.operands:
                if op.type == ARM_OP_MEM and op.mem.base == ARM_REG_PC:
                    pool = insn.address + 8 + op.mem.disp
                    for descriptor in pools.get(pool, []):
                        descriptor['literal_loads'].append(hex(insn.address))
    print(json.dumps(result, indent=2))
    log("inventory complete (JSON on stdout)")


if __name__ == '__main__':
    main()
