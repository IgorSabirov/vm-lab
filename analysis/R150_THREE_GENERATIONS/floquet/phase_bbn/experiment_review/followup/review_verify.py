"""Two reproducibility tests for E6. The physical test uses the strict four-arm result."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent/'results'
OBS = ['Yp','D_H','He3_H_late','Li7_H_late']


def read(p):
    return json.loads(p.read_text())


def strict_g(doc):
    assert doc['outputs']==OBS and doc['rtol']==1e-11
    curves=[]
    for arm in ('off','pulse'):
        x=[np.log([doc['cases'][k+'_'+arm][j] for j in OBS])
           for k in ['coupled','mediated','self_only','zero_contact']]
        curves.append(x[0]-x[1]-x[2]+x[3])
    return curves[1]-curves[0]


def check_strict(candidate):
    ref=strict_g(read(HERE/'results/conv_3.json'))
    x2=read(DATA/'conv_2.json')['intervention_on_graph_interaction_ln']
    x1=read(DATA/'conv_1.json')['intervention_on_graph_interaction_ln']
    floor=np.maximum(abs(ref-x2),abs(np.subtract(x2,x1)))
    assert np.all(floor>0)
    measured=strict_g(candidate)
    np.testing.assert_allclose(measured,candidate['intervention_on_graph_interaction_ln'],atol=2e-14,rtol=0)
    # A different sign or zero on an already resolved component always fails.
    resolved=(abs(ref)>5*floor)&(np.sign(ref)==np.sign(x1))&(np.sign(ref)==np.sign(x2))
    assert np.all(np.sign(measured[resolved])==np.sign(ref[resolved]))
    if np.any(abs(measured-ref)>floor):
        raise ValueError('Strict contrast differs by more than the measured componentwise convergence step')
    return dict(floor=floor.tolist(),resolved=resolved.tolist())


def bitwise(base,fine,strict):
    for a,b in [(base/'summary.json',DATA/'e6_base.json'),(fine/'summary.json',DATA/'e6_fine.json')]:
        assert a.read_bytes()==b.read_bytes(),str(a)
    with ZipFile(DATA/'e6_trajectories.zip') as arc:
        for n in arc.namelist():
            assert (fine/n).read_bytes()==arc.read(n),n
    assert strict.read_bytes()==(HERE/'results/conv_3.json').read_bytes(),'conv_3.json'


def physical(base,fine,strict):
    for path,filename in [(base,'e6_base'),(fine,'e6_fine')]:
        a=read(path/'summary.json');b=read(DATA/(filename+'.json'))
        assert a['outputs']==OBS and a['rtol']==b['rtol'] and a['cases'].keys()==b['cases'].keys()
        assert max(y['max_baryon_error'] for y in a['cases'].values())<1e-9
        for k,c in a['cases'].items():
            for obs in OBS:
                assert abs(np.log(c[obs]/b['cases'][k][obs]))<2e-6
        for o,pre in {'D':1e-10,'p_periodic':2e-9,'C_mean':1e-9,'z_MeV':1e-11}.items():
            assert all(row[o]['pre_max_abs']<=pre for row in a['signal'].values())
        peak=a['signal']['f1r1']['p_periodic']['peak']['value']
        ref=b['signal']['f1r1']['p_periodic']['peak']['value']
        assert abs(peak-ref)<5e-10
        assert abs(a['signal']['f1r0']['p_periodic']['final'])<1e-10
        assert abs(a['placebo']['decorrelated']['correlation_nD'])<=.05
        n=np.array([a['intervention_on_mixed_ln'],b['intervention_on_mixed_ln']])
        assert np.all(abs(n[0]-n[1])<np.array([5e-10,2e-8,2e-8,2e-8]))
    return check_strict(read(strict))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['bitwise','physical'],required=True)
    parser.add_argument('--base',type=Path,required=True,help='directory of coarse intervention.py run')
    parser.add_argument('--fine',type=Path,required=True,help='directory of fine intervention.py run')
    parser.add_argument('--strict',type=Path,required=True,help='convergence.py JSON at rtol 1e-11')
    args=parser.parse_args(argv)
    result=(bitwise if args.mode=='bitwise' else physical)(args.base,args.fine,args.strict)
    print(json.dumps({'status':'PASS','mode':args.mode,'numerical':result}))


if __name__=='__main__': main()
