#!/usr/bin/env python3
"""Trace the air-FPGA update path (UEG fw-id 11, DUML receiver 0x13) in P3X V01.11.0020.

Scope (CLAUDE.md): static interoperability analysis. Firmware is untrusted data, never run.
No key/cipher/signing values are read or printed.

Usage : python3 -I scripts/re/fpga_write_path.py              (canned report, logged)
        python3 -I scripts/re/fpga_write_path.py dis ADDR N   (sys image, annotated A32)
        python3 -I scripts/re/fpga_write_path.py xref ADDR    (literal-pool xrefs + bl callers)
        python3 -I scripts/re/fpga_write_path.py str TEXT     (find string, xrefs)
        python3 -I scripts/re/fpga_write_path.py m0900 ADDR N (Thumb disasm of m0900)
Inputs: tmp/air/amba_P3X0020/*_part_sys.a9s and *_part_rfs.a9s (from air_survey.py),
        firmware/unpacked/P3X_FW_V01.11.0020_m0900.bin, ..._m0101.bin
Output: tmp/logs/fpga_write_path.log ; rootfs files extracted to tmp/air/rfs_P3X0020/
Mode  : sys image is ARM (A32), load base 0x0e600000 (see mode_check()).
"""
import os
import re
import struct
import subprocess
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB, CS_MODE_MCLASS


def repo_root():
    env = os.environ.get("AWTO_DJI_REPO")
    if env and os.path.isdir(env):
        return env
    try:
        top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                      cwd=os.path.dirname(os.path.abspath(__file__)),
                                      stderr=subprocess.DEVNULL).decode().strip()
        if top:
            return top
    except Exception:
        pass
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


ROOT = repo_root()
AMBA = os.path.join(ROOT, "tmp/air/amba_P3X0020/P3X_FW_V01.11.0020_m0100_part_")
SYS = AMBA + "sys.a9s"
RFS = AMBA + "rfs.a9s"
M0900 = os.path.join(ROOT, "firmware/unpacked/P3X_FW_V01.11.0020_m0900.bin")
M0101 = os.path.join(ROOT, "firmware/unpacked/P3X_FW_V01.11.0020_m0101.bin")
RFS_OUT = os.path.join(ROOT, "tmp/air/rfs_P3X0020")
LOG = os.path.join(ROOT, "tmp/logs/fpga_write_path.log")
BASE = 0x0E600000
D = open(SYS, "rb").read()
END = BASE + len(D)
UEG_TABLE, UEG_STRIDE, UEG_N = 0x0EDBA638, 0xBC, 33
TYPE_NAMES = "CAMERA TERMINL MAINCON GIMBAL CENTER TELECON WIFI DM368.A 1765.A PC BATTERY ESC DM368.G 1765.G " \
             "68013.A 68013.G ONE_EYE TWO_EYE FPGA.A FPGA.G".split()
_log = []


def p(*a):
    s = " ".join(str(x) for x in a)
    _log.append(s)
    print(s)


def u32(addr):
    return struct.unpack_from("<I", D, addr - BASE)[0]


def cstr(addr, n=80):
    o = addr - BASE
    if not (0 <= o < len(D)):
        return None
    e = D.find(b"\0", o, o + n)
    s = D[o:e if e > 0 else o + n]
    if len(s) >= 3 and all(0x20 <= c < 0x7F for c in s):
        return s.decode()
    return None


MD = Cs(CS_ARCH_ARM, CS_MODE_ARM)


def mode_check():
    """ARM vs Thumb for the sys image: count A32 prologue/return words vs T16 push halves, and
    check that a known function (DjiMsgChannelInit 0x0e861988) decodes as sane A32."""
    a32 = sum(1 for o in range(0, len(D) - 3, 4) if (struct.unpack_from("<I", D, o)[0] & 0xFFFF4000) == 0xE92D4000)
    bxlr = D.count(struct.pack("<I", 0xE12FFF1E))
    t16 = sum(1 for o in range(0, len(D) - 1, 2) if (struct.unpack_from("<H", D, o)[0] & 0xFF00) == 0xB500)
    p(f"mode: A32 push{{..,lr}} words (4-aligned) {a32}; A32 'bx lr' words {bxlr}; T16 push{{..,lr}} halves {t16}")
    first = [f"{i.mnemonic} {i.op_str}" for i in MD.disasm(D[0x0E861988 - BASE:0x0E861988 - BASE + 16], 0x0E861988)]
    p("mode: DjiMsgChannelInit head decodes as A32:", first)
    p("mode: also movw/movt/bfi/uxtb/ldrd present (ARMv7-A, A32); string literals are 4-aligned pool words")


