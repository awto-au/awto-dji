#!/usr/bin/env python3
"""Compare isolated APK A64 and C1 A32 SIMPLE routines using CPU emulation.

No hardware access or firmware installation. Requires pyelftools and Unicorn;
--unicorn-path supports an isolated dependency directory. Emits vectors for the
Dart verifier and a small summary; vendor instruction bytes remain local inputs.
"""
import argparse
import hashlib
import json
import random
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import log  # noqa: E402
from fx3_trace import sections
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unicorn-path', type=Path)
    parser.add_argument('--vectors', required=True, type=Path)
    args = parser.parse_args()
    if args.unicorn_path:
        sys.path.insert(0, str(args.unicorn_path))
    import unicorn
    from unicorn import Uc, UC_ARCH_ARM, UC_ARCH_ARM64, UC_MODE_ARM
    from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC
    from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

    apk = Path('tmp/apk/raw/lib/arm64-v8a/libGroudStation.so')
    fw = Path('firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1601.bin')
    a64 = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    a64.mem_map(0, 0x20000)
    with apk.open('rb') as stream:
        elf = ELFFile(stream)
        for segment in elf.iter_segments():
            if segment['p_type'] == 'PT_LOAD':
                a64.mem_write(segment['p_vaddr'], segment.data())
        for section in elf.iter_sections():
            if isinstance(section, RelocationSection) and section.is_RELA():
                for relocation in section.iter_relocations():
                    if relocation['r_info_type'] == 1027:
                        a64.mem_write(relocation['r_offset'], struct.pack('<Q', relocation['r_addend']))
    a64.mem_map(0x200000, 0x20000)
    a64.mem_map(0x300000, 0x20000)

    a32 = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    a32.mem_map(0, 0x10000)
    a32.mem_map(0x40000000, 0x40000)
    a32.mem_map(0x50000000, 0x40000)
    for address, _, data in sections(fw.read_bytes()):
        a32.mem_write(address, data)

    def native64(data, seq):
        if data:
            a64.mem_write(0x200000, data)
        for reg, value in [(UC_ARM64_REG_X0, 0x200000), (UC_ARM64_REG_X1, len(data)),
                           (UC_ARM64_REG_X2, seq), (UC_ARM64_REG_X3, 0x210000),
                           (UC_ARM64_REG_X4, 1), (UC_ARM64_REG_SP, 0x30fff0),
                           (UC_ARM64_REG_LR, 0x310000)]:
            a64.reg_write(reg, value)
        a64.emu_start(0x3438, 0x310000, count=100000)
        assert a64.reg_read(UC_ARM64_REG_PC) == 0x310000
        assert a64.reg_read(UC_ARM64_REG_X0) == len(data)
        return bytes(a64.mem_read(0x210000, len(data))) if data else b''

    def native32(data, seq):
        if data:
            a32.mem_write(0x50000000, data)
        for reg, value in [(UC_ARM_REG_R0, 0x50000000), (UC_ARM_REG_R1, len(data)),
                           (UC_ARM_REG_R2, seq), (UC_ARM_REG_SP, 0x5001fff0),
                           (UC_ARM_REG_LR, 0x50020000)]:
            a32.reg_write(reg, value)
        a32.emu_start(0x400042e4, 0x50020000, count=100000)
        assert a32.reg_read(UC_ARM_REG_PC) == 0x50020000
        return bytes(a32.mem_read(0x50000000, len(data))) if data else b''

    rng = random.Random(0x574a)
    sizes = list(range(66)) + [127, 128, 255, 256, 511, 512, 1011, 1012]
    inputs = [(seq, rng.randbytes(size)) for seq in [0, 1, 0x1234, 0x34eb, 0xff00, 0xffff] for size in sizes]
    inputs.extend((rng.randrange(65536), rng.randbytes(rng.randrange(1013))) for _ in range(100))
    vectors = []
    for seq, plain in inputs:
        apk_output = native64(plain, seq)
        fw_output = native32(plain, seq)
        assert apk_output == fw_output, (seq, len(plain))
        assert native64(apk_output, seq) == plain
        assert native32(fw_output, seq) == plain
        vectors.append({'sequence': seq, 'plain': plain.hex(), 'protected': apk_output.hex()})
    args.vectors.write_text(json.dumps({'vectors': vectors}, indent=2) + '\n')
    log(f"{len(vectors)} vectors -> {args.vectors}")
    print(json.dumps({'unicorn_version': unicorn.__version__, 'cases': len(vectors),
                      'apk_entry': '0x3438', 'firmware_entry': '0x400042e4',
                      'apk_sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
                      'firmware_sha256': hashlib.sha256(fw.read_bytes()).hexdigest(),
                      'native_outputs_match': True, 'native_inverse_checks_pass': True,
                      'vectors': str(args.vectors)}, indent=2))


if __name__ == '__main__':
    main()
