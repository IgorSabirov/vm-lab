"""Replay the fixed supplied calculation blocks, including historical failures."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parent
INFILE=ROOT/'input/assignment.txt'
RANGES=[(35,37),(43,57),(150,190),(207,262),(273,331),(354,412),(417,467),
        (518,544),(594,636),(671,719),(757,805),(825,850),(1745,1805),
        (1831,1873),(1927,1983),(2028,2090),(2093,2148),(2209,2290),(2333,2379)]

def main():
    raw=INFILE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='693da0f6cc2d9e601540159e51cb672b1fbbc6d67303a29a187d9054597af402':
        raise ValueError('Source does not match the reviewed input')
    lines=raw.decode().split('\n')
    out=[]
    for a,b in RANGES:
        code='\n'.join(lines[a-1:b])
        p=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=90)
        out.append(dict(lines=[a,b],exit=p.returncode,stdout=p.stdout,stderr=p.stderr))
    (ROOT/'results'/'attachment_replay.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    print([(r['lines'][0],r['exit'],r['stderr'].splitlines()[-1:]) for r in out])

if __name__=='__main__': main()
