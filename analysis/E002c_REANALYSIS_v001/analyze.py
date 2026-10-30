"""Independent descriptive reanalysis of immutable E002c GitHub exports; no dynamics."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.integrate import simpson

ROOT=Path(__file__).resolve().parents[2]
REPORT='7fd36d60044b436484e81a5e92a80163c4688b45'
SOURCE='ae867241bc94ee6e2ce36ade26131ab28bcc939d'
RUN='E002c_REPAIR_v001_r001'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--github-cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args();cache=args.github_cache;p=cache/'files';out=args.output
    out.mkdir(parents=True,exist_ok=True)
    load=lambda name:json.loads((p/name).read_text())
    raw=json.loads((cache/'run.json').read_text());checks=load('checks.json');metrics=load('metrics.json')
    repair_seconds=raw['job']['finished']-raw['job']['started'];rt=checks['runtime_gate']
    time_first=dict(trajectory=checks['trajectory_runtime_gate'],repair=dict(expected_seconds=rt['expected_seconds'],
        actual_seconds=repair_seconds,lower_seconds=rt['lower_seconds'],upper_seconds=rt['upper_seconds'],
        deviation_seconds=repair_seconds-rt['expected_seconds'],queue_seconds=raw['job']['started']-raw['job']['created'],
        publication_seconds=None,status='PASS' if rt['lower_seconds']<=repair_seconds<=rt['upper_seconds'] else 'REVIEW_REQUIRED'))
    print(json.dumps(dict(time_first=time_first)))
    assert time_first['repair']['status']==time_first['trajectory']['status']=='PASS'
    sys.path.insert(0,str(ROOT/'infra'));sys.path.insert(0,str(ROOT))
    from github_result_reader import read_github_result
    from e002c_exp.verify import verify
    from e002c_exp.diagnostics import pair_reduction,negativity
    prefix='results/'+RUN+'/'
    def fetch(repo,path,ref):
        assert repo=='IgorSabirov/vm-lab' and ref==REPORT and path.startswith(prefix)
        return (cache/path[len(prefix):]).read_bytes()
    package=read_github_result(fetch,repository='IgorSabirov/vm-lab',result_commit=REPORT,run_id=RUN,source_commit=SOURCE)
    assert package['execution_succeeded'] and raw['export_errors']==[] and checks['failures']==[]
    verified=verify(p)
    sc=load('schema.json');sn=sc['series'];dn=sc['diagnostics'];by={s['case']['id']:s for s in metrics['cases']}
    arrays={cid:(np.load(p/'series'/f'{cid}.npz',allow_pickle=False)['values'],
                 np.load(p/'diagnostics'/f'{cid}.npz',allow_pickle=False)['values']) for cid in by}
    def endpoint(cid):
        a,d=arrays[cid];assert a[-1,0]==d[-1,0]
        return dict(zip(sn,a[-1])),dict(zip(dn,d[-1]))
    def split(q,r,dq,dr):
        gap=q['h']-r['h'];rows=[]
        for mask in range(8):
            pq,pr=q[f'p_m{mask}'],r[f'p_m{mask}'];assert min(pq,pr)>1e-6
            hq=dq[f'I12_m{mask}']+dq[f'I02_m{mask}'];hr=dr[f'I12_m{mask}']+dr[f'I02_m{mask}']
            jq,jr=hq/pq,hr/pr
            weights=(pq-pr)*(jq+jr)/2;conditional=(pq+pr)*(jq-jr)/2
            assert abs(weights+conditional-(hq-hr))<1e-12
            rows.append(dict(mask=mask,edges=[e for i,e in enumerate(('01','12','02')) if mask&(1<<i)],
                QS_p=pq,RR_p=pr,QS_h=hq,RR_h=hr,QS_conditional_current=jq,RR_conditional_current=jr,
                delta=hq-hr,share_percent=100*(hq-hr)/gap,weights_term=weights,conditional_term=conditional,
                I12_gap=dq[f'I12_m{mask}']-dr[f'I12_m{mask}'],I02_gap=dq[f'I02_m{mask}']-dr[f'I02_m{mask}']))
        assert abs(sum(x['delta'] for x in rows)-gap)<1e-12
        return dict(gap=gap,rows=rows,weights_term=sum(x['weights_term'] for x in rows),
            conditional_term=sum(x['conditional_term'] for x in rows),
            single_edge_share_percent=sum(rows[i]['share_percent'] for i in (2,4)))
    q,dq=endpoint('QS_P05_dt005');r,dr=endpoint('RR_QS_P05_dt005')
    assert all(by[c]['stationarity']['pass_gate'] and by[c]['refinement_status']=='passed'
               for c in ('QS_P05_dt005','RR_QS_P05_dt005'))
    baseline=split(q,r,dq,dr)
    qr=by['QS_P05_dt005']['reference'];rr=by['RR_QS_P05_dt005']['reference'];refgap=qr['h']-rr['h']
    baseline.update(time=200.,dt=.005,reference_window=[190.,200.],reference_QS_h=qr['h'],reference_RR_h=rr['h'],
        reference_gap=refgap,gap_over_QS_percent=100*refgap/qr['h'],gap_over_RR_percent=100*refgap/rr['h'],
        reference_endpoint_gap_difference=baseline['gap']-refgap,
        maximum_pL_ell_absolute_difference=max(abs(qr[k]-rr[k]) for k in ('pL01','pL12','pL02','ell01','ell12','ell02')),
        mask_total_variation=.5*sum(abs(q[f'p_m{i}']-r[f'p_m{i}']) for i in range(8)),
        symmetric_split_note='Exact descriptive identity, not a causal partition or a fraction of quantum advantage.')
    baseline['weights_share_percent']=100*baseline['weights_term']/baseline['gap']
    baseline['conditional_share_percent']=100*baseline['conditional_term']/baseline['gap']
    qc,dqc=endpoint('QS_P05_dt010');rc,drc=endpoint('RR_QS_P05_dt010');coarse=split(qc,rc,dqc,drc)
    baseline['dt_mask_gap_max_difference']=max(abs(x['delta']-y['delta']) for x,y in zip(baseline['rows'],coarse['rows']))
    # Diagnostic export has [192,196,200], not all six points of [190,200].
    # Check sensitivity on that common window without relabeling it as [190,200].
    def common_mean(cid):
        a,d=arrays[cid];t=np.array([192.,196.,200.]);ia=[np.flatnonzero(abs(a[:,0]-x)<1e-8)[0] for x in t]
        idd=[np.flatnonzero(abs(d[:,0]-x)<1e-8)[0] for x in t]
        return dict(zip(sn,simpson(a[ia],x=t,axis=0)/8)),dict(zip(dn,simpson(d[idd],x=t,axis=0)/8))
    qw,dqw=common_mean('QS_P05_dt005');rw,drw=common_mean('RR_QS_P05_dt005');window=split(qw,rw,dqw,drw)
    baseline['common_192_200_weights_share_percent']=100*window['weights_term']/window['gap']
    baseline['common_192_200_single_edge_share_percent']=window['single_edge_share_percent']
    dark={}
    for label,s,d in [('QS',q,dq),('RR_QS',r,dr)]:
        dark[label]=dict(total=sum(s[f'd_m{i}'] for i in range(8)),one_excitation=sum(s[f'w1_m{i}'] for i in range(8)),
            isolated=sum(d[f'd_isolated_m{i}'] for i in range(8)),interference=sum(d[f'd_interference_m{i}'] for i in range(8)),
            by_mask=[dict(mask=i,dark=s[f'd_m{i}'],isolated=d[f'd_isolated_m{i}'],interference=d[f'd_interference_m{i}'],
                fD=s[f'd_m{i}']/s[f'w1_m{i}'],fK=s[f'k_m{i}']/s[f'w1_m{i}']) for i in range(8)])
        assert abs(dark[label]['isolated']+dark[label]['interference']-dark[label]['total'])<1e-12
    dark['RR_minus_QS']={k:dark['RR_QS'][k]-dark['QS'][k] for k in ('total','isolated','interference')}
    dark['isolated_share_of_difference_percent']=100*dark['RR_minus_QS']['isolated']/dark['RR_minus_QS']['total']
    # Reconstruct terminal currents directly from the eight-dimensional evidence,
    # including both one- and two-excitation sectors. Phi=0 here, J=1.
    sectors={}
    for label in ('QS','RR_QS'):
        cid=label+'_P05_dt005';e=np.load(p/'evidence'/f'{cid}.npz',allow_pickle=False)
        assert e['time'][-1]==200.
        rows=[];_,d=endpoint(cid)
        for i in range(8):
            block=e['blocks'][-1,i+1]
            one=float(-2*np.imag((block[1,2] if i&2 else 0)+(block[1,4] if i&4 else 0)))
            two=float(-2*np.imag((block[5,6] if i&2 else 0)+(block[3,6] if i&4 else 0)))
            assert abs(one+two-d[f'I12_m{i}']-d[f'I02_m{i}'])<1e-10
            rows.append(dict(mask=i,one_excitation_current=one,two_excitation_current=two))
        sectors[label]=dict(rows=rows,one=sum(x['one_excitation_current'] for x in rows),two=sum(x['two_excitation_current'] for x in rows))
    sectors['two_excitation_gap_share_percent']=100*(sectors['QS']['two']-sectors['RR_QS']['two'])/baseline['gap']
    noise=[]
    for model in ('QS','RR_QS'):
        for point in (4,5,6,13,14,15):
            cid=f'{model}_P{point:02d}_dt010';s,d=endpoint(cid);c=by[cid]['case']
            row=dict(id=cid,model=model,phi_over_pi=c['phi_over_pi'],gamma=c['dephasing'],h_reference=by[cid]['reference']['h'],
                h_endpoint=s['h'],dark_interference=sum(d[f'd_interference_m{i}'] for i in range(8)))
            for mask in (6,7):
                row[f'C01_m{mask}_abs']=float(abs(d[f'C01_m{mask}_re']+1j*d[f'C01_m{mask}_im']))
                row[f'c01_m{mask}_abs']=float(abs(d[f'c01_m{mask}_re']+1j*d[f'c01_m{mask}_im']))
            noise.append(row)
    phases=metrics['phase'];phase_counts={model:dict(total=sum(x['model']==model for x in phases),
        resolved_near_matched=sum(x['model']==model and x['population_status']=='population_near_matched'
                                  and abs(x['delta_h'])>metrics['screening_threshold'] for x in phases)) for model in ('QS','RR_QS')}
    rrphase=next(x for x in phases if x['model']=='RR_QS' and x['phi_over_pi']==.5 and x['detuning']==0 and x['dephasing']==.05)
    rb=by['RR_QS_P05_dt010']['reference'];rp=by['RR_QS_P14_dt010']['reference']
    phase_detail=dict(row=rrphase,relative_response_percent=100*rrphase['delta_h']/rb['h'],
        maximum_mask_absolute_change=max(abs(rp[f'p_m{i}']-rb[f'p_m{i}']) for i in range(8)),
        node_population_changes=[rp[f'n{i}']-rb[f'n{i}'] for i in range(3)])
    gme=[]
    for j in metrics['joint']:
        for g in j['GME']:
            if g['status']!='GME_CERTIFIED':continue
            cid=j['id'];state=g['state'];e=np.load(p/'evidence'/f'{cid}.npz',allow_pickle=False)
            rho=e['extreme_blocks'][state];weight=float(np.trace(rho).real);rho=rho/weight
            _,d=arrays[cid];col=dn.index(f'W_s{state}')
            gme.append(dict(id=cid,state_index=state,edge_mask=state-1,time=float(e['extreme_time'][state]),
                weight=weight,witness=g['minimum'],threshold=g['threshold'],normalized_min_eigen=float(np.linalg.eigvalsh(rho)[0]),
                conditional_pair_negativity=[negativity(pair_reduction(rho,k),[2,2],[0])[0] for k in range(3)],
                published_negative_times=d[d[:,col]<-g['threshold'],0].tolist(),
                endpoint_witness=float(np.min(e['alpha'][-1,state]-e['overlap'][-1,state])),
                refinement_status=by[cid]['refinement_status'],case=by[cid]['case']))
    assert all(x['edge_mask']==5 and x['time']==2 and x['case']['dephasing']==0 for x in gme)
    fit=metrics['fit'];coverage=[]
    for start in (.25,1.,4.):
        records=[x for x in fit['records'] if x['start_factor']==start];a=np.array([x['alpha'] for x in records])
        coverage.append(dict(start_factor=start,calls=len(records),valid=sum(x['valid'] for x in records),
            distinct_alphas=[len(np.unique(a[:,i])) for i in range(3)],alpha02=float(a[0,2]),
            best_max_relative_error=min(x['maximum_error'] for x in records if x['valid'])))
    ic=dict(status=metrics['ic_structural_status'],transport_status=metrics['ic_transport_status'],coverage=coverage,
        selected=fit['selected'],validation=metrics['ic_validation'],
        necessary_alpha02_lower_bound_with_1pct_tolerance=.99*.038317472162921355/(1-1.4*.99*.26415137775171826),
        lower_bound_basis='Stationary pR=1-1.4*pL and alpha*<PR*C>=ell, with 0<=C<=1.',
        optimizer_convergence_recorded=False)
    comparison_counts={k:dict(total=len(metrics[k]),not_comparable=sum(not x['comparison']['comparable'] for x in metrics[k]))
                       for k in ('gaps','phase','interactions','gap_phase','flux_spans')}
    shares=[]
    for g in metrics['gaps']:
        if not g['comparison']['comparable']:continue
        qc,rc=g['comparison']['case_ids'];a,da=endpoint(qc);b,db=endpoint(rc);z=split(a,b,da,db)
        shares.append(dict(QS_case=qc,RR_case=rc,share_percent=z['single_edge_share_percent']))
    results=dict(provenance=dict(report_commit=REPORT,source_commit=SOURCE,run_id=RUN,
        run_json_sha256=hashlib.sha256((cache/'run.json').read_bytes()).hexdigest(),verified_files=len(raw['files']),
        source='Previously fetched pinned GitHub cache; every size/SHA256 rechecked.',new_trajectories=0,full_states_read=0),
        time_first=time_first,verification=verified,baseline=baseline,dark=dark,current_sectors=sectors,noise=noise,
        phase_counts=phase_counts,phase_RR_refined_example=phase_detail,GME=gme,IC=ic,comparison_counts=comparison_counts,
        single_edge_share_all_comparable=shares,
        limits=['Baseline decomposition is at common endpoint T200 with dt=.005; [192,200] diagnostic sensitivity is reported separately.',
            'Symmetric weight/conditional split is descriptive, not an intervention or identification of causality.',
            'Outside paired points, the original screening limitations remain.',
            'No new IC search, selective dephasing, or damage experiment is authorized or executed here.'])
    (out/'findings.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    make_plot(out,baseline,dark,noise,arrays,dn)
    print(json.dumps(dict(status='VERIFIED_REANALYSIS',mask_single_edge_share=baseline['single_edge_share_percent'],
        weights_share=baseline['weights_share_percent'],dark_isolated_share=dark['isolated_share_of_difference_percent'],
        two_excitation_share=sectors['two_excitation_gap_share_percent'],GME_records=len(gme),phase_counts=phase_counts)))


def make_plot(out,baseline,dark,noise,arrays,dn):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.hashsalt':'e002c-reanalysis-v001','svg.fonttype':'none'})
    fig,axes=plt.subplots(2,2,figsize=(11,7.5),layout='constrained')
    rows=baseline['rows'][2:];ax=axes[0,0]
    ax.bar([f"m{x['mask']}\n"+'+'.join(x['edges']) for x in rows],[x['share_percent'] for x in rows],color=['#1565c0' if x['mask'] in (2,4) else '#90a4ae' for x in rows])
    ax.set(title='Базовый зазор: вклад масок',ylabel='Доля знакового зазора, %')
    for i,x in enumerate(rows):ax.text(i,x['share_percent']+.7,f"{x['share_percent']:.1f}",ha='center',fontsize=9)
    ax=axes[0,1]
    for model,color,label in [('QS','#1565c0','QS'),('RR_QS','#d55e00','RR')]:
        r=[x for x in noise if x['model']==model and x['phi_over_pi']==0]
        ax.plot([x['gamma'] for x in r],[x['h_reference'] for x in r],'o-',label=label,color=color)
    ax.set(title='Дефазировка: противоположный отклик',xlabel='γ',ylabel='h, среднее [190,200]');ax.legend(frameon=False)
    ax=axes[1,0];iso=dark['isolated_share_of_difference_percent'];values=[iso,100-iso]
    ax.bar(['Изоляция','Интерференция'],values,color=['#1565c0','#90a4ae']);ax.set_ylim(0,112)
    for i,x in enumerate(values):ax.text(i,x+2,f'{x:.2f}%',ha='center')
    ax.set(title='Избыток тёмного веса RR над QS',ylabel='Доля различия, %')
    ax=axes[1,1];_,d=arrays['QS_P01_dt005'];take=(d[:,0]>0)&(d[:,0]<=20)
    ax.plot(d[take,0],d[take,dn.index('W_s6')],'o-',color='#1565c0')
    ax.axhline(0,color='#d55e00',linewidth=1);ax.set(title='GME-свидетель: условная маска m5',xlabel='t (QS P01, dt=0.005)',ylabel='W: отрицательное значение обнаруживает GME')
    ax.annotate('W(2) = −0.00599',xy=(2,-.0059895),xytext=(5,.12),arrowprops=dict(arrowstyle='->'),fontsize=9)
    for ax in axes.flat:ax.spines[['top','right']].set_visible(False)
    fig.suptitle('E002c: повторный анализ сохранённых данных',fontsize=15)
    fig.savefig(out/'findings.svg',metadata={'Date':None})
    fig.savefig('/tmp/e002c_reanalysis.png',dpi=150)
    plt.close(fig)


if __name__=='__main__':main()
