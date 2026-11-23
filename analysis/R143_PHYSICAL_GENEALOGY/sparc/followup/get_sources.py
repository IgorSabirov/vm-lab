"""Retrieve the published inputs (no credentials); extract only the 15 relevant X-COP profiles."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from urllib.request import Request, urlopen

p=argparse.ArgumentParser()
p.add_argument('out',type=Path)
out=p.parse_args().out
out.mkdir(parents=True,exist_ok=True)
urls={
    'chae20tex':('https://arxiv.org/src/2009.11525','93a27f52b7fe080091b2bf2b617314eba3171fd1dc174dc43de3d735f9be9874'),
    'chae_tex':('https://arxiv.org/src/2109.04745','5898e3532909968c1ac4b05d37e043d519962e60246d83fe6751254dc1cfed9a'),
    'ohtex':('https://arxiv.org/src/1502.01281','71af16551af8316b17a8904de06917b4a2a9faa387d24155903f5b075df9a9d6'),
    'suppdoc':('https://ndownloader.figshare.com/files/68389459','fade456f7a6115ae10c70b09f011828c670696747efc024b5a58c1dc7a36d4c8'),
    'ohviz':('https://vizier.cfa.harvard.edu/viz-bin/asu-tsv?-source=J/AJ/149/180&-out.all&-out.max=unlimited',None),
    'sparcpos':('https://vizier.cfa.harvard.edu/viz-bin/asu-tsv?-source=J/AJ/152/157/table1&-out.all&-out.max=unlimited',None),
    'xcop-package.tgz':('https://drive.switch.ch/s/j3WUOYXWgv9Jbnz/download','0edf5038b419b70d070b73b22f4801e27f318b0854db61eec52142c27c140d94')}
def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()
for name,(url,sha) in urls.items():
    path=out/name
    if path.is_file() and (sha is None or digest(path)==sha):
        continue
    tmp=out/(name+'.part')
    with tmp.open('wb') as sink:
        if name=='xcop-package.tgz':
            length=315080566;step=4*1024**2
            for a in range(0,length,step):
                b=min(length,a+step)-1
                with urlopen(Request(url,headers={'Range':f'bytes={a}-{b}'}),timeout=120) as response:
                    if a==0 and response.status==200:
                        shutil.copyfileobj(response,sink)
                        break
                    assert response.getheader('Content-Range')==f'bytes {a}-{b}/{length}'
                    shutil.copyfileobj(response,sink)
        else:
            with urlopen(url,timeout=90) as response:
                shutil.copyfileobj(response,sink)
    if sha is not None and digest(tmp)!=sha:
        raise ValueError(f'Unexpected release checksum: {name}')
    tmp.replace(path)
expected=json.loads((Path(__file__).parent/'cluster_inputs.json').read_text())
with tarfile.open(out/'xcop-package.tgz') as archive:
    for g,files in expected.items():
        for name,sha in files.items():
            with archive.extractfile(g+'/'+name) as src:
                data=src.read()
            assert hashlib.sha256(data).hexdigest()==sha
            (out/name).write_bytes(data)
