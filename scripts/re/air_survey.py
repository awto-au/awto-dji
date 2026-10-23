#!/usr/bin/env python3
"""Air-side survey: FPGA-stream contact, chip/die ID reads, upgrade-path roles.

Scope (CLAUDE.md): interoperability only. Reads firmware as untrusted data, never
executes it, extracts no keys, touches no geofence or auth code beyond noting it exists.

Inputs : firmware/unpacked/P3X_FW_V01.11.0020_m*.bin (+ raw/ variants, unpacked here)
Outputs: tmp/air/ (variant unpack dirs, m0100 partitions, rootfs), tmp/logs/air_survey.log
Run    : python3 scripts/re/air_survey.py          (about 1 minute, no network)
Notes  : unpack uses dji-firmware-tools' own venv python (needs pycryptodome); the
         analysis itself needs only capstone + stdlib. Rootfs walker is embedded below
         (no ubi_reader / lzo on this box).
"""
import glob
import hashlib
import math
import os
import re
import struct
import subprocess
import sys
import zlib
import collections

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_ARM, CS_MODE_MCLASS
from capstone.arm import ARM_OP_MEM, ARM_REG_PC


def repo_root():
    env = os.environ.get("AWTO_DJI_REPO")
    if env and os.path.isdir(env):
        return env
    try:
        top = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=os.path.dirname(os.path.abspath(__file__)), stderr=subprocess.DEVNULL).decode().strip()
        if top:
            return top
    except Exception:
        pass
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


ROOT = repo_root()
UNP = os.path.join(ROOT, "firmware", "unpacked")
RAW = os.path.join(ROOT, "firmware", "raw")
OUT = os.path.join(ROOT, "tmp", "air")
LOG = os.path.join(ROOT, "tmp", "logs", "air_survey.log")
TOOLS = "/mnt/2tb/git/dji-firmware-tools"
TOOLPY = os.path.join(TOOLS, ".venv", "bin", "python")
MISTRAL = "/mnt/2tb/git/mistral/build/mistral-cv/mistral-cv"
P3X = "P3X_FW_V01.11.0020"

# ---- UBI / UBIFS walker (read-only, untrusted input) -------------------------------
UBIFS_MAGIC = 0x06101831
N_INO, N_DATA, N_DENT = 0, 1, 2
S_IFMT, S_IFREG, S_IFDIR, S_IFLNK = 0o170000, 0o100000, 0o040000, 0o120000


def lzo1x_decompress(src, out_len):
    """LZO1X decompressor, port of the kernel lzo1x_decompress_safe state machine."""
    out = bytearray()
    ip = 0
    state = 0

    def ext(t, base):
        nonlocal ip
        if t == 0:
            while src[ip] == 0:
                t += 255
                ip += 1
            t += base + src[ip]
            ip += 1
        return t

    def copy_match(m, n):
        if m < 0:
            raise ValueError("bad LZO offset")
        for k in range(n):
            out.append(out[m + k])

    if src[0] > 17:
        t = src[0] - 17
        ip = 1
        out += src[ip:ip + t]
        ip += t
        state = t if t < 4 else 4
    while ip < len(src):
        t = src[ip]
        ip += 1
        if t < 16:
            if state == 0:
                t = ext(t, 15) + 3
                out += src[ip:ip + t]
                ip += t
                state = 4
                continue
            if state != 4:
                m = len(out) - 1 - (t >> 2) - (src[ip] << 2)
                ip += 1
                copy_match(m, 2)
            else:
                m = len(out) - 0x801 - (t >> 2) - (src[ip] << 2)
                ip += 1
                copy_match(m, 3)
            state = t & 3
        else:
            if t >= 64:
                m = len(out) - 1 - ((t >> 2) & 7) - (src[ip] << 3)
                ip += 1
                n = (t >> 5) - 1 + 2
                state = t & 3
            elif t >= 32:
                n = ext(t & 31, 31) + 2
                v = src[ip] | (src[ip + 1] << 8)
                ip += 2
                m = len(out) - 1 - (v >> 2)
                state = v & 3
            else:
                hi = (t & 8) << 11
                n = ext(t & 7, 7) + 2
                v = src[ip] | (src[ip + 1] << 8)
                ip += 2
                m = len(out) - hi - (v >> 2)
                if m == len(out):
                    break  # end-of-stream marker
                m -= 0x4000
                state = v & 3
            copy_match(m, n)
        if state:
            out += src[ip:ip + state]
            ip += state
    return bytes(out)


