"""Audit pinned GitHub E002b files; no VM reads and no dynamical runs.

Usage: python audit.py DOWNLOADED_RUN --output audit.json
The directory must contain run.json, output.log, files/, and source/ fetched
from the two immutable commits below. Also fetch source/infra's reader and
verify_e002b_report.py from SOURCE_COMMIT; infra is not a VM input.
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from scipy.integrate import simpson

RESULT = '8adfd0564884bdb4b7b2adad7bad2ea5435d25b8'
SOURCE = '556736fd5c6b23c22b24751accab63932a7c4825'
RUN = 'E002b_FEAS_GH_v001_r001'
EDGES = ['01','12','02']


def algebra():
    """Finite operator identities for two nodes and one edge, dimension 12."""
    eye2=np.eye(2);eye4=np.eye(4);eye3=np.eye(3)
    up=np.array([[0,0],[1,0]],dtype=complex);n=up@up.T.conj()
    n0=np.kron(n,eye2);n1=np.kron(eye2,n)
    x=np.kron(up,up.T.conj())+np.kron(up.T.conj(),up)
    C=np.diag([0,1,1,0]);Q=C/2
    p0,pr,pl=[np.diag([float(k==a) for k in range(3)]) for a in range(3)]
    bp=np.zeros((3,3));bp[2,1]=1;bm=bp.T
    N=np.kron(n1,eye3);PL=np.kron(eye4,pl)
    hh=np.kron(x,pl);hf=.5*np.kron(Q,bp+bm)
    cur=1j*(hh@N-N@hh)
    dephased_cur=sum(np.kron(eye4,p)@cur@np.kron(eye4,p) for p in [p0,pr,pl])
    a,b=.7,.3
    lp=np.sqrt(a)*np.kron(C,bp);lm=np.sqrt(b)*np.kron(C,bm)
    def adj(L,O):
        A=L.T.conj()@L
        return L.T.conj()@O@L-(A@O+O@A)/2
    def maximum(x):return float(np.max(np.abs(x)))
    identities={
        'edge_dephasing_leaves_hop_operator':maximum(cur-dephased_cur),
        'hop_is_PL_times_node_current':maximum(cur-np.kron(1j*(x@n1-n1@x),pl)),
        'BL_plus_ML_is_PL_single':maximum(np.kron((C+x)/2,pl)+np.kron((C-x)/2,pl)-np.kron(C,pl)),
        'BL_minus_ML_is_PL_real_hop':maximum(np.kron((C+x)/2,pl)-np.kron((C-x)/2,pl)-np.kron(x,pl)),
        'H_form_Q_commutes_with_node_population':maximum(hf@N-N@hf),
        'IC_preserves_node_population_directly':maximum(adj(lp,N)+adj(lm,N)),
        'IC_forward_population_rate':maximum(adj(lp,PL)-a*np.kron(C,pr)),
        'IC_reverse_population_rate':maximum(adj(lm,PL)+b*np.kron(C,pl)),
    }
    assert max(identities.values())<1e-14
    node_x=np.kron(np.kron(up+up.T.conj(),eye2),eye3)
    backaction=maximum(adj(lp,node_x)+adj(lm,node_x))
    assert backaction>0
    return {'identity_residuals':identities,'IC_effect_on_node_superposition_operator':backaction,
            'meaning':'Population preservation does not imply no coherence backaction. Pinching edge coherences at fixed rho leaves instantaneous hop unchanged.'}


def audit(root):
    receipt=json.loads((root/'run.json').read_text());m=json.loads((root/'files/metrics.json').read_text())
    cfg=json.loads((root/'source/config.json').read_text());assert cfg==m['protocol']
    actual=receipt['job']['finished']-receipt['job']['started'];f=cfg['runtime_forecast']
    assert f['lower_seconds']<=actual<=f['upper_seconds']
    sys.path.insert(0,str(root/'source/infra'))
    from github_result_reader import read_github_result
    from verify_e002b_report import verify
    def fetch(repo,path,ref):
        assert repo=='IgorSabirov/vm-lab' and ref==RESULT
        assert path.startswith('results/'+RUN+'/')
        return (root/path.removeprefix('results/'+RUN+'/')).read_bytes()
    v=read_github_result(fetch,repository='IgorSabirov/vm-lab',result_commit=RESULT,run_id=RUN,source_commit=SOURCE)
    assert v['execution_succeeded']
    assert receipt['full_data_inventory_errors']==[]
    for path,digest in receipt['input_sha256'].items():
        assert hashlib.sha256((root/'source'/path).read_bytes()).hexdigest()==digest,path
    for name,path in [('config_sha256','config.json'),('target_sha256',cfg['target_file'])]:
        assert hashlib.sha256((root/'source'/path).read_bytes()).hexdigest()==m[name]
    csv_check=verify(root/'files')
    manifest=json.loads((root/'files/data_manifest.json').read_text())
    ia={r['path']:r['bytes'] for r in receipt['full_data']}
    ib={r['vm_path']:r['bytes'] for r in manifest['full_files']}
    assert len(ia)==len(receipt['full_data'])==len(ib)==len(manifest['full_files']) and ia==ib
    checks=json.loads((root/'files/checks.json').read_text());assert all(c['passed'] for c in checks)
    def arrays(folder,cid):
        with (root/'files'/folder/(cid+'.csv')).open(newline='') as stream:rows=list(csv.DictReader(stream))
        return {k:np.array([float(r[k]) for r in rows]) for k in rows[0]}
    refs={};series={};snapshot_count=0;mh={r['vm_path']:r for r in manifest['full_files']}
    for cid,c in m['cases'].items():
        arr=arrays('pre',cid);t=arr['time'];series[cid]=arrays('series',cid)
        refs[cid]={k:float(simpson(y,x=t)/(t[-1]-t[0])) for k,y in arr.items() if k!='time'}
        assert c['records']==1001 and len(c['snapshots'])==7 and c['stationarity']['passed']
        for s in c['snapshots']:
            key='results/'+RUN+'/full/'+s['path']
            assert mh[key]['sha256']==s['sha256']
            snapshot_count+=1
    assert snapshot_count==56
    public_refinement={}
    for variant in cfg['models']:
        largest=0.
        for folder in ['pre','series']:
            a=arrays(folder,variant+'_coarse');b=arrays(folder,variant+'_fine')
            assert a.keys()==b.keys()
            for key in a:
                assert a[key].shape==b[key].shape
                if key!='time':largest=max(largest,float(np.max(abs(a[key]-b[key]))))
        assert largest<=cfg['acceptance']['refinement_observables']
        assert largest<=m['refinements'][variant]['max_observable_delta']+1e-12
        public_refinement[variant]=largest
    pairs={}
    for candidate in ['QS','QQ']:
        a=refs[candidate+'_fine'];b=refs['RR_'+candidate+'_fine'];h=a['I_hop_sink'];hr=b['I_hop_sink'];gap=h-hr
        edges={}
        for e in EDGES:
            pa,pb=a['pL'+e],b['pL'+e];u=a['B_L'+e]+a['M_L'+e];w=b['B_L'+e]+b['M_L'+e]
            edges[e]={
                'candidate_hop':a['I_hop'+e],'control_hop':b['I_hop'+e],
                'gap':a['I_hop'+e]-b['I_hop'+e],
                'sink_gap_share':(a['I_hop'+e]-b['I_hop'+e])/gap if e!='01' else None,
                'candidate_hop_given_L':a['I_hop'+e]/pa,'control_hop_given_L':b['I_hop'+e]/pb,
                'candidate_single_given_L':u/pa,'control_single_given_L':w/pb,
                'candidate_cov_PL_single':u-pa*2*a['gate_Q'+e],
                'control_cov_PL_single':w-pb*2*b['gate_Q'+e],
                'candidate_PL_bare_hop_real':a['B_L'+e]-a['M_L'+e],
                'control_PL_bare_hop_real':b['B_L'+e]-b['M_L'+e],
                'candidate_RL_Re':a['edge_coherence_Re'+e],'candidate_RL_Im':a['edge_coherence_Im'+e],
                'control_RL_Re':b['edge_coherence_Re'+e],'control_RL_Im':b['edge_coherence_Im'+e],
            }
        continuity={side:{'hop_sink_identity':abs(r['I_hop_sink']-r['I_hop02']-r['I_hop12']),
                          'middle_node_identity':abs(r['dn1_dt']-r['I_hop01']+r['I_hop12']),
                          'formation_direct_sink':abs(r['I_form_sink']),
                          'idle_direct_sink':abs(r['I_idle_sink'])} for side,r in [('candidate',a),('control',b)]}
        assert max(val for r in continuity.values() for val in r.values())<1e-12
        aa,bb=series[candidate+'_fine'],series['RR_'+candidate+'_fine'];dg=aa['I_hop_sink']-bb['I_hop_sink'];times=aa['time']
        pairs[candidate]={'candidate_hop':h,'control_hop':hr,'gap':gap,'mismatch_vs_candidate':gap/h,
            'candidate_excess_vs_control':gap/hr,'ratio':h/hr,'edges':edges,'continuity':continuity,
            'path_probability_candidate':a['path_probability'],'path_probability_control':b['path_probability'],
            'path_relative_increase':a['path_probability']/b['path_probability']-1,
            'gap_series_peak':{'time':float(times[np.argmax(dg)]),'value':float(max(dg))},
            'gap_at_times':{str(t):float(dg[np.argmin(abs(times-t))]) for t in [0,1,5,20,40,100,190,200]},
            'decision':m['pair_decisions'][candidate]}
    gaps=[pairs[x]['gap'] for x in ['QS','QQ']]
    case_seconds=sum(c['elapsed_seconds'] for c in m['cases'].values())
    old=json.loads((root/'source/analysis/E002_GH_v001_r001/audit.json').read_text())
    pp=old['cases']['PP'];old_comparison={}
    for variant in ['QQ','QS']:
        c=old['cases'][variant]
        old_comparison[variant]={
            'normalized_deficit_reduction_vs_PP_percent':100*(1-c['Lambda_hop']/pp['Lambda_hop']),
            'signed_absolute_hop_loss_reduction_vs_PP_percent':100*(1-c['signed_absolute_hop_loss']/pp['signed_absolute_hop_loss']),
            'baseline_hop':c['baseline_hop'],'Lambda_hop':c['Lambda_hop'],
            'signed_absolute_hop_loss':c['signed_absolute_hop_loss']}
    return {'result_commit':RESULT,'source_commit':SOURCE,'run_id':RUN,
        'runtime':{'expected_seconds':f['expected_seconds'],'actual_seconds':actual,
            'deviation_percent':100*(actual/f['expected_seconds']-1),'status':'PASS',
            'internal_seconds':m['runtime_gate']['actual_seconds'],'case_seconds':case_seconds,
            'actual_noncase_seconds':actual-case_seconds,'forecast_noncase_seconds':60,
            'forecast_case_seconds':f['expected_seconds']-60,'queue_seconds':receipt['job']['started']-receipt['job']['created']},
        'technical_status':'VERIFIED_GITHUB_PACKAGE','user_acceptance':'NOT_ASSIGNED_BY_ASSISTANT',
        'artifacts_verified':len(v['artifacts']),'artifact_bytes':sum(map(len,v['artifacts'].values())),
        'inputs_verified':len(receipt['input_sha256']),'csv_verification':csv_check,'checks_reported_pass':len(checks),
        'public_refinement_maxima':public_refinement,
        'full_inventory_files':len(ib),'full_inventory_bytes':sum(ib.values()),'snapshot_metadata_verified':snapshot_count,
        'pairs':pairs,'gap_difference':gaps[1]-gaps[0],'gap_difference_fraction_of_mean':(gaps[1]-gaps[0])/np.mean(gaps),
        'operator_algebra':algebra(),
        'E002_context_from_previous_verified_audit':old_comparison,
        'limits':['No raw VM matrices read; state norms and eigenvalues rely on reported diagnostics.',
            'B_L+M_L and gate_Q allow population covariance; unconditional imaginary node hopping coherence was not exported.',
            'Coherent net formation current is not a gross bidirectional event rate.',
            'This is post-hoc analysis of existing data, not a preregistered E002c prediction.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=audit(args.root.resolve());args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:out[k] for k in ['runtime','technical_status','artifacts_verified','inputs_verified','csv_verification','operator_algebra']},ensure_ascii=False))
