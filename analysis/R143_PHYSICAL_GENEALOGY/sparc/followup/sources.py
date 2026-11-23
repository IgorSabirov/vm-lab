"""Extract published numerical covariates and donor scores, without rotation-curve fits."""
import argparse
import hashlib
import io
import re
import tarfile
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import pandas as pd
p=argparse.ArgumentParser()
p.add_argument('source_dir',type=Path)
src=p.parse_args().source_dir
out=Path(__file__).resolve().parent
def tex(archive, member):
    with tarfile.open(src/archive) as t:
        return t.extractfile(member).read().decode()
numeral=r'[-+]?\d+(?:\.\d+)?'
def numbers(s):
    return [float(x) for x in re.findall(numeral,s)]
env={}
for line in tex('chae20tex','ms_r2.tex').splitlines():
    fields=line.strip().split('&')
    name=fields[0].split('$')[0].strip()
    if len(fields)==9 and re.fullmatch(r'[A-Za-z0-9-]+',name) and name!='galaxy':
        vs=numbers(fields[3])
        if len(vs)==3:
            env[name]={'e20':vs[0],'e20_lo':vs[1],'e20_hi':vs[2]}
assert len(env)==153
count=0
for line in tex('chae_tex','RCLSSr1.tex').splitlines():
    cells=line.strip().split('&')
    if len(cells)==3 and r'\pm' in cells[1] and r'\pm' in cells[2]:
        name=cells[0].strip()
        env.setdefault(name,{}).update(log_eN_max=numbers(cells[1])[0],log_eN_no=numbers(cells[2])[0])
        count+=1
assert count==109
pd.DataFrame.from_dict(env,orient='index').rename_axis('Galaxy').sort_index().to_csv(out/'environment.csv')
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with ZipFile(src/'suppdoc') as z:
    root=ET.fromstring(z.read('word/document.xml'))
rows=[]
for tab in root.findall('.//w:tbl',ns):
    for tr in tab.findall('w:tr',ns):
        cells=[''.join(t.text or '' for t in c.findall('.//w:t',ns)) for c in tr.findall('w:tc',ns)]
        if len(cells)==10 and cells[0]!='Galaxy' and all(re.fullmatch(numeral+x,cells[i]) for i,x in [(1,''),(6,''),(7,'')]):
            rows.append((cells[0],int(cells[1]),float(cells[6]),float(cells[7])))
assert len(rows)==len(set(x[0] for x in rows))==175
pd.DataFrame(rows,columns=['Galaxy','n','chi_p1','chi_p075']).to_csv(out/'S11_scores.csv',index=False)
print('Independent environment and published per-galaxy classifications:',len(env),len(rows))