def ubi_volumes(img):
    """Return {vol_id: {lnum: (sqnum, bytes)}} and leb_size, from a raw UBI image."""
    # PEB size: distance between first two 'UBI#' headers
    first = img.find(b"UBI#")
    second = img.find(b"UBI#", first + 4)
    peb = second - first
    vid_off, data_off = struct.unpack(">II", img[first + 16:first + 24])
    leb_size = peb - data_off
    vols = {}
    for p in range(first, len(img) - peb + 1, peb):
        if img[p:p + 4] != b"UBI#":
            continue
        v = p + vid_off
        if img[v:v + 4] != b"UBI!":
            continue
        vol_id, lnum = struct.unpack(">II", img[v + 8:v + 16])
        sq = struct.unpack(">Q", img[v + 40:v + 48])[0]
        if vol_id >= 0x7FFFEFFF:
            continue
        d = vols.setdefault(vol_id, {})
        if lnum not in d or d[lnum][0] < sq:
            d[lnum] = (sq, img[p + data_off:p + peb])
    return vols, leb_size


def ubifs_tree(vol):
    """Parse a UBIFS volume ({lnum: (sq, bytes)}). Returns (files, links) where
    files = {path: bytes}, links = {path: target}."""
    inodes = {}   # ino -> (sq, mode, size, compr, data)
    dents = {}    # (parent, name) -> (sq, inum, type)
    datas = {}    # (ino, block) -> (sq, compr, usize, payload)
    for lnum, (_, leb) in sorted(vol.items()):
        off = 0
        L = len(leb)
        while off + 24 <= L:
            magic = struct.unpack_from("<I", leb, off)[0]
            if magic != UBIFS_MAGIC:
                off += 8
                continue
            sq = struct.unpack_from("<Q", leb, off + 8)[0]
            ln = struct.unpack_from("<I", leb, off + 16)[0]
            nt = leb[off + 20]
            if ln < 24 or off + ln > L:
                off += 8
                continue
            if nt == N_INO and ln >= 160:
                ino = struct.unpack_from("<I", leb, off + 24)[0]
                size = struct.unpack_from("<Q", leb, off + 48)[0]
                mode = struct.unpack_from("<I", leb, off + 104)[0]
                dlen = struct.unpack_from("<I", leb, off + 112)[0]
                prev = inodes.get(ino)
                if not prev or prev[0] < sq:
                    inodes[ino] = (sq, mode, size, bytes(leb[off + 160:off + 160 + dlen]))
            elif nt == N_DENT and ln >= 56:
                parent = struct.unpack_from("<I", leb, off + 24)[0]
                inum = struct.unpack_from("<Q", leb, off + 40)[0]
                typ = leb[off + 49]
                nlen = struct.unpack_from("<H", leb, off + 50)[0]
                name = bytes(leb[off + 56:off + 56 + nlen]).decode("utf-8", "replace")
                k = (parent, name)
                if k not in dents or dents[k][0] < sq:
                    dents[k] = (sq, inum, typ)
            elif nt == N_DATA and ln >= 48:
                ino = struct.unpack_from("<I", leb, off + 24)[0]
                blk = struct.unpack_from("<I", leb, off + 28)[0] & 0x1FFFFFFF
                usize = struct.unpack_from("<I", leb, off + 40)[0]
                comp = struct.unpack_from("<H", leb, off + 44)[0]
                k = (ino, blk)
                if k not in datas or datas[k][0] < sq:
                    datas[k] = (sq, comp, usize, bytes(leb[off + 48:off + ln]))
            off += (ln + 7) & ~7
    children = {}
    for (parent, name), (sq, inum, typ) in dents.items():
        if inum == 0:
            continue
        children.setdefault(parent, []).append((name, inum))
    files, links = {}, {}
    blocks = {}
    for (ino, blk), v in datas.items():
        blocks.setdefault(ino, {})[blk] = v

    def read_file(ino, size):
        out = bytearray()
        for blk in range(0, (size + 4095) // 4096):
            v = blocks.get(ino, {}).get(blk)
            if v is None:
                out += b"\0" * min(4096, size - len(out))
                continue
            _, comp, usize, payload = v
            try:
                if comp == 0:
                    chunk = payload
                elif comp == 2:
                    chunk = zlib.decompress(payload, -15)
                elif comp == 1:
                    chunk = lzo1x_decompress(payload, usize)
                else:
                    chunk = b"\0" * usize
            except Exception:
                chunk = b"\0" * usize
            out += chunk[:usize]
        return bytes(out[:size])

    def walk(ino, path, depth=0):
        if depth > 32:
            return
        for name, inum in sorted(children.get(ino, [])):
            safe = name.replace("/", "_")
            p = path + "/" + safe
            meta = inodes.get(inum)
            if not meta:
                continue
            _, mode, size, data = meta
            fmt = mode & S_IFMT
            if fmt == S_IFDIR:
                walk(inum, p, depth + 1)
            elif fmt == S_IFREG:
                files[p] = read_file(inum, size)
            elif fmt == S_IFLNK:
                links[p] = data.decode("utf-8", "replace")

    walk(1, "")
    return files, links



# ---- helpers -------------------------------------------------------------------------
_log = []


def p(*a):
    line = " ".join(str(x) for x in a)
    _log.append(line)
    print(line)
    sys.stdout.flush()


def sha(d):
    return hashlib.sha256(d).hexdigest()[:12]


def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum(v / n * math.log2(v / n) for v in c.values())


def strings(d, minlen=5):
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % minlen, d):
        yield m.start(), m.group().decode("ascii")


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=300).stdout.decode("utf-8", "replace")


