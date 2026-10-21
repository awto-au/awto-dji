import sys, re, collections

path = sys.argv[1]
edges = []            # (src, dst) raw tokens
with open(path) as f:
    for line in f:
        line = line.split(";")[0].strip()   # drop package-pin comment
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        edges.append((parts[0], parts[1]))

def kind(tok):
    # block-pin token looks like LAB.r.c.n:PIN or DSP.r.c:PIN ; routing node like H6.r.c.idx
    return tok.split(".")[0]

# population by block type among block-pin tokens (those containing ':')
blockpin = collections.Counter()
ff_cells = set()
lut_outs = set()
for a, b in edges:
    for tok in (a, b):
        if ":" in tok:
            bt = kind(tok)
            pin = tok.split(":", 1)[1]
            blockpin[(bt, pin.split(".")[0])] += 1
            # FF output pins in Cyclone V ALM: FFT0/FFT1/FFB0/FFB1 (+ 'L' variants)
            if bt in ("LAB", "MLAB") and pin.startswith("FF"):
                ff_cells.add(tok)
            if bt in ("LAB", "MLAB") and pin in ("COMBOUT", "COMBOUT0", "COMBOUT1"):
                lut_outs.add(tok)

print("total edges:", len(edges))
print("distinct FF output pins:", len(ff_cells))
print("distinct LUT combout pins:", len(lut_outs))
print("\ntop block-pin (blocktype, pinbase) counts:")
for (bt, pin), c in blockpin.most_common(30):
    print(f"  {bt:6} {pin:12} {c}")
