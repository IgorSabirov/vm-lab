"""Verify an exact GitHub-response cache and independently analyze window blocks.

Input: JSON with repository, run_id, source_commit, result_commit and files mapping
full repository paths to {encoding, content}, fetched at result_commit only.
Usage: python audit.py CACHE.json OUTPUT_DIR
No VM access, trajectory evolution, or exporter import.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.integrate import simpson

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
try:
    from infra.github_result_reader import read_github_result
except ModuleNotFoundError:
    from github_result_reader import read_github_result

REPOSITORY='IgorSabirov/vm-lab'
SOURCE='29fe4496485c17e935b2e2ffa9c88b7d75ba6efe'
RESULT='8e796057bd0bb0870aa3ea41b323b68620771c67'
RUN='E002c_WINDOW_EXPORT_v001_r001'
PAIRS=[(0,1),(1,2),(0,2)]
COHERENCES=[(1,2),(5,6),(1,4),(3,6),(2,4)]


def encoded(z):
    return [float(np.real(z)),float(np.imag(z))]


def operators(mask):
    h=np.zeros((8,8))
    for state in range(8):
        for edge,(a,b) in enumerate(PAIRS):
            qa,qb=1<<(2-a),1<<(2-b)
            if mask&(1<<edge) and bool(state&qa)!=bool(state&qb):
                h[state,state^qa^qb]=1.
    n_sink=np.diag([int(bool(s&1)) for s in range(8)])
    current=1j*(h@n_sink-n_sink@h)
    sector=[np.diag([int(s.bit_count()==n) for s in range(8)]) for n in (1,2)]
    h_one=h[np.ix_([4,2,1],[4,2,1])]
    sink=np.array([[0.,0.,1.]])
    constraints=np.vstack([sink,sink@h_one,sink@h_one@h_one])
    _,singular,vh=np.linalg.svd(constraints,full_matrices=True)
    rank=np.count_nonzero(singular>1e-10*max(1.,singular[0]))
    dark=vh[rank:].T@vh[rank:]
    reachable={2}
    for _ in range(3):
        reachable|={j for i in list(reachable) for j in range(3) if h_one[i,j]!=0}
    iso=np.diag([int(i not in reachable) for i in range(3)])
    return [p@current@p for p in sector],iso,dark-iso


def main():
    started=time.monotonic()
    cache=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
    for k,v in dict(repository=REPOSITORY,source_commit=SOURCE,result_commit=RESULT,run_id=RUN).items():
        assert cache[k]==v,(k,cache[k])
    def fetch(repository,path,ref):
        assert repository==REPOSITORY and ref==RESULT
        row=cache['files'][path]
        return base64.b64decode(row['content']) if row['encoding']=='base64' else row['content'].encode()
    verified=read_github_result(fetch,repository=REPOSITORY,result_commit=RESULT,run_id=RUN,source_commit=SOURCE)
    assert verified['execution_succeeded']
    artifacts=verified['artifacts'];report=verified['report'];job=report['job']
    actual=job['finished']-job['started']
    runtime=dict(expected_seconds=5.,actual_seconds=actual,deviation_seconds=actual-5.,
                 allowed_seconds=[0.,65.],gate='PASS' if 0<=actual<=65 else 'REVIEW_REQUIRED',
                 worker_queue_seconds=job['started']-job['created'])
    assert runtime['gate']=='PASS'
    metrics=json.loads(artifacts['files/metrics.json']);checks=json.loads(artifacts['files/checks.json'])
    assert checks['failures']==[] and checks['inputs_unchanged'] and checks['anchors_pass']
    assert metrics['identity']=={'run_id':RUN,'source_commit':SOURCE}
    assert metrics['work']==dict(models=3,source_time_points_per_model=101,window_time_points_per_model=6,matrix_blocks=162,new_trajectories=0,integration_steps=0,rhs_calls=0)
    manifest=json.loads(artifacts['files/data_manifest.json'])
    for item in manifest['exported']:
        data=artifacts['files/'+item['path']]
        assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
    errors=[];models={};times=np.arange(190.,201.,2.)
    mean=lambda a:simpson(a,x=times,axis=0)/10
    def check(a,b):
        e=float(np.max(abs(np.asarray(a)-np.asarray(b))));errors.append(e)
        assert e<1e-10,e
    for label in ('QS','IC','RR'):
        with np.load(io.BytesIO(artifacts[f'files/windows/{label}.npz']),allow_pickle=False) as z:
            data={k:z[k] for k in z.files}
        assert np.array_equal(data['time'],times) and data['blocks'].shape==(6,9,8,8)
        anchor=next(s for s in metrics['sources'] if s['label']==label)['github_T200_anchors']
        for k in ('blocks','series','diagnostics'):
            assert hashlib.sha256(np.ascontiguousarray(data[k][-1]).tobytes()).hexdigest()==anchor[k+'_T200']
        masks=[]
        for m in range(8):
            block=data['blocks'][:,m+1]
            p=np.trace(block,axis1=-2,axis2=-1).real
            currents,iso,inter=operators(m)
            h1,h2=[np.einsum('tij,ji->t',block,op).real for op in currents]
            one=block[:,[4,2,1]][:,:,[4,2,1]]
            isolated=np.einsum('tij,ji->t',one,iso).real
            interference=np.einsum('tij,ji->t',one,inter).real
            c=block[:,2,4];h=h1+h2
            for k,v in dict(p=p,h=h,j=h/p,h_N1=h1,h_N2=h2,isolated_N1=isolated,interference_N1=interference,C01=c,c01=c/p).items():
                check(v,data[k][:,m])
            row=dict(mask=m,p=float(mean(p)),h=float(mean(h)),j_effective=float(mean(h)/mean(p)),
                     mean_j=float(mean(h/p)),h_N1=float(mean(h1)),h_N2=float(mean(h2)),
                     isolated_N1=float(mean(isolated)),interference_N1=float(mean(interference)),
                     C01=encoded(mean(c)),c01_effective=encoded(mean(c)/mean(p)),mean_c01=encoded(mean(c/p)),
                     rho_entries={f'{i},{j}':encoded(mean(block[:,i,j])) for i,j in COHERENCES},
                     effective_conditional_rho_entries={f'{i},{j}':encoded(mean(block[:,i,j])/mean(p)) for i,j in COHERENCES},
                     mean_conditional_rho_entries={f'{i},{j}':encoded(mean(block[:,i,j]/p)) for i,j in COHERENCES})
            for k,v in metrics['models'][label]['masks'][m].items():check(row[k],v)
            masks.append(row)
        means={k:sum(r[k] for r in masks) for k in ['h','h_N1','h_N2','isolated_N1','interference_N1']}
        means.update({f'abs_c01_eff_m{m}':float(np.linalg.norm(masks[m]['c01_effective'])) for m in (6,7)})
        for k,v in means.items():check(v,metrics['models'][label]['means'][k])
        extrema={}
        values={k:data[k].sum(axis=1) for k in ['h','h_N1','h_N2','isolated_N1','interference_N1']}
        values.update({f'abs_c01_m{m}':abs(data['c01'][:,m]) for m in (6,7)})
        for key,v in values.items():
            row=dict(minimum=float(v.min()),maximum=float(v.max()),range=float(np.ptp(v)),count=6,
                     time_of_minimum=float(times[v.argmin()]),time_of_maximum=float(times[v.argmax()]))
            for k,x in row.items():check(x,metrics['models'][label]['extrema'][key][k])
            extrema[key]=row
        models[label]=dict(means=means,masks=masks,extrema=extrema)
    comparisons={}
    for label in ('IC','RR'):
        q,r=models['QS'],models[label];gap=q['means']['h']-r['means']['h']
        pop=sum((a['p']-b['p'])*(a['j_effective']+b['j_effective'])/2 for a,b in zip(q['masks'],r['masks']))
        cond=sum((a['p']+b['p'])*(a['j_effective']-b['j_effective'])/2 for a,b in zip(q['masks'],r['masks']))
        check(pop+cond,gap)
        result=dict(gap=gap,relative_gap=gap/q['means']['h'],population_share=pop/gap,
                    conditional_current_share=cond/gap,N2_share=(q['means']['h_N2']-r['means']['h_N2'])/gap,
                    mask_total_variation=sum(abs(a['p']-b['p']) for a,b in zip(q['masks'],r['masks']))/2)
        for k,v in result.items():check(v,metrics['comparisons']['QS-'+label][k])
        comparisons['QS-'+label]=result
    output=dict(repository=REPOSITORY,result_commit=RESULT,source_commit=SOURCE,run_id=RUN,runtime=runtime,
                verified_artifact_count=len(artifacts),verified_artifact_bytes=sum(map(len,artifacts.values())),
                max_independent_absolute_error=max(errors),independent_comparisons=len(errors),
                current_method='i[H,n_sink] projected into N=1 and N=2; no exporter formulas imported',
                dark_method='N=1 Hamiltonian observability-kernel SVD and sink graph reachability',
                averaging='scipy.integrate.simpson on six points [190,200], divided by 10',
                complex_encoding='[real,imaginary]',models=models,comparisons=comparisons,
                local_audit_seconds=time.monotonic()-started)
    (out/'audit.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k not in ['models']},indent=2))
    print(json.dumps({k:v['means'] for k,v in models.items()},indent=2))


if __name__=='__main__':main()
