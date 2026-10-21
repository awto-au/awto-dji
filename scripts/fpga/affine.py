import sys, re, collections

bt = sys.argv[1]

def mask_to_tt(valstr):
    # "8e08a901.8a100121" -> 64-bit int (hi.lo). bit i = f(input combo i)
    hi, lo = valstr.split(".")
    return (int(hi, 16) << 32) | int(lo, 16)

def anf_degree_profile(tt):
    # Fast Mobius transform over 6 vars (64 entries). Returns ANF coeff bits.
    a = [(tt >> i) & 1 for i in range(64)]
    for b in range(6):
        step = 1 << b
        for i in range(64):
            if i & step:
                a[i] ^= a[i ^ step]
    return a  # a[i] = ANF coeff of monomial whose vars = bits set in i

def popcount(x):
    return bin(x).count("1")

def classify(tt):
    a = anf_degree_profile(tt)
    max_deg = 0
    lin_terms = []          # indices of degree-1 monomials present
    const = a[0]
    nonlinear = False
    for i in range(64):
        if a[i]:
            d = popcount(i)
            if d >= 2:
                nonlinear = True
            elif d == 1:
                lin_terms.append(i)
            max_deg = max(max_deg, d)
    return nonlinear, const, lin_terms, max_deg

lut_re = re.compile(r'^s (LAB|MLAB)\.(\d+)\.(\d+):LUT_MASK\.(\d+)\s+([0-9a-f.]+)$')

affine = []          # (block, r, c, alm, nvars, const, terms)
total = 0
degree_hist = collections.Counter()
trivial = 0
with open(bt) as f:
    for line in f:
        m = lut_re.match(line.strip())
        if not m:
            continue
        total += 1
        block, r, c, alm, val = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
        tt = mask_to_tt(val)
        if tt == 0 or tt == (1 << 64) - 1:
            trivial += 1
            continue
        nonlinear, const, lin_terms, max_deg = classify(tt)
        degree_hist[max_deg] += 1
        if not nonlinear:
            affine.append((block, r, c, alm, len(lin_terms), const, lin_terms))

print(f"total LUT_MASK records: {total}  (trivial all-0/all-1: {trivial})")
print("max-ANF-degree histogram (non-trivial LUTs):")
for d in sorted(degree_hist):
    print(f"  degree {d}: {degree_hist[d]}")
print(f"\nAFFINE (XOR/parity) LUTs: {len(affine)}")
# scrambler taps are affine with >=2 real input vars (pure XOR of 2+ inputs)
multi = [x for x in affine if x[4] >= 2]
print(f"  of which XOR of >=2 inputs (candidate feedback taps): {len(multi)}")
byvars = collections.Counter(x[4] for x in affine)
print("  affine LUTs by #linear-input-vars:")
for k in sorted(byvars):
    print(f"    {k} vars: {byvars[k]}")
print("\nsample multi-input affine LUTs (block r c alm nvars const):")
for x in multi[:25]:
    print(f"  {x[0]}.{x[1]:03d}.{x[2]:03d}.{x[3]}  nvars={x[4]} const={x[5]}")
