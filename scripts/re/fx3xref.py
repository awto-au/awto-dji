# fx3xref.py FLAT : builds function starts (push..lr) and call graph; helpers importable
import sys,struct,bisect
from capstone import *
from capstone.arm import ARM_REG_PC,ARM_OP_MEM
img=open(sys.argv[1],'rb').read(); B=0x40000000; LO,HI=0x40003000,0x40024000
md=Cs(CS_ARCH_ARM,CS_MODE_ARM); md.detail=True
ins={}
for a in range(LO,HI,4):
    for i in md.disasm(img[a-B:a-B+4],a): ins[a]=i
starts=sorted(a for a,i in ins.items() if i.mnemonic in('push','stmdb') and 'lr' in i.op_str)
def fn(a): k=bisect.bisect_right(starts,a)-1; return starts[k] if k>=0 else None
calls={}   # callee -> [(site, caller fn)]
for a,i in ins.items():
    if i.mnemonic in('bl','b','blx') and i.op_str.startswith('#'):
        t=int(i.op_str[1:],16)
        if i.mnemonic=='b' and fn(t)==fn(a): continue
        calls.setdefault(t,[]).append((a,fn(a)))
    for op in i.operands:
        if op.type==ARM_OP_MEM and op.mem.base==ARM_REG_PC:
            v=struct.unpack_from('<I',img,a+8+op.mem.disp-B)[0]
            if LO<=v<HI and (v in set(starts) or v-1 in set(starts)): calls.setdefault(v&~1,[]).append((a,fn(a),'ptr'))
if __name__=='__main__':
    for t in map(lambda x:int(x,16),sys.argv[2:]):
        f=fn(t); print(f'{t:#x} in fn {f:#x}' if f else hex(t))
        for c in calls.get(f,[]): print('    called from',hex(c[0]),'fn',hex(c[1]) if c[1] else None, c[2] if len(c)>2 else '')
