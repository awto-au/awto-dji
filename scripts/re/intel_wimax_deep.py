#!/usr/bin/env python3
"""Analyze Intel SBCF frequency constants and map them to firmware load addresses.
Read-only. No firmware bytes are committed or uploaded.
"""
import argparse,collections,json,re,struct,hashlib
from pathlib import Path

CENTERS=(2300,2400,2404,2412,2422,2450,2462,2480,2483,2496,2500,2690,2700,3400,3500,3800)

def get_sections(b):
    hdr=struct.unpack_from("<10I",b)
    assert hdr[0]==6 and hdr[4]==0x8086, "Unknown container"
    off=hdr[1]*4
    end=hdr[6]*4
    out=[]
    jump=None
    while off+16<=end:
        cmd,addr,n,cksum=struct.unpack_from("<4I",b,off)
        if cmd>>16!=0xcbbc:raise ValueError("Unexpected boot command "+hex(off))
        op=cmd&15
        if op in (3,8):
            jump={"op":op,"target":hex(addr),"file_offset":hex(off)}
            break
        if off+16+n>end:raise ValueError("size overflow")
        if op==2:out.append({"file_start":off+16,"file_end":off+16+n,"target":addr,"size":n})
        off=((off+16+n+3)//4)*4
    return out,jump

def inspect(p):
    b=p.read_bytes()
    sections,jump=get_sections(b)
    results=[]
    groups=collections.defaultdict(list)
    for sec in sections:
        data=b[sec["file_start"]:sec["file_end"]]
        for center in CENTERS:
            target_value=center*1000
            tag=struct.pack("<I",target_value)
            pos=0
            while 1:
                loc=data.find(tag,pos)
                if loc<0:break
                if loc%4==0:
                    offset=sec["file_start"]+loc
                    groups[(offset//256)*256].append((offset,center,sec["target"]+loc,sec))
                pos=loc+1
    ranked=sorted(groups.values(),key=lambda a:len(set(v[1] for v in a)),reverse=True)
    for vals in ranked[:25]:
        for offset,center,memory,sec in sorted(vals):
            lo=max(sec["file_start"],offset-48)
            hi=min(sec["file_end"],offset+80)
            bytes_local=b[lo:hi]
            words=[]
            start=sec["file_start"]+((lo-sec["file_start"]+3)//4)*4
            for i in range(start,hi-3,4):
                val=struct.unpack_from("<I",b,i)[0]
                words.append({"file_offset":hex(i),"u32":val,"hex":hex(val),"freq_MHz":val/1000 if 2000000<=val<=6000000 else None})
            results.append({"freq_mhz":center,"file_offset":hex(offset),"load_address":hex(memory),
                            "section_base":hex(sec["target"]),
                            "nearby_dwords":words,"byte_context_hex":bytes_local.hex()})
    notable=[]
    pat=re.compile(rb'[ -~]{10,}')
    search=re.compile(r'arc|thread|rtos|ucos|frequency|freq|band|rf\b|pll|calibrat|startScan|stopScan|l1fw|scanparam|chipset|cpu|dsp|mips|arm|vendor|oscillator|unsupported|invalid|tuning|radio|regulator|3gpp|802\.',re.I)
    for sec in sections:
        data=b[sec["file_start"]:sec["file_end"]]
        for m in pat.finditer(data):
            v=m.group().decode("ascii","replace")
            if search.search(v):
                notable.append({"at":hex(sec["file_start"]+m.start()),
                                "load":hex(sec["target"]+m.start()),
                                "text":v[:200]})
    # Separate candidate 2450 if found; 2450 literal can be legal channel or a guard condition.
    return {"name":p.name,"sha256":hashlib.sha256(b).hexdigest(),
            "jump":jump,"sections":len(sections),
            "frequency_groups":len(ranked),"frequency_instances":results,
            "notable_strings_count":len(notable),"notable_strings":notable[:160],
            "caveat":"Constants alone cannot identify comparisons, hardware permissions or runtime acceptance."}

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("file",type=Path)
    a=ap.parse_args()
    print(json.dumps(inspect(a.file),indent=2))
