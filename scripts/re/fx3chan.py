# Decode every CyU3PDmaChannelCreate(handle, type, &cfg) call: tiny constant tracker over
# the 48 instructions before each call (literal loads, mov/movw/orr/add imm, stores to sp).
import sys,struct
from capstone import *
from capstone.arm import ARM_REG_PC,ARM_OP_MEM,ARM_OP_IMM,ARM_OP_REG
img=open(sys.argv[1],'rb').read(); B=0x40000000; CREATE=0x40012b84
md=Cs(CS_ARCH_ARM,CS_MODE_ARM); md.detail=True
TYPES=['AUTO','AUTO_SIGNAL','MANUAL','MANUAL_IN','MANUAL_OUT','AUTO_MANY_TO_ONE','AUTO_ONE_TO_MANY','MANUAL_MANY_TO_ONE','MANUAL_ONE_TO_MANY','MULTICAST']
def sk(v):
    if v is None: return '?'
    if 0x100<=v<=0x11f: return f'FPGA(PIB{v-0x100})'
    if 0x300<=v<=0x30f: return f'USB EP{v-0x300} IN (to phone)'
    if 0x400<=v<=0x40f: return f'USB EP{v-0x400} OUT (from phone)'
    return {0x3f00:'CPU (consumes)',0x3f01:'CPU (produces)'}.get(v,hex(v))
def rd(x): return struct.unpack_from('<I',img,x-B)[0]
calls=[a for a in range(0x40003000,0x40023000,4) for i in md.disasm(img[a-B:a-B+4],a) if i.mnemonic=='bl' and i.op_str==f'#{CREATE:#x}']
for c in calls:
    regs={}; mem={}
    for i in md.disasm(img[c-B-4*48:c-B],c-4*48):
        ops=i.operands; m=i.mnemonic
        if m.startswith('bl'): regs={k:v for k,v in regs.items() if k not in('r0','r1','r2','r3','ip','lr')}; continue
        if not ops or ops[0].type!=ARM_OP_REG: 
            continue
        d=i.reg_name(ops[0].reg)
        if m=='ldr' and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC: regs[d]=rd(i.address+8+ops[1].mem.disp)
        elif m in('mov','movw','mvn') and ops[1].type==ARM_OP_IMM: regs[d]=(~ops[1].imm if m=='mvn' else ops[1].imm)&0xffffffff
        elif m=='mov' and ops[1].type==ARM_OP_REG: 
            s=i.reg_name(ops[1].reg); regs[d]=regs.get(s)
        elif m in('orr','add') and len(ops)==3 and ops[2].type==ARM_OP_IMM:
            s=i.reg_name(ops[1].reg)
            if s=='sp': regs[d]=('sp',ops[2].imm)
            elif isinstance(regs.get(s),int): regs[d]=(regs[s]|ops[2].imm) if m=='orr' else regs[s]+ops[2].imm
            else: regs.pop(d,None)
        elif m in('str','strh','strb') and ops[1].type==ARM_OP_MEM and i.reg_name(ops[1].mem.base)=='sp':
            v=regs.get(d); off=ops[1].mem.disp
            if isinstance(v,int):
                n={'str':4,'strh':2,'strb':1}[m]
                for k in range(n): mem[off+k]=(v>>(8*k))&0xff
        elif m in ('ldr','ldrh','ldrb'): regs.pop(d,None)
    cfg=regs.get('r2'); h=regs.get('r0'); t=regs.get('r1')
    if isinstance(cfg,tuple):
        base=cfg[1]
        g=lambda off,n: (int.from_bytes(bytes(mem[base+off+k] for k in range(n)),'little') if all(base+off+k in mem for k in range(n)) else None)
        size,count,prod,cons=g(0,2),g(2,2),g(4,2),g(6,2)
    else: size=count=prod=cons=None
    tn=TYPES[t] if isinstance(t,int) and t<len(TYPES) else f'type={t}'
    print(f'{c:#x}: handle {h if not isinstance(h,int) else hex(h)}  {tn:12} {sk(prod):24} -> {sk(cons):24} buf {size if size is None else hex(size)} x {count}')
