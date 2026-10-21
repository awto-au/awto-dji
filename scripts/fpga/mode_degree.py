import sys, re, collections

bt = sys.argv[1]

# Collect per (LAB,r,c, almidx): LUT_MASK, TMODE, BMODE, ARITH_SEL
mask = {}
tmode = {}
bmode = {}
arith = {}
pat = re.compile(r'^s (LAB|MLAB)\.(\d+)\.(\d+):(LUT_MASK|TMODE|BMODE|ARITH_SEL)\.(\d+)\s+(\S+)$')
with open(bt) as f:
    for line in f:
        m = pat.match(line.strip())
        if not m:
            continue
        key = (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(5)))
        field, val = m.group(4), m.group(6)
        if field == "LUT_MASK":
            hi, lo = val.split(".")
            mask[key] = (int(hi, 16) << 32) | int(lo, 16)
        elif field == "TMODE":
            tmode[key] = val
        elif field == "BMODE":
            bmode[key] = val
        elif field == "ARITH_SEL":
            arith[key] = val

def anf(tt):
    a = [(tt >> i) & 1 for i in range(64)]
    for b in range(6):
        s = 1 << b
        for i in range(64):
            if i & s:
                a[i] ^= a[i ^ s]
    return a

def maxdeg(tt):
    a = anf(tt)
    md = 0
    for i in range(64):
        if a[i]:
            d = bin(i).count("1")
            if d > md:
                md = d
    return md

# Also try interpreting the two 32-bit halves as two independent 5-input (32-entry) LUTs.
def maxdeg5(tt32):
    a = [(tt32 >> i) & 1 for i in range(32)]
    for b in range(5):
        s = 1 << b
        for i in range(32):
            if i & s:
                a[i] ^= a[i ^ s]
    md = 0
    for i in range(32):
        if a[i]:
            d = bin(i).count("1")
            if d > md:
                md = d
    return md

groups = collections.defaultdict(list)       # mode-tuple -> list of maxdeg(6var)
half_low = 0                                  # ALMs where BOTH 32-bit halves are low-degree(<=2)
half_total = 0
for key, tt in mask.items():
    g = (tmode.get(key, "?"), bmode.get(key, "?"), arith.get(key, "?"))
    groups[g].append(maxdeg(tt))
    lo = tt & 0xffffffff
    hi = tt >> 32
    half_total += 1
    if maxdeg5(lo) <= 2 and maxdeg5(hi) <= 2:
        half_low += 1

print("6-var interpretation: max-degree by (TMODE,BMODE,ARITH_SEL) mode, top groups:")
rows = []
for g, degs in groups.items():
    n = len(degs)
    mn = min(degs); mx = max(degs)
    avg = sum(degs) / n
    rows.append((n, g, mn, avg, mx))
rows.sort(reverse=True)
for n, g, mn, avg, mx in rows[:20]:
    print(f"  n={n:5}  T={g[0]:6} B={g[1]:6} AR={g[2]:8}  deg min/avg/max = {mn}/{avg:.1f}/{mx}")

print(f"\n5-var half-split interpretation: ALMs where BOTH 32-bit halves are affine-ish (deg<=2): {half_low}/{half_total}")

# And: count halves individually that are affine (deg<=1) or deg<=2
h_aff = 0; h_deg2 = 0; H = 0
for key, tt in mask.items():
    for half in (tt & 0xffffffff, tt >> 32):
        H += 1
        d = maxdeg5(half)
        if d <= 1: h_aff += 1
        elif d == 2: h_deg2 += 1
print(f"individual 32-bit halves: affine(deg<=1)={h_aff}  deg2={h_deg2}  total halves={H}")
