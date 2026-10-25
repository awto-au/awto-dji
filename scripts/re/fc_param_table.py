#!/usr/bin/env python3
"""Extract the DJI FC (m0306) parameter table: name -> RAM address/type/size.
Entry = FlycExportParam2015 (60B): nameptr,valptr,valsize,type_id,limits(36B),attribute,callback
(layout from o-gs/dji-firmware-tools dji_flyc_param_ed.py). Run on the DECRYPTED m0306
(scripts/re/xv4_decrypt.py). Usage: python3 scripts/re/fc_param_table.py m0306_dec.bin"""
import sys,struct
d=open(sys.argv[1],'rb').read(); B=0x08020000; E=B+len(d)
def cstr(va):
    o=va-B
    if not(0<=o<len(d)): return None
    e=d.find(b'\0',o); s=d[o:e]
    return s.decode() if 2<len(s)<80 and all(32<=c<127 for c in s) else None
inram=lambda v:0x20000000<=v<0x20030000 or 0x10000000<=v<0x10010000
sz=60; i=0; rows=[]
while i<len(d)-sz:
    npv,vpv,vsize,tid=struct.unpack_from('<IIII',d,i)
    nm=cstr(npv) if B<=npv<E else None
    if nm and inram(vpv): rows.append((vpv,nm,tid,vsize)); i+=sz
    else: i+=4
print("addr\tname\ttype_id\tsize")
for a,nm,tid,s in rows: print("%#010x\t%s\t%d\t%d"%(a,nm,tid,s))
