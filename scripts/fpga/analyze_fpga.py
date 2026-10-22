import sys, collections, math

d = open(sys.argv[1], "rb").read()
n = len(d)
first = next((i for i, b in enumerate(d) if b != 0xFF), 0)
last = n - 1
while last > 0 and d[last] == 0xFF:
    last -= 1
print(f"total={n} first_nonFF=0x{first:x} last_nonFF=0x{last:x} used={last-first+1}")
print("first 64 bytes:", d[first:first + 64].hex())

print("\nentropy profile (64KB windows, showing low-entropy ones):")
off = first
while off <= last:
    w = d[off:off + 65536]
    c = collections.Counter(w)
    m = len(w) or 1
    e = -sum((v / m) * math.log2(v / m) for v in c.values())
    if e < 6.5 or off < first + 65536 * 4:
        print(f"  0x{off:07x} ent={e:4.2f} {'#' * int(e*4)}")
    off += 65536

for sig, name in [(b"Altera", "Altera"), (b"CycloneV", "CycloneV"),
                  (b"(c) 20", "copyright"), (b"\xaa\x99\x55\x66", "Xilinx-sync")]:
    i = d.find(sig)
    if i >= 0:
        print(f"found {name} at 0x{i:x}")