# stall guard: each unpack run is local file IO, observed < 5 s; 300 s overall backstop above.
VARIANTS = {
    "P3X0020": (UNP, None),  # already unpacked
    "P3X0006": ("zip", "P3X/Phantom_3_Professional_Firmware_v1.1.6_en.zip"),
    "P3S0008": ("zip", "P3S/Phantom_3_Advanced_Firmware_v1.1.8_en.zip"),
    "P3C": ("bin", "P3C/P3C_FW_V01.08.0100.bin"),
    "P3SE": ("bin", "P3SE/P3SE_FW_V01.01.0000.bin"),
    "P3XW": ("bin", "P3XW/P3XW_FW_V01.00.0010.bin"),
    "P3XS_RC": ("bin", "P3XS/P3XS_FW_RC_V01.03.0020.bin"),
}


def unpack_variants():
    """Unpack each variant package into a NEW dir under tmp/air (skipped when present)."""
    import zipfile
    dirs = {"P3X0020": UNP}
    for name, (kind, rel) in VARIANTS.items():
        if kind == UNP:
            continue
        dst = os.path.join(OUT, name)
        dirs[name] = dst
        if os.path.isdir(dst) and glob.glob(os.path.join(dst, "*_m*.bin")):
            continue
        os.makedirs(dst, exist_ok=True)
        src = os.path.join(RAW, rel)
        if kind == "zip":
            zd = os.path.join(OUT, "zip_" + name)
            os.makedirs(zd, exist_ok=True)
            with zipfile.ZipFile(src) as z:
                for n in z.namelist():
                    if n.endswith(".bin") and "__MACOSX" not in n:
                        src = os.path.join(zd, os.path.basename(n))
                        with open(src, "wb") as f:
                            f.write(z.read(n))
        out = run([TOOLPY, "-I", os.path.join(TOOLS, "dji_xv4_fwcon.py"), "-x", "-p", src], dst)
        p("unpack", name, "->", dst, "files", len(os.listdir(dst)))
    return dirs


def module_files(d, prefix=None):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "*_m[0-9][0-9][0-9][0-9].bin"))):
        m = re.search(r"_(m\d{4})\.bin$", f)
        if m and (prefix is None or os.path.basename(f).startswith(prefix)):
            out[m.group(1)] = f
    return out


def ini_desc(path):
    s = open(path[:-4] + ".ini").read()
    d = re.search(r"# Stores firmware for (.*)", s)
    v = re.search(r"^version=(.*)", s, re.M)
    return (d.group(1) if d else "?"), (v.group(1) if v else "?")


# ---- architecture identification -------------------------------------------------------
def parse_iic(d):
    """Cypress FX2 C2 .iic -> (vid, pid, did, [(addr, data)])."""
    if d[0] != 0xC2:
        return None
    vid, pid, did = struct.unpack("<HHH", d[1:7])
    i, recs = 8, []  # header: C2, VID, PID, DID (2 B each), config byte
    while i + 4 <= len(d):
        ln = (d[i] << 8) | d[i + 1]
        last, ln = ln & 0x8000, ln & 0x7FFF
        ad = (d[i + 2] << 8) | d[i + 3]
        recs.append((ad, d[i + 4:i + 4 + ln]))
        i += 4 + ln
        if last:
            break
    return vid, pid, did, recs


def pick_base(d, cands):
    best, score = None, -1
    for b in cands:
        s = 0
        for off in range(0, len(d) - 3, 4):
            w = struct.unpack_from("<I", d, off)[0]
            o = w - b
            if 0 <= o < len(d) - 4 and 0x20 <= d[o] < 0x7F and all(0x20 <= x < 0x7F for x in d[o:o + 4]):
                s += 1
        if s > score:
            best, score = b, s
    return best