def dis(addr, n, annotate=True):
    o = addr - BASE
    out = []
    for i in MD.disasm(D[o:o + n * 4], addr):
        line = f"{i.address:#x}: {i.mnemonic} {i.op_str}"
        if annotate and i.mnemonic == "ldr" and "[pc, #" in i.op_str:
            m = re.search(r"\[pc, #(-?)(0x[0-9a-f]+|\d+)\]", i.op_str)
            if m:
                slot = i.address + 8 + int(m.group(2), 0) * (-1 if m.group(1) else 1)
                if BASE <= slot < END:
                    v = u32(slot)
                    s = cstr(v) if BASE <= v < END else None
                    line += f"    ; [{slot:#x}]={v:#x}" + (f' "{s}"' if s else "")
        out.append(line)
        if len(out) >= n:
            break
    return out


def fn_start(addr):
    a = addr - BASE
    while a > 0:
        w = struct.unpack_from("<I", D, a)[0]
        if (w & 0xFFFF0000) == 0xE92D0000 and (w & 0x4000):
            return BASE + a
        a -= 4
    return None


def pool_xrefs(target):
    res = []
    needle = struct.pack("<I", target)
    i = D.find(needle)
    while i != -1:
        if i % 4 == 0:
            slot = BASE + i
            for a in range(max(0, i - 4096), i, 4):
                w = struct.unpack_from("<I", D, a)[0]
                if (w & 0x0F7F0000) in (0x051F0000, 0x059F0000):
                    imm = w & 0xFFF
                    if BASE + a + 8 + (imm if (w >> 23) & 1 else -imm) == slot:
                        res.append(BASE + a)
        i = D.find(needle, i + 1)
    return res


def bl_callers(target):
    res = []
    for o in range(0, len(D) - 3, 4):
        w = struct.unpack_from("<I", D, o)[0]
        if (w & 0x0F000000) == 0x0B000000 and (w >> 28) != 0xF:
            off = w & 0xFFFFFF
            if off & 0x800000:
                off -= 0x1000000
            if BASE + o + 8 + off * 4 == target:
                res.append(BASE + o)
    return res


def show_xrefs(target, label=""):
    px, bc = pool_xrefs(target), bl_callers(target)
    p(f"xref {label}{target:#x}: literal-pool users {[hex(x) for x in px]}; bl callers {[hex(x) for x in bc]}")


def find_str(text):
    return [BASE + m.start() for m in re.finditer(re.escape(text.encode()), D)]


def show_fn(addr, n, title=""):
    p(f"--- {title} {addr:#x} (fn start {fn_start(addr) or 0:#x}) ---")
    for l in dis(addr, n):
        p("  " + l)


def fwid(e):
    return u32(e) & 0xFF  # low byte of entry word 0 = firmware id (verified against wrapper 'mov r0,#id')


def sec_ueg_table():
    p("\n## 1. UEG table: per-entry cells read at the entry's OWN offsets (+0xa4 = transmit-send cell)")
    p("entry-base = path_string - 0x42. Cells: +0x8c ver-send +0x94 entry-send +0x9c confirm-send +0xa4 transmit-send "
      "+0xac finish-send +0xb4 reboot-send; odd +0x90..+0xb8 = response handlers (wrapper fns)")
    names = {0x0E89E018: "DjiUegFwMsgTransmitSend(DUML)", 0x0E89EC48: "DjiUegFwUsbTransmitSend(USB)",
             0x0E8998A8: "DjiUegFpgaFinishHandle", 0x0E8A00E8: "DjiUegFpgaCleanUpHandle",
             0x0E89E608: "DjiUegFwMsgFinishSend", 0x0E89D824: "DjiUegFwMsgEntrySend", 0x0E89DAB4: "ConfirmSend(generic)",
             0x0E89EA3C: "RebootSend(generic)"}
    for k in range(UEG_N):
        e = UEG_TABLE + k * UEG_STRIDE
        path = cstr(e + 0x42, 24)
        if not path or not path.startswith("P"):
            continue
        if path[1:5] in ("FPGA", "6801", "1765", "DM36") or "FC300X" in path:
            cells = {f"+{o:#x}": names.get(u32(e + o), hex(u32(e + o))) for o in (0xA4, 0xB0, 0xB4)}
            prev = e - UEG_STRIDE
            p(f"  {path:<14} entry@{e:#x} fw-id={fwid(e)} type={u32(e + 0x84)} idx={u32(e + 0x88)} own cells {cells}")
            p(f"      cell the old 'path-0x5a' heuristic read = {e + 0x42 - 0x5A - BASE + BASE:#x} -> "
              f"prev entry {prev:#x} +0xa4 = {names.get(u32(prev + 0xA4), hex(u32(prev + 0xA4)))}")


