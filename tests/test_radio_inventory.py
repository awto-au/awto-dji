"""Inventory safeguards independent of downloaded firmware or a simulator."""
import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / "scripts/re/lightbridge_radio_inventory.py"
spec = importlib.util.spec_from_file_location("radio_inventory", path)
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


def test_wrong_firmware_is_refused_before_using_fixed_offsets(tmp_path):
    p = tmp_path / "wrong.bin"
    p.write_bytes(b"wrong firmware")
    with pytest.raises(ValueError, match="SHA-256"):
        inventory.verified_image(p, "air")


def test_script_bounds_and_unknown_operations_are_refused():
    for offset, size in ((0, 3), (0, 8), (-1, 4)):
        with pytest.raises(ValueError, match="bounds"):
            list(inventory.records(b"\x06\x80\x00\x00", offset, size))
    with pytest.raises(ValueError, match="unrecognised"):
        list(inventory.records(b"\xff\x00\x00\x00", 0, 4))


def test_read_dependent_data_is_not_reported_as_a_constant():
    # Minimal input includes FIR configuration values needed by the summariser.
    raw = bytes([6, 0x80, 0x65, 0x78, 6, 0x80, 0xF5, 0x78,
                 8, 0x80, 0xA3, 0, 6, 0x80, 0xA3, 0x12,
                 6, 0x80, 0x0A, 3, 6, 0x80, 0x0A, 6])
    rows = list(inventory.records(raw, 0, len(raw)))
    final, summary, _ = inventory.analyse(rows)
    assert final[0xA3]["table_literal"] == "0x12"
    assert "cached_read" in final[0xA3]["applied"]
    assert final[0x0A]["applied"] == "0x06"
    assert summary["register_history"]["0x00a"] == [("0x10", 3), ("0x14", 6)]