def arch_of(m, d):
    if d[:8] == b"Salted__"[:8]:
        return "openssl-salted blob (DM368 Linux image), not decryptable here (no key extraction)", None
    if d[:6] == b"FC300X":
        return "Ambarella A9SE firmware container (partitions: sys RTOS, lnx Linux, rfs UBIFS, rom_fw, dsp_fw)", None
    if d[0] == 0xC2 and parse_iic(d):
        return "Cypress FX2LP (8051) .iic image", None
    if m == "m1900":
        return "FPGA bitstream container (0xFF padded, compressed Altera-style payload)", None
    if m == "m0101":
        return "Ambarella camera loader (ARM Cortex-A9, ThreadX/IAR)", None
    sp, rst = struct.unpack_from("<II", d, 0)
    if (sp >> 28) in (1, 2) and rst & 1:
        cands = [0x08000000, 0x08004000, 0x08008000, 0x0800C000, 0x08010000, 0x08020000, 0x20000000, 0]
        known = {"m0305": 0x20000000, "m0306": 0x08020000, "m0400": 0x08008000, "m0900": 0x08008000,
                 "m1701": 0}
        cands = [c for c in cands if c <= (rst & ~1) < c + len(d)]
        base = known[m] if m in known else pick_base(d, cands)
        return f"Cortex-M (Thumb) SP={sp:#x} reset={rst:#x}", base
    if m in ("m1100", "m1101") and b"\x31\x40" in d[:0x80]:
        return "likely TI MSP430 (opcode 0x4031 'mov #imm,SP' near start; inferred)", None
    return "unidentified (not Cortex-M, not 8051 .iic)", None


# ---- constant scan with Thumb literal-pool xrefs ------------------------------------
CONSTS = {
    0x1FFFF7E8: "STM32F1 UID96", 0x1FFFF7E0: "STM32F1 flash-size", 0x1FFFF7AC: "STM32F0/F3 UID96",
    0x1FFFF7CC: "STM32F0/F3 flash-size", 0x1FFF7A10: "STM32F2/F4 UID96", 0x1FFF7A22: "STM32F4 flash-size",
    0x1FFF7590: "STM32L4 UID96", 0x1FF0F420: "STM32F7 UID96", 0x1FF80050: "STM32L1 UID96",
    0xE0042000: "DBGMCU_IDCODE", 0x1FFF1FF1: "LPC IAP entry", 0x1FFF7800: "STM32F4 OTP",
    0x1FFFC000: "STM32F4 option bytes",
}


def thumb_sweep(d, base):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    md.detail = True
    ins, a, end = [], base, base + len(d)
    while a < end:
        got = False
        for i in md.disasm(d[a - base:], a):
            got = True
            ins.append(i)
            a = i.address + i.size
        if not got:
            a += 2
    return ins


def const_scan(m, d, base):
    pools = {}
    for c, n in CONSTS.items():
        b = struct.pack("<I", c)
        i = d.find(b)
        while i != -1:
            if i % 4 == 0:  # literal-pool words are 4-aligned; unaligned hits are opcode noise
                pools[base + i] = (c, n)
            i = d.find(b, i + 1)
    unal = sum(d.count(struct.pack("<I", c)) for c in CONSTS) - len(pools)
    p(f"  consts: {len(pools)} aligned hit(s), {unal} unaligned (ignored)")
    if not pools:
        return
    ins = thumb_sweep(d, base)
    users = {}
    for k, i in enumerate(ins):
        if i.mnemonic.startswith("ldr"):
            for op in i.operands:
                if op.type == ARM_OP_MEM and op.mem.base == ARM_REG_PC:
                    pool = ((i.address + 4) & ~3) + op.mem.disp
                    if pool in pools:
                        users.setdefault(pool, []).append((k, i.address))
    for pool, (c, n) in sorted(pools.items()):
        us = users.get(pool, [])
        p(f"  {c:#010x} {n} pool@{pool:#x} code xrefs: {[hex(a) for _, a in us] or 'none (data, not code)'}")
        for k, a in us[:3]:
            p("      " + "; ".join(f"{j.address:#x} {j.mnemonic} {j.op_str}" for j in ins[k:k + 6]))


