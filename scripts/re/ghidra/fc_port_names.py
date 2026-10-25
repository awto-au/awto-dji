# Jython (part B of the string-anchored port): map upstream names into OUR V01.11.0020 image.
# Input: anchors.tsv (name, string_vaddr, string) from scripts/re/port_symbols.py.
# For each anchor, resolve string_vaddr -> the function to name:
#   * log-style string ("call X", "[SDK] X", "X: %d"): the CODE that loads the string is inside
#     the named function -> high confidence.
#   * bare-name string (string == name, a state-name table entry): the ref is a DATA pointer in a
#     {fn_ptr, name_ptr} table; read neighbouring words for a thumb code pointer -> medium.
# Emits our_addr/name/confidence/via to anchors_ported.tsv and applies high-confidence names.
from ghidra.program.model.symbol import SourceType
import struct
fm = currentProgram.getFunctionManager(); refm = currentProgram.getReferenceManager()
mem = currentProgram.getMemory()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
def u32(a):
    b = bytearray(4); mem.getBytes(A(a), b); return struct.unpack("<I", bytes(b))[0]

rows = []
for ln in open(SC + "/anchors_p3.tsv"):
    ln = ln.rstrip("\n")
    if not ln or ln.startswith("name\t"):
        continue
    p = ln.split("\t")
    if len(p) < 3:
        continue
    rows.append((p[0], int(p[1], 16), p[2]))

out = open(SC + "/anchors_ported.tsv", "w")
out.write("our_addr\tname\tconfidence\tvia\n")
applied = 0
for name, sva, s in rows:
    logstyle = (s.strip() != name)  # bare name table entry vs a log message
    refs = list(refm.getReferencesTo(A(sva)))
    funcs = []
    tablerefs = []
    for r in refs:
        fa = r.getFromAddress()
        f = fm.getFunctionContaining(fa)
        if f:
            funcs.append(f)
        else:
            tablerefs.append(fa)  # ref sits in data (a table)
    done = False
    if logstyle and funcs:
        # pick the function with fewest anchor-strings (avoid a shared logger); usually unique
        uniq = sorted(set(f.getEntryPoint().getOffset() for f in funcs))
        conf = "high" if len(uniq) == 1 else "med"
        fa = uniq[0]
        out.write("%#010x\t%s\t%s\tlog:%s\n" % (fa, name, conf, s[:40]))
        if conf == "high":
            f = fm.getFunctionContaining(A(fa))
            try:
                f.setName(name, SourceType.USER_DEFINED); applied += 1
            except: pass
        done = True
    if not done and tablerefs:
        # {fn_ptr, name_ptr} table: name_ptr lives at tableref; try neighbour words for a thumb fn.
        for ta in tablerefs:
            cand = None
            for off in (-4, 4, -8, 8):
                try:
                    w = u32(ta.getOffset() + off)
                except: continue
                if 0x08020000 <= (w & ~1) < 0x08120000 and (w & 1):  # thumb code pointer
                    fn = fm.getFunctionContaining(A(w & ~1))
                    if fn:
                        cand = fn.getEntryPoint().getOffset(); break
            if cand is not None:
                out.write("%#010x\t%s\tmed\ttable@%s\n" % (cand, name, ta))
                done = True; break
    if not done:
        out.write("-\t%s\tnone\t(no code ref / unresolved)\n" % name)
out.close()
print("ported -> anchors_ported.tsv ; applied %d high-confidence names" % applied)
