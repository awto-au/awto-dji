import sys, re, collections

routes = sys.argv[1]
gpio_re = re.compile(r'GPIO\.(\d+)\.(\d+)\.(\d+):(\w+)(?:\.(\d+))?')

inputs = {}   # pin -> pkg   (DATAIN appears as SOURCE: pin drives fabric)
outputs = {}  # pin -> pkg   (DATAOUT appears as DEST: fabric drives pin)
pkg_of = {}

with open(routes) as f:
    for line in f:
        body, _, pkg = line.rstrip("\n").partition(";")
        pkg = pkg.strip()
        toks = body.split()
        if len(toks) < 2:
            continue
        src, dst = toks[0], toks[1]
        ms = gpio_re.match(src)
        md = gpio_re.match(dst)
        if ms and ms.group(4) == "DATAIN":
            pin = (int(ms.group(1)), int(ms.group(2)), int(ms.group(3)))
            inputs[pin] = pkg or inputs.get(pin, "")
            if pkg: pkg_of[pin] = pkg
        if md and md.group(4) == "DATAOUT":
            pin = (int(md.group(1)), int(md.group(2)), int(md.group(3)))
            outputs[pin] = pkg or outputs.get(pin, "")
            if pkg: pkg_of[pin] = pkg

def pkgsort(p):
    # split letters+digits of a BGA ball like 'AA17'
    m = re.match(r'([A-Z]+)(\d+)', p)
    return (m.group(1), int(m.group(2))) if m else (p, 0)

print(f"TRUE FPGA inputs  (DATAIN drives fabric): {len(inputs)}")
print(f"TRUE FPGA outputs (fabric drives DATAOUT): {len(outputs)}")

named_in = sorted([pkg_of[p] for p in inputs if p in pkg_of], key=pkgsort)
named_out = sorted([pkg_of[p] for p in outputs if p in pkg_of], key=pkgsort)
print(f"\ninputs with package ball ({len(named_in)}):")
print("  " + " ".join(named_in))
print(f"\noutputs with package ball ({len(named_out)}):")
print("  " + " ".join(named_out))

# cluster input balls by row-letter to hint at physical bus grouping
byrow = collections.defaultdict(list)
for p in named_in:
    m = re.match(r'([A-Z]+)(\d+)', p)
    if m: byrow[m.group(1)].append(int(m.group(2)))
print("\ninput balls grouped by BGA row-letter (bus hint):")
for row in sorted(byrow):
    nums = sorted(byrow[row])
    print(f"  row {row:3}: {len(nums):2} pins  cols {nums}")