def table_scan(d, base, minrun=5):
    """Heuristic: runs of 8-byte records [thumb handler ptr][LE key], key byte1==0, byte2 (cmd set) <= 0x20.
    Calibrated on m0900's DUML dispatch table 0x0801a120 (28 records). Semantics not decoded here."""
    hi = base + len(d)
    out = []
    for start in (0, 4):
        cur = []
        for off in range(start, len(d) - 8, 8):
            h, k = struct.unpack_from("<II", d, off)
            ok = (h & 1) and base <= h < hi and ((k >> 8) & 0xFF) == 0 and ((k >> 16) & 0xFF) <= 0x20
            if ok:
                cur.append((off, h, k))
            else:
                if len(cur) >= minrun:
                    out.append(cur)
                cur = []
        if len(cur) >= minrun:
            out.append(cur)
    for run_ in out:
        p(f"  dispatch-like table @{base + run_[0][0]:#x} n={len(run_)} first keys "
          + ", ".join(f"{k:#010x}->{h:#x}" for _, h, k in run_[:3]))


KW = re.compile(r"(?i)(fpga|altera|cyclone|jtag|idcode|chip.?id|unique|\buid\b|uuid|serial|\bsn\b|\befuse|\botp\b|"
                r"sha204|hwid|68013|lightbridge|dm368|encrypt|authoriz|activation|stream|usb)")


def kw_scan(d, cap=25, skip=None):
    hits = [(o, s) for o, s in strings(d) if KW.search(s) and not (skip and re.search(skip, s))]
    p(f"  keyword strings: {len(hits)}")
    for o, s in hits[:cap]:
        p(f"      {o:#x} {s[:100]}")


# ---- Ambarella m0100 -------------------------------------------------------------------
def amba_extract(variant, m0100):
    dst = os.path.join(OUT, "amba_" + variant)
    if not glob.glob(os.path.join(dst, "*_part_sys.a9s")):
        os.makedirs(dst, exist_ok=True)
        out = run([TOOLPY, "-I", os.path.join(TOOLS, "amba_fwpak.py"), "-x", "-m", m0100], dst)
        if "unusual entry sizes" in out:
            p(f"  amba_fwpak {variant}: {out.strip().splitlines()[-1]}")
    return dst


def a32_xrefs(d, base, target):
    """LDR rX,[pc,#imm] sites whose literal slot holds `target` (ARM mode, 4-aligned)."""
    res = []
    needle = struct.pack("<I", target)
    i = d.find(needle)
    while i != -1:
        if i % 4 == 0:
            slot = base + i
            for a in range(max(0, i - 4096), i, 4):
                w = struct.unpack_from("<I", d, a)[0]
                if (w & 0x0F7F0000) == 0x051F0000 or (w & 0x0F7F0000) == 0x059F0000:
                    imm = w & 0xFFF
                    tgt = base + a + 8 + (imm if (w >> 23) & 1 else -imm)
                    if tgt == slot:
                        res.append(base + a)
        i = d.find(needle, i + 1)
    return res


def fn_start_a32(d, base, addr):
    a = addr - base
    while a > 0:
        a -= 4
        w = struct.unpack_from("<I", d, a)[0]
        if (w & 0xFFFF0000) == 0xE92D0000 and (w & 0x4000):
            return base + a
    return None


def wrapper_fwid(sysd, base, path_off):
    """Firmware id of a UEG table entry = the 'mov r0,#N' inside its per-entry wrapper cells."""
    ids = collections.Counter()
    for k in range(-0x18, 0x08, 4):
        c = struct.unpack_from("<I", sysd, path_off - 0x5A + k)[0]
        o = c - base
        if not (0 <= o < len(sysd) - 24):
            continue
        for w in range(0, 6):
            wd = struct.unpack_from("<I", sysd, o + 4 * w)[0]
            if (wd & 0xFFFFFF00) == 0xE3A00000:
                ids[wd & 0xFF] += 1
                break
    return ids.most_common(1)[0][0] if ids else None


ELF = b"\x7fELF"


