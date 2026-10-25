# usage: fx3img.py IMG OUTFLAT : parse Cypress FX3 "CY" boot image; write a flat RAM image
# (base 0x40000000, SYSMEM 512 KB) and print sections + entry.
import sys,struct
d=open(sys.argv[1],'rb').read()
assert d[:2]==b'CY', d[:4]
ctl,typ=d[2],d[3]; print(f'bImageCTL {ctl:#x} bImageType {typ:#x}')
o=4; secs=[]
while True:
    n,addr=struct.unpack_from('<II',d,o); o+=8
    if n==0: print(f'entry {addr:#010x}'); entry=addr; break
    secs.append((addr,d[o:o+4*n])); print(f'section {addr:#010x} len {4*n:#x}'); o+=4*n
chk=struct.unpack_from('<I',d,o)[0]; print(f'checksum {chk:#010x}, trailing {len(d)-o-4} bytes')
BASE=0x40000000; img=bytearray(0x80000)
itcm=bytearray(0x4000)
for a,b in secs:
    if a>=BASE: img[a-BASE:a-BASE+len(b)]=b
    else: itcm[a:a+len(b)]=b
open(sys.argv[2],'wb').write(img); open(sys.argv[2]+'.itcm','wb').write(itcm)
