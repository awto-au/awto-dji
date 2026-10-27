import struct,sys,hashlib,os
d=open(sys.argv[1],'rb').read(); out=sys.argv[2]
hl=struct.unpack_from('<H',d,6)[0]; n=struct.unpack_from('<H',d,0x2c)[0]
for i in range(n):
    o=0x40+i*0x34
    tid,=struct.unpack_from('<B',d,o)
    ver,off,ln,al=struct.unpack_from('<IIII',d,o+4)
    name='m%02d%02d'%(tid&0x1f,tid>>5)
    blob=d[off:off+ln]
    print(name,hex(off),ln,hashlib.sha256(blob).hexdigest()[:16])
    if name=='m0900': open(os.path.join(out,'P3X_FW_V01.11.0020_m0900.bin'),'wb').write(blob)