def survey_m0100(variant, m0100, deep=True):
    dst = amba_extract(variant, m0100)
    parts = {os.path.basename(f).split("_part_")[1][:-4]: f for f in glob.glob(os.path.join(dst, "*_part_*.a9s"))}
    p(f"  [{variant}] partitions: " + ", ".join(f"{k}={os.path.getsize(v)}" for k, v in sorted(parts.items())))
    if "sys" not in parts:
        # container layout not handled by amba_fwpak (P3SE): raw presence scan only
        raw = open(m0100, "rb").read()
        p(f"  [{variant}] amba_fwpak could not split m0100; raw presence scan of whole module:")
        for k in ("DjiUegFpgaFinishHandle", "MCCTRL_68013Update", "DjiEncryptSaveBothToSha204AndA9", "FPGA.A ",
                  "PFPGAFw3.bin", "Vend_Ax.iic", "68013.ko"):
            p(f"    {k!r}: {raw.count(k.encode())} occurrence(s) (compressed/UBIFS content not searchable)")
        return None
    sysd = open(parts["sys"], "rb").read()
    base = 0x0E600000  # mem_addr= in *_part_sys.a9h
    keys = ["DjiUegFpgaFinishHandle", "DjiUegFpgaCleanUpHandle", "DjiUegFwUsbTransmitSend", "MCCTRL_68013Update",
            "MCCTRL_68013GetVersion", "DjiReset68013", "DjiAgingIfDM368Ok", "DjiEncryptSaveBothToSha204AndA9",
            "DjiEncryptCheckA9Mac", "DjiEncryptWriteAllBoardNumToOTP", "DjiSerialNumGenerate", "DjiMsgAuthorizedMac",
            "FPGA.A ", "68013.A", "DM368.A", "PFPGAFw3.bin", "P68013Fw3.bin", "PDM368Fw3.bin"]
    found = {}
    for k in keys:
        o = sysd.find(k.encode() + b"\0")
        if o < 0:
            o = sysd.find(k.encode())  # e.g. 'DjiAgingIfDM368Ok:' is embedded in a longer log string
        found[k] = o
        if o >= 0 and deep:
            xr = a32_xrefs(sysd, base, base + o)
            p(f"    sys {k!r} str@{base + o:#x} (file {o:#x}) code xrefs {[hex(x) for x in xr[:4]]}")
        else:
            p(f"    sys {k!r}: {'present' if o >= 0 else 'ABSENT'}")
    # UEG firmware table: transmit-handler cell sits 0x5a bytes before each 'P*Fw3.bin' path string
    msg_o, usb_o = found["DjiUegFwUsbTransmitSend"], found.get("DjiUegFwUsbTransmitSend")
    if usb_o >= 0:
        usb_fn = None
        xr = a32_xrefs(sysd, base, base + usb_o)
        if xr:
            usb_fn = fn_start_a32(sysd, base, xr[0])
        mo = sysd.find(b"DjiUegFwMsgTransmitSend\0")
        xm = a32_xrefs(sysd, base, base + mo)
        msg_fn = fn_start_a32(sysd, base, xm[0]) if xm else None
        p(f"    UEG fns: UsbTransmitSend={usb_fn and hex(usb_fn)} MsgTransmitSend={msg_fn and hex(msg_fn)}")
        for m in re.finditer(rb"P[A-Z0-9]+Fw3\.bin\0", sysd):
            o = m.start()
            cell = struct.unpack_from("<I", sysd, o - 0x5A)[0]
            tag = "USB" if cell == usb_fn else ("DUML-msg" if cell == msg_fn else f"{cell:#x}")
            if m.group()[1:-8].decode() in ("FPGA", "68013", "DM368", "1765", "ESC1", "GIMBAL", "FC300X", "MCAPP", "CAMLDR"):
                fid = wrapper_fwid(sysd, base, o)
                e = o - 0x42  # entry start: DjiUegFwConfigCheck reads receiver at +0x84, index at +0x88 (stride 0xBC)
                rtype = struct.unpack_from("<I", sysd, e + 0x84)[0]
                ridx = struct.unpack_from("<I", sysd, e + 0x88)[0]
                p(f"      fw-table {m.group()[:-1].decode():<16} fw-id={fid} receiver(type,idx)=({rtype},{ridx}) "
                  f"entry@{base + e:#x} path@file {o:#x} transmit-cell@file {o - 0x5A:#x} -> {tag}")
    # module-name table (DUML receiver names) for orientation
    nm = sysd.find(b"CAMERA \0")
    if nm >= 0:
        names = [sysd[nm + 8 * k:nm + 8 * k + 7].decode("ascii", "replace").strip("\0 ") for k in range(32)]
        p("    DUML receiver-name table @%#x: %s" % (base + nm, names))
    if not deep:
        return
    # rootfs
    img = open(parts["rfs"], "rb").read()
    vols, _ = ubi_volumes(img)
    files, links = ubifs_tree(vols[0])
    p(f"  [{variant}] rootfs: {len(files)} files, {len(links)} symlinks; "
      f"ELF {sum(1 for v in files.values() if v[:4] == ELF)}")
    interesting = [f for f in files if re.search(r"(68013|lpc1765|rpmsg|rscvmem|fxload|Vend_Ax|cam_server|rpc_trans|"
                                                 r"viz_tracking|util_svc|monhotplug|usersetting|libambaipc|libudt)", f)]
    p("    DJI-specific rootfs paths: " + ", ".join(f"{f}({len(files[f])})" for f in sorted(interesting)))
    for f in sorted(interesting):
        d = files[f]
        if f.endswith(".ko") or "/bin/" in f or f.endswith("usersetting_s2.sh"):
            hits = [s for _, s in strings(d, 6) if re.search(
                r"(?i)(68013|fxload|Vend_Ax|0547|authorized mac|\bMAC\b.*reject|h264|bitrate|update_data|video_data|"
                r"/dev/mem|netlink|usb_bulk|insmod|FTP|ftpput)", s)]
            hits = [re.sub(r"(-p )\S+", r"\1<redacted>", s) for s in hits]  # hard-coded credential in cam_server
            if hits:
                p(f"      {f}: " + " | ".join(h[:70] for h in hits[:12]))
    # kernel
    lnx = open(parts["lnx"], "rb").read()
    kh = [s for _, s in strings(lnx, 6) if re.search(r"(?i)(fpga|dji|spidev|uio)", s)]
    p(f"    lnx kernel: strings matching fpga|dji|spidev|uio: {len(kh)} {kh[:5]}")
    for pn in ("rom_fw", "dsp_fw"):
        dd = open(parts[pn], "rb").read()
        hh = [s for _, s in strings(dd, 6) if re.search(r"(?i)(chip_?id|\befuse|fpga|68013)", s)]
        p(f"    {pn}: chip_id/efuse strings {len(hh)} e.g. {hh[:3]}")
    return files


