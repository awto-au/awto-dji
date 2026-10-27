# usage: fx3dis.py FLAT START N  (ARM mode, base 0x40000000; annotates literal pool loads)
import sys,struct
from capstone import *
from capstone.arm import ARM_REG_PC,ARM_OP_MEM
img=open(sys.argv[1],'rb').read(); B=0x40000000
a=int(sys.argv[2],16); n=int(sys.argv[3])
md=Cs(CS_ARCH_ARM,CS_MODE_ARM); md.detail=True
def rd(x): return struct.unpack_from('<I',img,x-B)[0] if 0<=x-B<len(img)-3 else None
def s(v):
    if v and B<=v<B+len(img):
        o=v-B; e=img.find(b'\0',o); t=img[o:e]
        if 3<len(t)<80 and all(32<=c<127 for c in t): return repr(t.decode())
    return ''
for i in md.disasm(img[a-B:a-B+4*n],a):
    note=''
    for op in i.operands:
        if op.type==ARM_OP_MEM and op.mem.base==ARM_REG_PC:
            v=rd(i.address+8+op.mem.disp); note=f'={v:#x} {s(v)}' if v is not None else ''
    print(f'{i.address:08x}: {i.mnemonic:8} {i.op_str:32} {"; "+note if note else ""}')
