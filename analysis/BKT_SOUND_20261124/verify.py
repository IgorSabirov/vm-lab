"""Fail on altered measurements, inconsistent decisions, or failed model controls."""
import hashlib
import json
import zipfile
import numpy as np
from scipy.integrate import quad
from model import ROOT, STARTS, SEED, inputs, osc, response, statistics, physical, write_json
from replay import s4, at_boundary
from thermodynamics import rows, eos_inversion

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def verify():
    meta=json.loads((ROOT/'data'/'manifest.json').read_text())
    archive=ROOT/'data'/'cambridge.zip'
    assert digest(archive.read_bytes())==meta['archive_sha256']
    key=(ROOT/'preregistration'/'reveal.json').read_bytes()
    assert digest(key)==(ROOT/'preregistration'/'seal.sha256').read_text().split()[0]
    key=json.loads(key)['map']
    records=json.loads((ROOT/'results'/'BLIND.json').read_text())
    with zipfile.ZipFile(archive) as z:
        for item in meta['tables']:
            assert digest(z.read(item['path']))==item['sha256']
        assert len(meta['tables'])==11
        for label, entry in key.items():
            assert (ROOT/'data'/f'{label}.txt').read_bytes()==z.read(entry['member'])
    total=2*quad(lambda t:t*osc(t,.78,.47),0,np.inf)[0]
    assert abs(total-1)<1e-9
    # Near a sharp resonance the denominator tends to 4δ²+Γ².
    g=.0001; w=.8
    rat=osc(w+g/2,w,g)/osc(w,w,g)
    assert abs(rat-.5)<1e-4
    # S4 at fixed x and w²/G converges pointwise in a finite measurement band.
    rate=.3; amp=.24; freq=np.linspace(.1,2.,20); width=1e5
    w0=np.sqrt(rate*width)
    finite=(np.pi*amp*w0**2)*osc(freq,w0,width)
    diff=amp*rate*freq/(freq**2+rate**2)
    assert np.max(abs(finite/diff-1))<1e-5
    sims={}
    for label in records:
        t,y,e=inputs(label); a=records[label]
        target=np.array([1.25,.56,.43,.70,.34]); artificial=response(t,target)
        cost,params=s4(t,artificial,e,STARTS)
        assert cost<1e-10 and np.allclose(params,target,atol=1e-5)
        p=np.asarray(a['p_internal']); ep=np.asarray(a['edge_params'])
        starts=np.vstack([p,ep,STARTS])
        assert abs(np.sum(((response(t,p)-y)/e)**2)-a['chi2'])<1e-7
        assert np.allclose(physical(p),a['physical'])
        assert all(abs(v[0]-a['LR'])<1e-4 for k,v in a['multistart_LR'].items() if k!='independent_scipy')
        # Cross-check native fits on random observations, not just the two best-fit curves.
        rng=np.random.default_rng(SEED+100)
        ysim=response(t,ep)+rng.normal(size=(12,len(t)))*e
        _,_,free,edge=statistics(t,e,ysim,starts)
        gaps=[]
        for i,yn in enumerate(ysim):
            extra=np.vstack([starts,free[i,1:],edge[i,1:]])
            fc,_=s4(t,yn,e,extra); bc,_=at_boundary(t,yn,e,extra)
            gaps.append(max(abs(free[i,0]-fc),abs(edge[i,0]-bc)))
        sims[label]={'sample_size':len(gaps),'median_objective_gap':np.median(gaps),
                     'maximum_objective_gap':max(gaps),'above_0_05':sum(gap>.05 for gap in gaps)}
        assert np.median(gaps)<.01
        count=a['bootstrap_above_observed']
        assert a['p_boot']==(count+1)/1000
    thermal=rows(); assert len(thermal)==9 and sum(row['S'] is not None for row in thermal)==6
    # Forward both branches of the hydrodynamic quartic from a known EOS.
    c10sq,c20sq,gamma,thermal_speed_sq,D=2.,.6,1.3,1.1,7.
    roots=np.sqrt(np.sort(np.roots([1.,-(c10sq+c20sq),c10sq*c20sq/gamma])))
    result=eos_inversion(*roots[::-1],c10sq,gamma,thermal_speed_sq,D)
    assert np.allclose(result,D*c20sq/(c20sq+thermal_speed_sq))
    return {'archive_SHA256':meta['archive_sha256'],'source_tables':11,'panel_files_byte_identical':True,
            'salted_key_verified':True,'unit_two_sided_fsum':total,'weak_damping_half_height':rat,
            'S4_to_S5_max_relative_error':np.max(abs(finite/diff-1)),'noise_free_recovery_both_grids':True,
            'independent_optimizer_synthetic_check':sims,'EOS_synthetic_roundtrip':result,
            'matched_temperature_rows':len(thermal),'two_sound_rows':6,'all_assertions_passed':True}

if __name__=='__main__':
    write_json(ROOT/'results'/'CHECKS.json',verify())
