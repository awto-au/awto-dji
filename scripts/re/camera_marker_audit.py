#!/usr/bin/env python3
"""Static camera marker inventory; no device access and no SD-card writes.

Uses the existing A32 tracer and UBIFS reconstruction helper. Reports protocol/path
facts and artifact hashes, never copies vendor source or secret values into output.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import log
import air_survey as ubi
import fpga_write_path as arm

NAMES = [
    '0x40003000.dji', 'CameraLogCur.log', 'CameraLogOld.log',
    'c:\\autoexec.ash', 'd:\\autoexec.ash',
    'P3X_FW_DEBUG', 'P3X_FW_DEBUG_2', 'P3X_FW_LOOP',
    'c:\\DjiAgingFun_300X', 'c:\\DjiBoard', 'c:\\DjiCheckVideo',
    'c:\\Dji97986986_300X', 'c:\\Dji97986986R_300X', 'c:\\amba_mtp.txt',
]


def exact_strings(data, name):
    needle = name.encode() + b'\0'
    offset = data.find(needle)
    while offset >= 0:
        yield offset
        offset = data.find(needle, offset + 1)


def main():
    rootfs = Path(arm.RFS).read_bytes()
    volumes, _ = ubi.ubi_volumes(rootfs)
    files, links = ubi.ubifs_tree(volumes[0])
    result = {
        'sys_image': str(Path(arm.SYS).relative_to(arm.ROOT)),
        'sys_sha256': hashlib.sha256(arm.D).hexdigest(),
        'sys_load_base': hex(arm.BASE),
        'rootfs_image': str(Path(arm.RFS).relative_to(arm.ROOT)),
        'rootfs_sha256': hashlib.sha256(rootfs).hexdigest(),
        'rootfs_files_reconstructed': len(files), 'rootfs_symlinks': len(links),
        'rootfs_limit': 'Existing UBIFS walker; no independent decompression/CRC audit. Negative searches are bounded to reconstructed bytes.',
        'sys_strings': [], 'rootfs_marker_hits': [], 'linux_path_references': [],
    }
    for name in NAMES:
        for offset in exact_strings(arm.D, name):
            address = arm.BASE + offset
            result['sys_strings'].append({
                'name': name, 'file_offset': hex(offset), 'va': hex(address),
                'literal_loads': [hex(a) for a in arm.pool_xrefs(address)],
            })
    for path, data in sorted(files.items()):
        for name in ['0x40003000.dji', 'CameraLogCur.log', 'CameraLogOld.log']:
            if name.encode() in data:
                result['rootfs_marker_hits'].append({'path': path, 'name': name})
        for name in ['/tmp/fuse_d/MISC/tcp_tuner.sh', '/tmp/fuse_d/MISC/wifi.conf',
                     '/tmp/fuse_d/MISC/bt.conf', '/tmp/fuse_a/.exist']:
            if name.encode() in data:
                result['linux_path_references'].append({'path': path, 'name': name})
    result['autoexec_table'] = {
        'va': '0xed8c074', 'count': 2, 'registration_call': '0xe8130c4',
        'table_loads': [hex(a) for a in arm.pool_xrefs(0xed8c074)],
    }
    print(json.dumps(result, indent=2))
    log("audit complete (JSON on stdout)")


if __name__ == '__main__':
    main()
