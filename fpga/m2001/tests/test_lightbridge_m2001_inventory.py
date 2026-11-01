import hashlib
from pathlib import Path
import struct
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import lightbridge_m2001_inventory as inventory  # noqa: E402


def test_m2001_entry_reads_xv4_module_without_extracting(tmp_path):
    payload = b"unique-m2001-payload"
    data = bytearray(0x80 + len(payload))
    struct.pack_into("<I", data, 0, inventory.XV4_MAGIC)
    struct.pack_into("<H", data, 0x2C, 1)
    data[0x40] = (1 << 5) | 20  # subtype 1, module 20 -> m2001
    struct.pack_into("<IIII", data, 0x44, 0x0101083B, 0x80, len(payload), len(payload))
    data[0x80:] = payload
    image = tmp_path / "C1.bin"
    image.write_bytes(data)

    row = inventory.m2001_entry(image)
    assert row == {
        "path": str(image),
        "entry_version": "0x0101083b",
        "stored_len": len(payload),
        "alloc_len": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