def sec_route():
    p("\n## 2. DUML route: DjiMsgSendTask -> route fn [0x109bdc60] -> channel -> send fn [0x109bdc5c]")
    show_fn(0x0E866DD0, 14, "DjiMsgSendTask route call (blx [0x109bdc60] r0=&pkt[5]=receiver byte)")
    show_fn(0x0E8685C0, 10, "registration (DjiMsgInit): ops = init 0x0e861988, 0x0e861bbc, send 0x0e861c40, route 0x0e861cc4")
    t = D[0x0E861CE4 - BASE:0x0E861CE4 - BASE + 30]
    tg = {0xE861D04: "self-check", 0xE861D40: "ch0", 0xE861D34: "ch2", 0xE861D4C: "ch1", 0xE861D58: "DROP(-1)"}
    p("route fn 0x0e861cc4 byte-switch table @0x0e861ce4, index = receiver_type-1, target = 0x0e861ce8 + 4*byte:")
    for i, b in enumerate(t):
        nm = TYPE_NAMES[i] if i < len(TYPE_NAMES) else "?"
        p(f"   type {i + 1:2d} {nm:<8} -> {tg.get(0xE861CE8 + 4 * b, hex(0xE861CE8 + 4 * b))}")
    tb = D[0x0E861D80 - BASE:0x0E861D80 - BASE + 30]
    p("alt route fn 0x0e861d60 (selected only by DjiMsgTestRouteSet 0x0e86b08c): type19 target "
      f"{0xE861D84 + 4 * tb[18]:#x} (0xe861da0 = ch2)")
    show_fn(0x0E861988, 3, "DjiMsgChannelInit")
    t = D[0x0E8619BC - BASE:0x0E8619BC - BASE + 4]
    p(f"ChannelInit switch table @0x0e8619bc bytes {t.hex()} -> case targets "
      f"{[hex(0xE8619C0 + 4 * b) for b in t]} (ch0/ch1/ch2 UART config; ch3 -> 0xe861aa4 -> 0xe861628 IPC cmd init)")
    show_fn(0x0E861DD0, 12, "channel -> UART index map (0->1, 1->2, 2->3)")
    show_fn(0x0E861C40, 22, "send fn: ch0..2 -> 0xe7f1c30 (UART write); ch3 -> 0xe861934 (IPC)")


def sec_transmit():
    p("\n## 3. Transmit steps")
    show_fn(0x0E89EC48, 12, "DjiUegFwUsbTransmitSend head")
    p("USB transmit core (file offset = [fw+0x48] + [fw+0x458]*[fw+0x460]; read [fw+0x458] bytes; IPC send):")
    for l in dis(0x0E89ED80, 12):
        p("  " + l)
    for l in dis(0x0E89EE60, 12):
        p("  " + l)
    p("  60 s wait after block 0 (movw 0xea60 -> sleep 0xe6f44e4):")
    for l in dis(0x0E89EF18, 6):
        p("  " + l)
    show_fn(0x0E913978, 12, "DjiIpcSendDataSyn (msg magic 0x7788, type 3, size 0x1c, +0x10 data, +0x14 len)")
    show_fn(0x0E8A4A60, 8, "DjiUegFwUpdateById: prep gated on fw-id == 0xb (cmp r0,#0xb)")
    for a, what in ((0x0E8A4AAC, "Linux Boot Up Fail"), (0x0E8A4B68, "IPC attach port 0x5501"),
                    (0x0E8A4C44, "store IPC channel to [fw+0x450]"), (0x0E8A4C70, "Switch To USB Host"),
                    (0x0E8A4D88, "Stop Streaming")):
        p(f"  {what}: {a:#x}: " + "; ".join(l.split(': ', 1)[1] for l in dis(a, 3)))
    p("Confirm handler (block size from reply): 0xe89df04 ldrh [r6]; str [r5,#0x458]")
    for l in dis(0x0E89DF04, 3):
        p("  " + l)
    p("DUML variant (other modules, for contrast) 0xe89e018: payload = [u8 fw+0x450][u32 idx][u16 len][data]; "
      "send = 0xe864ca0(set0, cmd9, ack2, &receiver, pay, len, 1000 ms)")
    show_fn(0x0E89E7A0, 4, "Finish send: FPGA id 0xb copies 2 bytes [fw+0x484], others 16 bytes md5 [fw+0x474]")
    for l in dis(0x0E89E758, 12):
        p("  " + l)
    p("FwInfoInit: sum16 only for fw-id 0xb, over module bytes (path fw+8, off fw+0x48, size fw+0x454); md5 for all:")
    for l in dis(0x0E8A9694, 8):
        p("  " + l)
    show_fn(0x0E8A93D0, 4, "FwInfoInit helper: module header md5 verify (retry 3)")


