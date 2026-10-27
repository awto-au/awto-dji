# usage: strcmp.py BINARY SRC_DIR... : human-readable messages in BINARY (contain a space,
# >=12 chars) whose longest literal run (split on printf specs / newlines) is absent from
# every file under the source dirs. Prints counts + the missing messages.
import re,sys,os,subprocess
src=[]
for d in sys.argv[2:]:
    for root,_,fs in os.walk(d):
        for f in fs:
            if f.endswith(('.c','.h','.cfg','.xs','.S','.tci','.cpp','.txt','.sh','.mak')) or f in ('Makefile','Kconfig'):
                try: src.append(open(os.path.join(root,f),errors='replace').read())
                except OSError: pass
blob=re.sub(r'"\s*\\?\s*\n\s*"','','\n'.join(src))  # join adjacent C literals
blob=blob.replace('\\"','"').replace('\\t','\t')
out=subprocess.run(['strings','-n','12',sys.argv[1]],capture_output=True,text=True).stdout.splitlines()
META=re.compile(r'^(vermagic|author|description|license|alias|depends|srcversion)=|GCC: \(|built on |^\s*File /|^@\(#\)')
msgs=[s for s in out if ' ' in s.strip() and re.search('[a-zA-Z]{4}',s) and not s.startswith(('parm','--cpu')) and not META.search(s.strip())]
miss=[]
for s in msgs:
    s0=re.sub(r'^(<\d>)?\s*[A-Za-z0-9_]+( (Error|Warning|Debug|error|warning))?: (%s: )?','',s)
    runs=[r.strip() for r in re.split(r'%[-+ #0-9.]*[a-zA-Z]+|\\n|<\d>|[\n\t]',s0)]
    key=max(runs,key=len)
    if len(key)>=8 and key not in blob: miss.append(s)
print(f'# {os.path.basename(sys.argv[1])}: {len(msgs)} messages, {len(msgs)-len(miss)} found in reference, {len(miss)} not')
for s in miss: print('   ',s)
