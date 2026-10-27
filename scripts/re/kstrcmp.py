# usage: kstrcmp.py BINARY OUT_TSV SRC_ROOT... : like strcmp.py, but indexes only the C string
# literals (adjacent/continued literals joined) of large trees, for speed.
import re,sys,os,subprocess
lit=re.compile(r'"((?:[^"\\\n]|\\.)*)"')
parts=[]
for d in sys.argv[3:]:
    for root,_,fs in os.walk(d):
        if '/Documentation' in root or '/scripts' in root: continue
        for f in fs:
            if not f.endswith(('.c','.h','.S')): continue
            t=open(os.path.join(root,f),errors='replace').read()
            t=re.sub(r'"\s*\\?\s*\n\s*"','',t)
            t=re.sub(r'"\s+"','',t)
            parts.extend(m.group(1) for m in lit.finditer(t))
blob='\x00'.join(parts).replace('\\"','"').replace('\\t','\t').replace('\\n','\n')
META=re.compile(r'GCC: \(|^Linux version')
out=subprocess.run(['strings','-n','12',sys.argv[1]],capture_output=True,text=True).stdout.splitlines()
msgs=[s for s in out if ' ' in s.strip() and re.search('[a-zA-Z]{4}',s) and not META.search(s)]
miss=[]
for s in msgs:
    s0=re.sub(r'^(<\d>)?\s*[A-Za-z0-9_.-]+( (Error|Warning|Debug|error|warning))?: (%s: )?','',s)
    runs=[r.strip() for r in re.split(r'%[-+ #0-9.lhz]*[a-zA-Z]|<\d>|[\n\t]|: |=>',s0)]
    key=max(runs,key=len)
    if len(key)>=10 and key not in blob: miss.append(s)
print(f'# {os.path.basename(sys.argv[1])}: {len(msgs)} messages, {len(msgs)-len(miss)} in reference, {len(miss)} not')
open(sys.argv[2],'w').write('\n'.join(miss)+'\n')