def sec_ipc_ports():
    p("\n## 4. IPC ports (RTOS 0x55xx <-> Linux 0x66xx)")
    for a in (0x0E8DD34C, 0x0E8DC938, 0x0E91351C, 0x0E913538):
        p(f"  {a:#x}: " + "; ".join(l.split(': ', 1)[1] for l in dis(a, 1)))
    show_fn(0x0E8DD334, 8, "Linux boot-up ack handler attaches ports 0x5500..0x5507")


def sec_m0900():
    p("\n## 5. m0900 re-check (Thumb, base 0x08008000)")
    d = open(M0900, "rb").read()
    B = 0x08008000
    p("dispatch fn 0x0801198a: key bytes [rcv_type][rcv_idx][cmd_set][cmd_id] vs pkt[5]&0x1f, pkt[5]>>5, pkt[9], pkt[10]")
    o = 0x0801A120 - B
    keys = []
    for k in range(40):
        h, key = struct.unpack_from("<II", d, o + 8 * k)
        if h == 0:
            break
        keys.append((h, key))
    p(f"  table 0x0801a120: {len(keys)} records; keys with receiver 0x13: " +
      ", ".join(f"cmd{(k >> 24) & 255:02x}/set{(k >> 16) & 255:02x}->{h:#x}" for h, k in keys if k & 0xFF == 0x13))
    p(f"  any key with cmd 0x09 set 0x00: {[hex(k) for h, k in keys if (k >> 24) == 9 and (k >> 16) & 255 == 0]}")
    t = d[0x80118E4 - B:0x80118E4 - B + 31]
    p("  default (no key match) handler 0x080118d0: tbb table @0x080118e4 by receiver type; type 19 -> "
      f"{0x80118E4 + 2 * t[19]:#x} (0x08011988 = pop {{r4-r6,pc}} = drop). Forwarded types -> "
      f"{sorted({hex(0x80118E4 + 2 * b) for b in t})}")
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    p("  drop target: " + "; ".join(f"{i.mnemonic} {i.op_str}" for i in md.disasm(d[0x8011988 - B:0x8011988 - B + 2], 0x8011988)))
    spi2 = struct.pack("<I", 0x40003800)
    p(f"  SPI2 base literal 0x40003800 occurrences in m0900: {[hex(B + i) for i in range(len(d)) if d[i:i + 4] == spi2]} (register driver only)")
    p(f"  STM32F103 app size {len(d)} B vs FPGA module span ~2.0 MB (see doc): cannot hold the image")


def sec_m0101():
    p("\n## 6. m0101 (camera loader / SD updater)")
    d = open(M0101, "rb").read()
    for pat in (rb"fpga", rb"FPGA", rb"68013", rb"usb", rb"USB", rb"C:/PFC300XFw3\.bin", rb"C:/P3X_FW_V\?\?\.\?\?\.\?\?\?\?\.bin",
                rb"Invalid CRC32 code", rb"firmware model name"):
        p(f"  {pat.decode():<45} count {len(re.findall(pat, d))}")


