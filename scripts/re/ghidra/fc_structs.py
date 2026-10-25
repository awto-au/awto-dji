# Jython: define + apply core structs so members decompile as named fields.
from ghidra.program.model.data import (StructureDataType, ArrayDataType, ByteDataType,
    UnsignedShortDataType, UnsignedIntegerDataType, PointerDataType, Undefined1DataType, CategoryPath)
from ghidra.program.model.symbol import SourceType
from ghidra.program.model.listing import CodeUnit
dtm=currentProgram.getDataTypeManager(); mem=currentProgram.getMemory()
fm=currentProgram.getFunctionManager(); listing=currentProgram.getListing()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
U8=ByteDataType(); U16=UnsignedShortDataType(); U32=UnsignedIntegerDataType()
def ptr(): return PointerDataType()
cp=CategoryPath("/fc")
def mk(name,size):
    s=StructureDataType(cp,name,size); return s
def put(s,off,dt,nm,cmt=None):
    s.replaceAtOffset(off,dt,dt.getLength(),nm,cmt)

# --- DumlFrame (wire header; payload at 0x0b) ---
duml=mk("DumlFrame",0x0c)
put(duml,0x00,U8,"sof","0x55")
put(duml,0x01,U8,"len_lo")
put(duml,0x02,U8,"ver_len_hi","ver<<2 | len_hi")
put(duml,0x03,U8,"hdr_crc8")
put(duml,0x04,U8,"sender","devtype<<? ; low5=type")
put(duml,0x05,U8,"receiver","low5=devtype, high3=index")
put(duml,0x06,U16,"seq")
put(duml,0x08,U8,"cmd_type","ack/enc flags (&0x60,&0x1f)")
put(duml,0x09,U8,"cmd_set")
put(duml,0x0a,U8,"cmd_id")
put(duml,0x0b,U8,"payload0")
duml=dtm.addDataType(duml,None)

# --- CtrlAgency @0x20023664 ---
ag=mk("CtrlAgency",0x24)
put(ag,0x00,U8,"active","1 = a controller holds agency")
put(ag,0x03,U8,"holder_id","device type currently holding control")
put(ag,0x20,U8,"granted","grant latch")
ag=dtm.addDataType(ag,None)

# --- CtrlMode @0x200001d5 (active_device then src_flags) ---
cm=mk("CtrlMode",0x04)
put(cm,0x00,U8,"active_device","winning control source code; ==2 => API/nav")
put(cm,0x01,U8,"src_flags","bit1=src1, bit2=API/nav eligible")
cm=dtm.addDataType(cm,None)

# --- FlycExportParam (60B table entry) ---
pp=mk("FlycExportParam",60)
put(pp,0x00,ptr(),"nameptr"); put(pp,0x04,ptr(),"valptr"); put(pp,0x08,U32,"valsize"); put(pp,0x0c,U32,"type_id")
put(pp,0x10,ArrayDataType(U8,36,1),"limits"); put(pp,0x34,U32,"attribute"); put(pp,0x38,ptr(),"callback")
pp=dtm.addDataType(pp,None)

def apply_at(addr,dt):
    try:
        clearListing(A(addr),A(addr+dt.getLength()-1))
        createData(A(addr),dt)
        return True
    except Exception as e:
        print("  apply fail %#x: %s"%(addr,e)); return False

ok=0
if mem.getBlock(A(0x20023664)) and apply_at(0x20023664,ag): ok+=1
if mem.getBlock(A(0x200001d5)) and apply_at(0x200001d5,cm): ok+=1
# param table array (808 entries) at 0x080ab66c
arr=ArrayDataType(pp,808,60)
if apply_at(0x080ab66c,arr): ok+=1
print("structs applied at globals: %d"%ok)

# retype param_1 of two raw-frame handlers to DumlFrame*
for a in (0x08044d2a,0x08044dfa):
    f=fm.getFunctionContaining(A(a))
    if f and f.getParameterCount()>=1:
        try: f.getParameter(0).setDataType(dtm.getPointer(duml),SourceType.USER_DEFINED); print("  retyped arg0 of %s -> DumlFrame*"%f.getName())
        except Exception as e: print("  retype fail %s: %s"%(f.getName(),e))
print("done")
