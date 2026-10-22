import sys, struct

d = open(sys.argv[1], "rb").read()
n = len(d)

# AD9361 SPI: 16-bit command = R/W(bit15) | bytes(bit14-12) | addr(bit9-0, 0x000-0x3FF).
# A static init table is typically either:
#   - address words in 0x0000-0x03FF, or
#   - write-command words in 0x8000-0x83FF (1-byte write = 0x8000|addr),
# appearing densely over a run.
def in_addr(v):  return v <= 0x03FF
def in_wcmd(v):  return 0x8000 <= v <= 0x83FF

def scan(pred, label):
    runs = []
    i = 0
    while i + 2 <= n:
        v = struct.unpack_from("<H", d, i)[0]
        if pred(v):
            j = i
            cnt = 0
            while j + 2 <= n and pred(struct.unpack_from("<H", d, j)[0]):
                cnt += 1
                j += 2
            if cnt >= 16:
                runs.append((i, cnt))
            i = j
        else:
            i += 2
    runs.sort(key=lambda r: -r[1])
    print(f"[{label}] candidate runs (>=16 consecutive u16): {len(runs)}")
    for off, cnt in runs[:6]:
        vals = [struct.unpack_from("<H", d, off + 2 * k)[0] for k in range(min(cnt, 12))]
        print(f"  @0x{off:06x} len={cnt}: " + " ".join(f"{v:04x}" for v in vals))

scan(in_addr, "addr 0x000-0x3FF")
scan(in_wcmd, "wcmd 0x8000-0x83FF")

# Also: (addr_u16_LE, val_u8) records with addr in range, high density over a window.
best = (0, 0)
for base in range(0, n - 300, 1):
    ok = 0
    for k in range(100):
        o = base + 3 * k
        if o + 2 > n:
            break
        a = struct.unpack_from("<H", d, o)[0]
        if a <= 0x3FF:
            ok += 1
    if ok > best[1]:
        best = (base, ok)
print(f"[addr,val triple] best window @0x{best[0]:06x}: {best[1]}/100 records have addr<=0x3FF")