def sec_linux():
    p("\n## 7. Linux side (rootfs extracted to tmp/air/rfs_P3X0020/)")
    sys.path.insert(0, os.path.join(ROOT, "scripts/re"))
    import air_survey as A  # ubi/ubifs walker only (main guarded)
    want = ["/lib/modules/3.8.0/updates/drivers/rpmsg_trans.ko", "/lib/modules/3.8.0/updates/drivers/68013.ko",
            "/usr/bin/cam_server", "/home/Vend_Ax.iic", "/usr/bin/fxload"]
    if not all(os.path.exists(RFS_OUT + w) for w in want):
        vols, _ = A.ubi_volumes(open(RFS, "rb").read())
        files, _ = A.ubifs_tree(vols[0])
        for w in want:
            os.makedirs(os.path.dirname(RFS_OUT + w), exist_ok=True)
            open(RFS_OUT + w, "wb").write(files[w])
    from elftools.elf.elffile import ELFFile
    for ko, funcs in (("rpmsg_trans.ko", ("ul_rxproc_usbdrv", "ul_rxproc_app")), ("68013.ko", ("usb_cy7c68013a_write_s",))):
        path = RFS_OUT + "/lib/modules/3.8.0/updates/drivers/" + ko
        ef = ELFFile(open(path, "rb"))
        text = ef.get_section_by_name(".text")
        tdata = text.data()
        symtab = ef.get_section_by_name(".symtab")
        syms = {s.name: s for s in symtab.iter_symbols()}
        rel = {}
        for r in ef.get_section_by_name(".rel.text").iter_relocations():
            rel[r["r_offset"]] = symtab.get_symbol(r["r_info_sym"]).name
        for fn in funcs:
            s = syms[fn]
            st, sz = s["st_value"], s["st_size"]
            p(f"--- {ko}:{fn} +{st:#x} size {sz:#x} ---")
            for i in MD.disasm(tdata[st:st + sz], st):
                ann = f"   ; {rel[i.address]}" if i.address in rel else ""
                if i.mnemonic in ("bl", "movw", "cmp", "blx") or ann or "usb" in ann:
                    if i.mnemonic == "bl" or (i.mnemonic in ("movw", "cmp") and ("0x7788" in i.op_str or "#3" in i.op_str[-3:] or "#512" in i.op_str or "#2" in i.op_str[-3:])):
                        p(f"  {i.address:#x}: {i.mnemonic} {i.op_str}{ann}")
        if ko == "68013.ko":
            s = syms["usb_cy7c68013a_write_s"]
            st = s["st_value"]
            ins = list(MD.disasm(tdata[st:st + s["st_size"]], st))
            p("  usb_bulk_msg pipe = (devnum<<8)|0x10000|0xC0000000 (bulk, endpoint 2, OUT); chunk = min(len,512);")
            p("  chunk/pipe/timeout setup (movw r7,#0xd40 + movt r7,#3 = 0x30d40 = 200000 ms per bulk msg):")
            for i in ins:
                if st + 0x5C <= i.address <= st + 0x98:
                    p(f"  {i.address:#x}: {i.mnemonic} {i.op_str}")
    p("  68013.ko USB id alias (strings): " + str([m.group().decode() for m in re.finditer(
        rb"alias=usb:[ -~]{0,40}", open(RFS_OUT + "/lib/modules/3.8.0/updates/drivers/68013.ko", "rb").read())]))


def main():
    if len(sys.argv) > 1:
        c = sys.argv[1]
        if c == "dis":
            show_fn(int(sys.argv[2], 16), int(sys.argv[3]))
        elif c == "xref":
            show_xrefs(int(sys.argv[2], 16))
        elif c == "str":
            for a in find_str(sys.argv[2]):
                p(f"str {a:#x}")
                show_xrefs(a)
        elif c == "m0900":
            d = open(M0900, "rb").read()
            md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
            a = int(sys.argv[2], 16) & ~1
            for k, i in enumerate(md.disasm(d[a - 0x08008000:a - 0x08008000 + 4 * int(sys.argv[3])], a)):
                p(f"{i.address:#x}: {i.mnemonic} {i.op_str}")
                if k + 1 >= int(sys.argv[3]):
                    break
        return
    mode_check()
    sec_ueg_table()
    sec_route()
    sec_transmit()
    sec_ipc_ports()
    sec_m0900()
    sec_m0101()
    sec_linux()
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w") as f:
        f.write("\n".join(_log) + "\n")


if __name__ == "__main__":
    main()
