"""Source-only data provenance and assembled channel inventory; no BBN solve."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from run import PIN, digest, dump

p=argparse.ArgumentParser(); p.add_argument('--upstream',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
a=p.parse_args(); root=a.upstream.resolve()
assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==PIN
sys.path.insert(0,str(root))
from primat.config import PRIMATConfig
from primat.network_data import UpdateNuclearRates

profiles=[]
for name,params,expected in [('P0',{'network':'small'},(8,13)),('P1',{'network':'large','amax':8},(12,67)),('P2',{'network':'large'},(59,428))]:
    cfg=PRIMATConfig(params|{'use_numba':False,'rate_grid_npts':4000})
    nucl=UpdateNuclearRates(cfg); eras=[]
    assert (len(nucl._lt_net.species),len(nucl._lt_net.names))==expected
    for label,net in [('MT',nucl._mt_net),('LT',nucl._lt_net)]:
        channels=[]
        for i,n in enumerate(net.names):
            f=Path(net.files[i]) if net.files[i] else None
            channels.append({'name':n,'equation':net.reaction_equation(i),'weak':i in net.weak_indices,
                             'source':net.sources[i],'path':str(f.relative_to(root)) if f else None,
                             'digest':digest(f) if f else None,'reverse_abg':(None if i in net.weak_indices else net._abg[i-sum(j<i for j in net.weak_indices)].tolist()),
                             'transform':'entire assembled RHS and analytic Jacobian divided by f(T), using unscaled base weak callbacks',
                             'units':'assembled dY/dt in s^-1; original rate units/density powers preserved inside kernel',
                             'reverse':'upstream detailed balance/capping preserved before common factor',
                             'status':'STRUCTURAL_COVERAGE_NOT_PER_CHANNEL_PHYSICAL_DERIVATION'})
        eras.append({'era':label,'species':net.species,'channels':channels,'reverse_clamp':label=='LT'})
    profiles.append({'profile':name,'params':params,'HT':'n/p forward and reverse callbacks each divided once; includes neutron decay','eras':eras,'executed':False})
files=[]
for path in subprocess.check_output(['git','-C',str(root),'ls-files','primat/data'],text=True).splitlines():
    f=root/path
    if f.is_file(): files.append({'path':path,**digest(f)})
dump(a.out/'RATE_COVERAGE.json',{'upstream_commit':PIN,'profiles':profiles,'optional_post_BBN_decay_era':False,'P2':'inventory only; not launch scope'})
dump(a.out/'UPSTREAM_DATA_MANIFEST.json',{'upstream_commit':PIN,'storage':'hashes and paths only; no copied tables','files':files})
print(json.dumps({'profiles':[(x['profile'],len(x['eras'][1]['channels'])) for x in profiles],'data_files':len(files)}))
