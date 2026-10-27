# Jython: find a handler-registration function (callee that receives a function-pointer arg at
# many call sites), then dump (immediate args, handler) per site = the (set,id)->handler map.
from ghidra.program.model.lang import OperandType
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
listing=currentProgram.getListing(); sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
def is_fn(v):
    if not v or (v&1)==0: return False
    f=fm.getFunctionContaining(A(v&~1)); return f and f.getEntryPoint().getOffset()==(v&~1)
# For each call site, scan back up to 10 instrs for ldr rX,[pc,..] loading a fn ptr.
from collections import defaultdict
cand=defaultdict(list)
fcnt=fm.getFunctionCount()
it=fm.getFunctions(True)
for f in it:
    ep=f.getEntryPoint()
    insns=listing.getInstructions(f.getBody(),True)
    recent=[]  # (reg, value) fn-ptr loads
    consts={}  # reg->int const
    for ins in insns:
        mn=ins.getMnemonicString()
        # track ldr rX,[pc,#imm] -> pool value; and mov/movs rX,#imm
        if mn=="ldr" and ins.getNumOperands()>=2:
            try:
                reg=ins.getRegister(0)
                refs=ins.getReferencesFrom()
                val=None
                for r in refs:
                    if r.getReferenceType().isData():
                        try: val=currentProgram.getMemory().getInt(r.getToAddress())&0xffffffff
                        except: pass
                if reg is not None and val is not None:
                    consts[reg.getName()]=val
            except: pass
        elif mn in("mov","movs","movw") and ins.getNumOperands()>=2 and OperandType.isScalar(ins.getOperandType(1)):
            reg=ins.getRegister(0); sc=ins.getScalar(1)
            if reg is not None and sc is not None: consts[reg.getName()]=sc.getUnsignedValue()
        elif mn in("bl","blx") and ins.getNumOperands()>=1:
            # callee
            tgt=None
            for r in ins.getReferencesFrom():
                if r.getReferenceType().isCall(): tgt=r.getToAddress()
            if tgt is not None:
                args={k:v for k,v in consts.items() if k in("r0","r1","r2","r3")}
                fnptrs=[(k,v) for k,v in args.items() if is_fn(v)]
                if fnptrs:
                    cand[tgt.getOffset()].append((ins.getAddress().getOffset(),dict(args)))
            consts={}
# rank candidate register fns by number of fn-ptr-bearing call sites
ranked=sorted(cand.items(), key=lambda kv:-len(kv[1]))
print("candidate handler-register fns (callee: #sites with fn-ptr arg):")
for ep,sites in ranked[:8]:
    f=fm.getFunctionContaining(A(ep))
    print("  %#x %s : %d sites"%(ep, f.getName() if f else '?', len(sites)))
out=open(SC+"/fc_register_dump.txt","w")
for ep,sites in ranked[:3]:
    out.write("\n=== register fn %#x : %d sites ===\n"%(ep,len(sites)))
    for site,args in sites:
        out.write("  @%#x  %s\n"%(site, {k:hex(v) for k,v in sorted(args.items())}))
out.close(); print("dump -> fc_register_dump.txt")
