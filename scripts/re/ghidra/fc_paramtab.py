# Find the FC parameter descriptor table: entries referencing g_config/g_real/g_debug name strings.
from ghidra.program.model.data import StringDataType
import jarray
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
listing=currentProgram.getListing(); mem=currentProgram.getMemory()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
# pick a few known param-name strings, find data refs (table entries)
samples=["g_config.go_home.fixed_go_home_altitude","g_config.fail_safe.protect_action","g_config.advanced_function.fail_safe_protection_enabled"]
for d in listing.getDefinedData(True):
    if not isinstance(d.getDataType(),StringDataType): continue
    try: s=str(d.getValue())
    except: continue
    if s and any(k in s for k in samples):
        sa=d.getAddress()
        print("string %s @ %s"%(s[:50], sa))
        for r in refm.getReferencesTo(sa):
            fa=r.getFromAddress()
            # dump the 24 bytes around the referencing location as a candidate descriptor
            o=fa.getOffset()
            buf=jarray.zeros(24,'b')
            try: mem.getBytes(A(o-8),buf)
            except: continue
            words=[(buf[i]&0xff)|((buf[i+1]&0xff)<<8)|((buf[i+2]&0xff)<<16)|((buf[i+3]&0xff)<<24) for i in range(0,24,4)]
            print("  ref@%s rtype=%s  words[-8..+16]: %s"%(fa, r.getReferenceType().getName(), ' '.join('%08x'%w for w in words)))
