#!/usr/bin/env python3
"""Read-only Intel i2400m/i6050 SBCF firmware band table candidate scanner."""
import argparse,collections,hashlib,json,re,struct
from pathlib import Path
C=struct.Struct('<4I')
OP={1:'READ',2:'WRITE',3:'JUMP',8:'SIGNED_JUMP',9:'HASH_PAYLOAD_ONLY'}
FREQ=(2300,2400,2404,2412,2422,2450,2462,2480,2483,2496,2500,2690,2700,3400,3500,3800)

def inspect(path):
    buf=path.read_bytes()
    if len(buf)<128: raise ValueError('BCF header too short')
    header=struct.unpack_from('<10I',buf)
    typ,hlen,version,module,vendor,date,total,key,modulus,exponent=header
    if typ!=6 or vendor!=0x8086 or version>>16!=1: raise ValueError('Not recognized as Intel BCF')
    stop=total*4; off=hlen*4
    if stop>len(buf) or not 128<=off<=stop: raise ValueError('Invalid BCF bounds')
    rec=[]; observations=[]; clusters=collections.defaultdict(list)
    for i in range(100000):
        if off+16>stop:raise ValueError('No final JUMP within image')
        word,addr,n,checksum=C.unpack_from(buf,off)
        if word & 0xffff0000!=0xcbbc0000:raise ValueError(f'Bad command at {off:#x}')
        op=word&15
        current={'offset':hex(off),'opcode':OP.get(op,'OTHER'),'target_addr':hex(addr),'size':n}
        rec.append(current)
        if op in (3,8):break
        start=off+16; end=start+n
        if end>stop:raise ValueError('Truncated command')
        if op==2:
            payload=buf[start:end]
            for v in FREQ:
                for scale in (1,10,100,1000,10000,1000000):
                    value=v*scale
                    if value>=2**32:continue
                    for endian,pattern in [('LE',struct.pack('<I',value)),('BE',struct.pack('>I',value))]:
                        at=0
                        while True:
                            idx=payload.find(pattern,at)
                            if idx<0:break
                            absolute=start+idx
                            if absolute%4==0:
                                clusters[absolute//128].append({'offset':hex(absolute),'mhz':v,'scale':scale,'endian':endian})
                            at=idx+1
            for m in re.finditer(rb'[ -~]{8,}',payload):
                txt=m.group().decode('ascii','replace')
                if re.search(r'freq|band|calib|channel|scan|pll|regulatory|radio|spectrum',txt,re.I):
                    observations.append({'offset':hex(start+m.start()),'text':txt[:140]})
        off=(end+3)&~3
    ranked=sorted(clusters.items(),key=lambda kv:len(set((x['mhz'],x['scale']) for x in kv[1])),reverse=True)
    return {'file':path.name,'bytes':len(buf),'sha256':hashlib.sha256(buf).hexdigest(),
            'header':{'module_id':module,'version':hex(version),'date':hex(date),'primary_image_bytes':stop,'key_bytes':key*4,'modulus_bytes':modulus*4,'exponent_bytes':exponent*4},
            'sections':rec,'candidate_frequency_clusters':[{'offset':hex(k*128),'hits':v[:20]} for k,v in ranked[:50]],
            'relevant_strings':observations[:100],
            'caveat':'Numeric matches are not proof of gating. Absence of matches does not exclude computed bounds, host policy, NVM RF calibration, or hardware RF filters.'}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('file',type=Path);ap.add_argument('--json',action='store_true');a=ap.parse_args()
    report=inspect(a.file);print(json.dumps(report,indent=2))
