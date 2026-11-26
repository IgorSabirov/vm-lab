"""Reduce the per-case JSON records. Input may be an extracted run archive or a runner output tree."""
import argparse
from itertools import combinations,product
import json
from pathlib import Path
import numpy as np
from scipy.linalg import null_space
from runner import HERE, OBS
from scans import four, spec, label, STANDARD
from nuclear import hot_name


def rec(path):
    return json.loads(path.read_text())


def vec(d):
    return np.log([d[k] for k in OBS])


def quant(x):
    return dict(zip(('q025','median','q975'),np.quantile(x,[.025,.5,.975],axis=0).tolist()))


def calculate(raw):
    def get(group,name):
        return rec(raw/group/(name+'.json'))['result']
    def scan(s):return get('scans',label(s))
    def G(**kw):
        parts=[list(map(scan,four(a,**kw))) for a in (0.,.1)]
        def mix(rows):
            a,b,c,d=map(vec,rows)
            return a-b-c+d
        return mix(parts[1])-mix(parts[0])
    def peak(record,background,key,cold,hot):
        ts=np.array(record['trace']['Tgamma_MeV'])
        delta=np.subtract(record['trace'][key],background['trace'][key])
        i=int(np.argmax(abs(delta)))
        return dict(peak=delta[i],T_MeV=ts[i],final=delta[-1],pre=max(abs(delta[ts>hot])))
    def cases_at(window,amps):
        baseline=scan(spec())
        return {str(a):{'p':peak(scan(spec(a,window)),baseline,'p_periodic',*window),
                        'Y_D':peak(scan(spec(a,window)),baseline,'D',*window),
                        'delta_ln_y':(vec(scan(spec(a,window)))-vec(baseline)).tolist()} for a in amps}
    out={'observables':list(OBS)}
    out['windows']={str(w):cases_at(w,amps) for w,amps in [
        (STANDARD,[-.2,-.1,-.05,.05,.1,.2]),((.04,.05),[-.1,.1]),((.10,.13),[-.1,.1])]}
    out['lambda']={}
    for s in (.5,1.,2.):
        plus,minus=G(lam=s),G(lam=-s)
        out['lambda'][str(s)]=dict(G_plus=plus.tolist(),G_minus=minus.tolist(),
                                  odd=((plus-minus)/2).tolist(),even=((plus+minus)/2).tolist())
    out['lambda_zero']=G(lam=0.).tolist()
    out['forward_np_power']={str(k):G(power=k).tolist() for k in range(4)}
    out['memory']={}
    canonical=scan(spec())
    for tau,clock in product((10.,50.,200.),(.1,1.,10.)):
        off,live=[scan(spec(tau=tau,clock=clock,reverse=r)) for r in (False,True)]
        t=np.array(live['trace']['Tgamma_MeV'])
        p=np.subtract(live['trace']['p_periodic'],off['trace']['p_periodic'])
        z=np.subtract(live['trace']['z_MeV'],live['trace']['drive_MeV'])
        ix=np.argmax(abs(p))
        out['memory'][f'{tau:g},{clock:g}']=dict(delta_reverse_ln=(vec(live)-vec(off)).tolist(),
          relative_to_nominal_ln=(vec(live)-vec(canonical)).tolist(),p_reverse_peak=p[ix],
          peak_T=t[ix],z_minus_drive_at_80keV_MeV=np.interp(.08,t[::-1],z[::-1]))
    src=lambda s:get('ensemble',s)
    base=vec(src('original'));idv=vec(src('identity'))
    out['ensemble_controls']={k:(vec(src(k))-base).tolist() for k in ['identity','fourier_raw','iaaft_raw']}
    out['ensemble']={}
    for method in ('fourier','iaaft'):
        ds=[src(f'{method}_{i:03}') for i in range(100)]
        xs=np.array([vec(d)-idv for d in ds]); corr=np.array([d['corr_nD'] for d in ds])
        out['ensemble'][method]={'K':len(ds),'delta_ln_y_against_identity':quant(xs),
            'correlation_with_nD':quant(corr),'joint_correlation_of_ln_y_and_input_corr':[
            np.corrcoef(corr,x)[0,1] for x in xs.T],
            'seed0_smoothed_minus_raw_ln':(vec(ds[0])-vec(src(method+'_raw'))).tolist(),
            **{k:quant([row[k] for row in ds]) for k in ['raw_spectrum_error','joined_spectrum_error',
                  'raw_sorted_error_MeV','joined_sorted_error_MeV','sign_crossings']}}
    def hot(x): return vec(get('nuclear',hot_name(x)))
    out['hot']={}
    for h in (.5,1.):
        centre=hot([0,0,0]); dirs=h*np.eye(3);J=np.zeros((4,3));H=np.zeros((4,3,3))
        for i,d in enumerate(dirs):
            J[:,i]=(hot(d)-hot(-d))/(2*h/1000)
            H[:,i,i]=(hot(d)-2*centre+hot(-d))/(h/1000)**2
        for i,j in combinations(range(3),2):
            u,v=dirs[i],dirs[j]
            cross=(hot(u+v)-hot(u-v)-hot(-u+v)+hot(-u-v))/(2*h/1000)**2
            H[:,i,j]=H[:,j,i]=cross
        after=J[[0,2,3]]@null_space(J[[1]])
        s=np.linalg.svd(J,compute_uv=False);q=np.linalg.svd(after,compute_uv=False)
        out['hot'][str(h)]={'jacobian_per_MeV':J.tolist(),'hessian_per_MeV2':H.tolist(),
             'singular_values':s.tolist(),'condition':s[0]/s[-1],
             'D_matched_singular_values':q.tolist(),'D_matched_condition':q[0]/q[-1]}
    out['weak_derivative_per_keV']={}
    for coulomb,lifetime in product((0,1),repeat=2):
        minus,plus=[get('nuclear',f'weak_{coulomb}_{lifetime}_{s}') for s in (-1,1)]
        out['weak_derivative_per_keV'][f'fermi{coulomb}_lifetime{lifetime}']={
            k:(plus[k]-minus[k])/.6 for k in OBS}
    out['convergence']={'intervention_on_graph_interaction_ln':G(rtol=1e-11).tolist()}
    out['timing']={m:rec(raw/m/'_timing.json') for m in ('ensemble','scans','nuclear')}
    out['max_baryon_error']=max(rec(p)['result']['max_baryon_error'] for m in out['timing']
                                for p in (raw/m).glob('*.json') if not p.name.startswith('_'))
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('raw',type=Path);parser.add_argument('out',type=Path)
    a=parser.parse_args();a.out.write_text(json.dumps(calculate(a.raw),indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
