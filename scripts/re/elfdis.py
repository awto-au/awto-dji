# usage: elfdis.py ELF SYMBOL|0xADDR [N]  - ARM-mode disasm with symbol + literal annotation
import sys,subprocess,struct,re
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
from capstone.arm import ARM_REG_PC,ARM_OP_MEM
elf=sys.argv[1]; d=open(elf,'rb').read()
syms={}; byname={}
for l in subprocess.run(['readelf','-sW',elf],capture_output=True,text=True).stdout.splitlines():
    p=l.split()
    if len(p)>=8 and p[3] in('FUNC','OBJECT') and p[1]!='00000000':
        a=int(p[1],16); syms.setdefault(a&~1,p[7]); byname[p[7]]=(a&~1,int(p[2],0) if p[2].isdigit() else int(p[2],16))
segs=[]
for l in subprocess.run(['readelf','-lW',elf],capture_output=True,text=True).stdout.splitlines():
    p=l.split()
    if p and p[0]=='LOAD': segs.append((int(p[2],16),int(p[1],16),int(p[4],16)))
def off(a):
    for v,o,sz in segs:
        if v<=a<v+sz: return a-v+o
def rd(a): o=off(a); return struct.unpack_from('<I',d,o)[0] if o is not None else None
objs=sorted((a,n) for n,(a,s) in byname.items())
def name(v):
    if v in syms: return syms[v]
    import bisect
    i=bisect.bisect_right(objs,(v,'~'))-1
    if i>=0:
        a,n=objs[i]; sz=byname[n][1]
        if a<=v<a+max(sz,1): return f'{n}+{v-a:#x}'
    o=off(v)
    if o is not None:
        e=d.find(b'\0',o)
        s=d[o:e]
        if 3<len(s)<120 and all(32<=c<127 or c in (9,10) for c in s): return repr(s.decode())
    return None
t=sys.argv[2]
start,size=(byname[t] if t in byname else (int(t,16),0))
n=int(sys.argv[3]) if len(sys.argv)>3 else None
md=Cs(CS_ARCH_ARM,CS_MODE_ARM); md.detail=True
end=start+(size or 4*(n or 60))
for i in md.disasm(d[off(start):off(end)],start):
    note=''
    if i.mnemonic in('bl','b','blx') and i.op_str.startswith('#'):
        tgt=int(i.op_str[1:],16); note=name(tgt) or ''
    for op in i.operands:
        if op.type==ARM_OP_MEM and op.mem.base==ARM_REG_PC:
            la=i.address+8+op.mem.disp; v=rd(la)
            nm=name(v) if v is not None else None
            note=f'={v:#x}'+(f' {nm}' if nm else '')
    print(f'{i.address:08x}: {i.mnemonic:8} {i.op_str:30} {("; "+note) if note else ""}')