# ---- FPGA container ---------------------------------------------------------------------
def survey_fpga():
    cases = [("P3X m1900 (air)", os.path.join(UNP, "P3X_m1900", "m1900.depack.bin")),
             ("P3S m1900 (air)", os.path.join(UNP, "P3S_FW_V01.01.0008", "m1900_p3s.depack.bin")),
             ("C1 m2001 (ground, valid die, control)", os.path.join(UNP, "corpus_scan", "C1", "m2001.depack.bin"))]
    for label, f in cases:
        if not os.path.exists(f) or not os.path.exists(MISTRAL):
            p(f"  {label}: skipped (missing {f if not os.path.exists(f) else MISTRAL})")
            continue
        for model in ("5CEFA4U19I7", "5CEBA4U19C8"):
            r = subprocess.run([MISTRAL, "routes", model, f], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
            lines = r.stdout.decode().splitlines()
            ctrl = [l for l in lines if "CTRL." in l]
            chip = [l for l in lines if "CHIPID" in l.upper()]
            p(f"  {label} model {model}: routes {len(lines)}, CTRL-block routes {len(ctrl)}, CHIPID routes {chip}")
        r = subprocess.run([MISTRAL, "routes2", "5CEFA4U19I7", f], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
        p(f"  {label} model 5CEFA4U19I7: unresolved active routes (routes2) {len(r.stdout.splitlines())}")


# ---- main --------------------------------------------------------------------------------
def main():
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    dirs = unpack_variants()
    p("# air_survey  root=%s" % ROOT)

    p("\n## 1. P3X V01.11.0020 module table")
    mods = module_files(UNP, P3X)
    data = {}
    for m, f in mods.items():
        d = open(f, "rb").read()
        data[m] = d
        desc, ver = ini_desc(f)
        a, base = arch_of(m, d)
        p(f"{m} {len(d):>9} sha256:{sha(d)} ent64k={entropy(d[:65536]):.2f} ver={ver} | {desc} | {a}"
          + (f" | base={base:#x}" if base is not None else ""))
        if base is not None:
            const_scan(m, d, base)
            table_scan(d, base)
        if m not in ("m0100", "m0800", "m1900"):
            kw_scan(d)

    p("  m1700 identity-related strings: " + str([f"{o:#x} {t[:40]}" for o, t in strings(data['m1700'], 6)
                                                    if re.search(r"(?i)(Hardware version|Camera ID|Factory|EFL)", t)]))

    p("\n## 2. m1500 (FX2LP) detail")
    vid, pid, did, recs = parse_iic(data["m1500"])
    p(f"  iic VID={vid:#06x} PID={pid:#06x} DID={did:#06x}; load records {[(hex(a), len(x)) for a, x in recs]}")
    img = bytearray(0x10000)
    for a, x in recs:
        img[a:a + len(x)] = x
    regs = collections.OrderedDict()
    for k in range(0, 0x1000):
        if img[k] == 0x90 and img[k + 1] in (0xE6, 0xE7):
            regs.setdefault((img[k + 1] << 8) | img[k + 2], []).append(k)
    FX2 = {0xE600: "CPUCS", 0xE601: "IFCONFIG", 0xE602: "PINFLAGSAB", 0xE603: "PINFLAGSCD", 0xE604: "FIFORESET",
           0xE609: "FIFOPINPOLAR", 0xE60A: "REVID", 0xE60B: "REVCTL", 0xE670: "PORTACFG", 0xE678: "I2CS",
           0xE679: "I2DAT", 0xE67A: "I2CTL", 0xE6B8: "SETUPDAT0", 0xE740: "EP0BUF"}
    p("  DPTR immediates in E6xx/E7xx: " + ", ".join(f"{a:#06x}{'(' + FX2[a] + ')' if a in FX2 else ''}" for a in regs))
    p("  REVID(0xE60A) read: %s; I2C/EEPROM regs (0xE678-0xE67A) used: %s" % (
        0xE60A in regs, any(a in regs for a in (0xE678, 0xE679, 0xE67A))))
    dd = bytes(img)
    k = dd.find(bytes([0x12, 0x01, 0x00, 0x02]))
    p("  device descriptor @%#x: %s (iManufacturer=%d iProduct=%d iSerialNumber=%d)" % (
        k, dd[k:k + 18].hex(), dd[k + 14], dd[k + 15], dd[k + 16]))
    p("  strings: " + str([s for _, s in strings(data['m1500'], 4)] + [x.decode('utf-16le') for x in re.findall(rb'(?:[\x20-\x7e]\x00){4,}', data['m1500'])]))

    p("\n## 3. m0100 (camera SoC) P3X V01.11.0020")
    survey_m0100("P3X0020", mods["m0100"], deep=True)

    p("\n## 4. m1900 (air FPGA) and Mistral CHIPID check")
    d = data["m1900"]
    first = next(i for i, b in enumerate(d) if b != 0xFF)
    last = len(d) - 1
    while d[last] == 0xFF:
        last -= 1
    p(f"  m1900 used span {first:#x}..{last:#x} ({last - first + 1} B), entropy(used)={entropy(d[first:last + 1]):.2f}; "
      f"strings>=8: {[s for _, s in strings(d, 8)][:3]}")
    survey_fpga()

    p("\n## 5. variant cross-check (same module names)")
    ref = {m: sha(open(f, 'rb').read()) for m, f in mods.items()}
    for v, dd_ in dirs.items():
        if v == "P3X0020":
            continue
        mf = module_files(dd_)
        row = []
        for m, f in mf.items():
            b = open(f, "rb").read()
            row.append(f"{m}{'=' if ref.get(m) == sha(b) else '~'}")
        p(f"  {v}: " + " ".join(row))
    for v in ("P3X0006", "P3S0008", "P3C", "P3SE", "P3XW"):
        mf = module_files(dirs[v])
        p(f"\n### {v}")
        for m, f in mf.items():
            if m in ("m0100", "m0800", "m1900", "m0101"):
                continue
            b = open(f, "rb").read()
            a, base = arch_of(m, b)
            if base is not None and m in ("m0306", "m0400", "m0900", "m1700", "m1701", "m0305"):
                p(f"{m} ver={ini_desc(f)[1]} {a}")
                const_scan(m, b, base)
        if "m0100" in mf:
            survey_m0100(v, mf["m0100"], deep=(v in ("P3C",)))
        if "m1500" in mf:
            q = parse_iic(open(mf["m1500"], "rb").read())
            p(f"  m1500 iic PID={q[1]:#06x} DID={q[2]:#06x} identical-to-P3X={sha(open(mf['m1500'],'rb').read()) == ref['m1500']}")
        for m in ("m0700", "m2700"):
            if m in mf:
                b = open(mf[m], "rb").read()
                p(f"  {m} {ini_desc(mf[m])} size={len(b)} head={b[:4].hex()}")
                if b[:2] == b"\x1f\x8b":
                    import gzip
                    try:
                        g = gzip.decompress(b)
                        p(f"    gunzip -> {len(g)} B, keyword strings:")
                        kw_scan(g, cap=8)
                    except Exception as e:
                        p(f"    gunzip failed: {e}")
        if "m1900" in mf:
            b = open(mf["m1900"], "rb").read()
            p(f"  m1900 sha256:{sha(b)} identical-to-P3X={sha(b) == ref['m1900']}")

    with open(LOG, "w") as f:
        f.write("\n".join(_log) + "\n")


if __name__ == "__main__":
    main()
