#!/usr/bin/env python3
"""Report Shannon entropy across Intel WiMAX SBCF payloads. Read-only; no firmware copied."""
import argparse, collections, hashlib, json, math, struct
from pathlib import Path

CMD=struct.Struct("<4I")
def entropy(data):
    if not data: return 0.0
    h=collections.Counter(data)
    n=len(data)
    return round(-sum((v/n)*math.log2(v/n) for v in h.values()),5)

def inspect(path,blocksize):
    b=path.read_bytes()
    if len(b)<128:raise ValueError("short BCF")
    words=struct.unpack_from("<10I",b)
    typ,headlen,version,module,vendor,date,image_size,keysize,modulus,exponent=words
    if typ!=6 or vendor!=0x8086 or version>>16!=1:
        raise ValueError("not supported Intel BCF")
    image_end=image_size*4
    if image_end>len(b):raise ValueError("bad image length")
    off=headlen*4
    segments=[]
    for i in range(100000):
        if off+16>image_end:raise ValueError("no jump")
        opword,addr,n,cksum=CMD.unpack_from(b,off)
        if (opword&0xffff0000)!=0xcbbc0000:raise ValueError(f"bad command at {off:#x}")
        opcode=opword&15
        if opcode in (3,8):break
        end=off+16+n
        if end>image_end:raise ValueError("out of bounds")
        if opcode==2 and n:
            s=b[off+16:end]
            blocks=[{"offset":hex(off+16+j),"entropy":entropy(s[j:j+blocksize]),
                     "ascii_frac":round(sum(32<=x<127 for x in s[j:j+blocksize])/len(s[j:j+blocksize]),4)}
                    for j in range(0,len(s),blocksize)]
            segments.append({"target":hex(addr),"file_offset":hex(off+16),"length":n,
                             "entropy":entropy(s),"ascii_fraction":round(sum(32<=x<127 for x in s)/len(s),4),
                             "first_32_hex":s[:32].hex(),"blocks":blocks})
        off=(end+3)&~3
    all_blocks=[x["entropy"] for s in segments for x in s["blocks"]]
    return {"name":path.name,"size":len(b),"sha256":hashlib.sha256(b).hexdigest(),
            "whole_file_entropy":entropy(b),
            "header_entropy":entropy(b[:min(len(b),128)]),"blocksize":blocksize,
            "num_segments":len(segments),"min_block_entropy":min(all_blocks) if all_blocks else None,
            "max_block_entropy":max(all_blocks) if all_blocks else None,
            "segments":segments,
            "interpretation":"Entropy can distinguish low/high information density but cannot establish encryption, compression or CPU ISA alone."}

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("path",type=Path)
    a.add_argument("--blocksize",type=int,default=4096)
    x=a.parse_args()
    print(json.dumps(inspect(x.path,x.blocksize),indent=2))
