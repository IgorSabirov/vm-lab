"""Independent report-only reader: no engine, model or full/ reads."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.integrate import simpson

class InvalidReport(ValueError):pass

def require(ok,message):
    if not ok:raise InvalidReport(message)

def load_json(p):return json.loads(p.read_text())

def pt_neg(r,dims,cut):
    n=len(dims);ax=list(range(2*n));ax[cut],ax[n+cut]=ax[n+cut],ax[cut]
    a=r.reshape(dims+dims).transpose(ax).reshape(r.shape)
    ev=np.linalg.eigvalsh((a+a.conj().T)/2)
    return float(-ev[ev<0].sum())

def check_certificate(block,vec,alpha,overlap,valid):
    weight=float(np.trace(block).real)
    require(bool(valid)==(weight>1e-6),'Invalid conditional weight flag')
    require(np.max(abs(block-block.conj().T))<1e-9,'Non-Hermitian node evidence')
    require(np.linalg.eigvalsh((block+block.conj().T)/2)[0]>=-1e-8,'Negative node evidence')
    if not valid:return None
    r=block/weight
    require(vec.shape==(6,8),'Wrong witness vector shape')
    for i,v in enumerate(vec):
        require(abs(np.vdot(v,v)-1)<1e-9,'Non-unit witness vector')
        a=max(np.linalg.eigvalsh(np.moveaxis(v.reshape(2,2,2),k,0).reshape(2,4)@
               np.moveaxis(v.reshape(2,2,2),k,0).reshape(2,4).conj().T)[-1].real for k in range(3))
        ov=float(np.vdot(v,r@v).real)
        require(abs(a-alpha[i])<1e-9,'Wrong Schmidt alpha')
        require(abs(ov-overlap[i])<1e-9,'Wrong witness overlap/sign')
    return float(np.min(alpha-overlap))

def verify(report):
    report=Path(report);man=load_json(report/'data_manifest.json')
    require((report/'RESULT.md').stat().st_size<=24576,'Oversized RESULT')
    actual={p.relative_to(report).as_posix() for p in report.rglob('*') if p.is_file()}
    declared={x['path'] for x in man['exported']}
    require(actual==declared|{'data_manifest.json'},'Incomplete or extra report files')
    require(sum(p.stat().st_size for p in report.rglob('*') if p.is_file())<=30*1024**2,'Report budget')
    require(len(actual)<=500,'File budget')
    arrays={}
    for entry in man['exported']:
        name=entry['path'];p=Path(name)
        require(not p.is_absolute() and '..' not in p.parts,'Unsafe path')
        raw=(report/p).read_bytes()
        require(len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256'],'SHA/size mismatch: '+name)
        if p.suffix=='.npz':
            with np.load(report/p,allow_pickle=False) as z:
                require(set(z.files)==set(entry['arrays']),'Unexpected array set')
                a={}
                for k,spec in entry['arrays'].items():
                    v=z[k];require(v.dtype in (np.dtype('float64'),np.dtype('complex128')),'Unsafe/unsupported dtype')
                    require(str(v.dtype)==spec['dtype'] and list(v.shape)==spec['shape'],'Array shape/type mismatch')
                    a[k]=v
                arrays[name]=a
    sc=load_json(report/'schema.json');metrics=load_json(report/'metrics.json');checks=load_json(report/'checks.json')
    require(checks.get('export_complete') is True,'Unfinished export')
    require(sc.get('version')=='e002c-2','Unsupported schema')
    sn=sc['series'];dn=sc['diagnostics'];ext=load_json(report/'extrema.json')
    require(len(set(sn))==len(sn) and len(set(dn))==len(dn),'Duplicate column names')
    for m in (7,6):
        for prefix in ('C','c'):
            for part in ('re','im'):require(f'{prefix}01_m{m}_{part}' in dn,'Missing coherence column')
    with (report/'cases.csv').open() as stream:cases=list(csv.DictReader(stream))
    require(len(cases)==len(metrics['cases']),'Case inventory mismatch')
    ids=[s['case']['id'] for s in metrics['cases']]
    require(len(set(ids))==len(ids) and set(ids)=={c['id'] for c in cases},'Duplicate/missing cases')
    computed=[]
    for summary in metrics['cases']:
        cid=summary['case']['id'];T=summary['horizon'];a=arrays[f'series/{cid}.npz']['values'];d=arrays[f'diagnostics/{cid}.npz']['values'];e=arrays[f'evidence/{cid}.npz']
        expected_t=np.r_[np.arange(round(min(T,10)/.2)+1)*.2,np.arange(12,T+1e-8,2)]
        expected_d=np.r_[np.arange(0,min(T,20)+1e-8,2),np.arange(24,T+1e-8,4)]
        require(a.shape==(len(expected_t),len(sn)) and np.allclose(a[:,0],expected_t,atol=1e-8,rtol=0),'Wrong scalar grid')
        require(d.shape==(len(expected_d),len(dn)) and np.allclose(d[:,0],expected_d,atol=1e-8,rtol=0),'Wrong diagnostic grid')
        require(len(sn)<=56 and len(dn)<=128,'Too many columns')
        require(np.isfinite(a).all(),'Nonfinite scalar series')
        require(summary['requested_horizon']==summary['case']['horizon'] and summary['extended']==(T>summary['requested_horizon']+1e-9),'Wrong extension metadata')
        require(summary['steps']==round(T/summary['case']['dt']) and summary['rhs_calls']==4*summary['steps'],'Step/RHS mismatch')
        require(np.max(abs(a[:,sn.index('h')]-a[:,sn.index('I02')]-a[:,sn.index('I12')]))<1e-9,'Sink current double-count/sign')
        require(np.max(abs(sum(a[:,sn.index(f'p_m{m}')] for m in range(8))-1))<1e-9,'Missing mask')
        for j,t in enumerate(d[:,0]):
            row=a[np.argmin(abs(a[:,0]-t))];require(abs(row[0]-t)<1e-8,'Missing aligned scalar')
            for edge in ('01','12','02'):
                require(abs(sum(d[j,dn.index(f'I{edge}_m{m}')] for m in range(8))-row[sn.index('I'+edge)])<1e-9,'Mask currents do not sum')
            for m in (7,6):
                weight=row[sn.index(f'p_m{m}')]
                C=np.array([d[j,dn.index(f'C01_m{m}_{part}')] for part in ('re','im')])
                cond=np.array([d[j,dn.index(f'c01_m{m}_{part}')] for part in ('re','im')])
                require(np.isfinite(C).all(),'Nonfinite unnormalized coherence')
                if weight<=1e-6:require(np.isnan(cond).all(),'Conditional coherence must be NaN')
                else:require(np.isfinite(cond).all() and np.allclose(cond,C/weight,atol=1e-10,rtol=1e-9),'Wrong conditional coherence normalization')
            for s in range(9):
                valid=d[j,dn.index(f'valid_s{s}')]>0.5
                for key in [f'N_s{s}_cut{k}' for k in range(3)]+[f'W_s{s}']:
                    require(bool(np.isfinite(d[j,dn.index(key)]))==valid,'Wrong null encoding')
        ref=summary['reference']
        if ref is not None:
            take=(a[:,0]>=T-10-1e-8)&np.isclose(a[:,0]/2,np.round(a[:,0]/2),atol=1e-9)
            mean=simpson(a[take,1:],x=a[take,0],axis=0)/10
            require(np.allclose(mean,[ref[k] for k in sn[1:]],atol=1e-10,rtol=1e-10),'Reference mean mismatch')
        tref=summary.get('transition_reference')
        if T>=200:
            require(tref is not None,'Missing fixed-window reference')
            take=(a[:,0]>=190-1e-8)&(a[:,0]<=200+1e-8)&np.isclose(a[:,0]/2,np.round(a[:,0]/2),atol=1e-9)
            require(sum(take)==6,'Missing fixed-window samples')
            mean=simpson(a[take,1:],x=a[take,0],axis=0)/10
            require(np.allclose(mean,[tref[k] for k in sn[1:]],atol=1e-10,rtol=1e-10),'Transition mean mismatch')
        else:require(tref is None,'Transition reference before T200')
        for j,t in enumerate(e['time']):
            blocks=e['blocks'][j]
            require(np.max(abs(blocks[0]-blocks[1:].sum(axis=0)))<1e-9,'Node reductions do not sum')
            row=a[np.argmin(abs(a[:,0]-t))];dr=d[np.argmin(abs(d[:,0]-t))]
            require(abs(row[0]-t)<1e-8 and abs(dr[0]-t)<1e-8,'Evidence grid mismatch')
            for m in range(8):require(abs(np.trace(blocks[m+1]).real-row[sn.index(f'p_m{m}')])<1e-9,'Evidence mask weight mismatch')
            for m in (7,6):
                expected=blocks[m+1,2,4]
                saved=complex(dr[dn.index(f'C01_m{m}_re')],dr[dn.index(f'C01_m{m}_im')])
                require(abs(expected-saved)<1e-10,'Wrong coherence index/sign/mask')
            for s in range(9):
                w=check_certificate(blocks[s],e['vectors'][j,s],e['alpha'][j,s],e['overlap'][j,s],e['valid'][j,s])
                if w is not None:
                    require(abs(w-dr[dn.index(f'W_s{s}')])<1e-9,'Witness scalar sign mismatch')
                    r=blocks[s]/np.trace(blocks[s]).real
                    for k in range(3):require(abs(pt_neg(r,[2,2,2],k)-dr[dn.index(f'N_s{s}_cut{k}')])<1e-9,'Partial transpose mismatch')
            for k in range(3):
                pair=np.trace(blocks[0].reshape(2,2,2,2,2,2),axis1=k,axis2=k+3).reshape(4,4)
                require(abs(pt_neg(pair,[2,2],0)-dr[dn.index(f'pair_N_exclude{k}')])<1e-9,'Pair negativity mismatch')
        for s in range(9):
            w=check_certificate(e['extreme_blocks'][s],e['extreme_vectors'][s],e['extreme_alpha'][s],e['extreme_overlap'][s],e['extreme_valid'][s])
            if w is not None:
                expected=ext[cid]['diagnostic'][dn.index(f'W_s{s}')-1][0]
                require(abs(w-expected)<1e-9,'Extreme certificate mismatch')
        for key,data,cols in [('scalar',a,sn),('diagnostic',d,dn)]:
            for i,x in enumerate(ext[cid][key]):
                values=data[:,i+1];finite=values[np.isfinite(values)]
                if len(finite):require(x[0]<=min(finite)+1e-9 and x[2]>=max(finite)-1e-9,'Extrema omit exported point')
        computed.append(cid)
    # Recheck dt pairs on every published common row. Full-grid error maxima must dominate these.
    byid={s['case']['id']:s for s in metrics['cases']}
    expected_refinement={cid:'not_refined' for cid in byid}
    for cid,pair in checks.get('pairs',{}).items():
        coarse=byid[cid]['case']
        fine=next((s['case'] for s in metrics['cases'] if all(s['case'][k]==coarse[k] for k in ('model','phi_over_pi','detuning','dephasing')) and abs(s['case']['dt']-coarse['dt']/2)<1e-12 and (s['case'].get('family')=='validation')==(coarse.get('family')=='validation')),None)
        require(fine is not None,'Missing dt partner')
        expected_refinement[cid]=expected_refinement[fine['id']]='passed' if pair['pass_gate'] else 'failed'
        for section,columns in (('series',sn),('diagnostics',dn)):
            a=arrays[f"{section}/{cid}.npz"]['values'];b=arrays[f"{section}/{fine['id']}.npz"]['values']
            require(a.shape==b.shape and np.array_equal(a[:,0],b[:,0]),'Unpaired export grids')
            finite=np.isfinite(a)&np.isfinite(b);error=np.where(finite,abs(a-b),0.)
            observed=error.max(axis=0)
            if pair['pass_gate']:
                require(np.array_equal(np.isnan(a),np.isnan(b)),'Invalid dt null mismatch')
                limit=1e-6+1e-4*np.maximum(np.nan_to_num(abs(a)),np.nan_to_num(abs(b)))
                require(np.all(error<=limit),'False dt PASS')
            for k,v in zip(columns,observed):
                if section in pair.get('errors',{}):require(pair['errors'][section][k]+1e-12>=v,'Underreported full-grid error')
    for cid,status in expected_refinement.items():require(byid[cid]['refinement_status']==status,'Unsubstantiated refinement status')
    numeric=bool(checks.get('pairs')) and all(p['pass_gate'] for p in checks['pairs'].values())
    werror=max([v for p in checks.get('pairs',{}).values() for values in p.get('errors',{}).values() for k,v in values.items() if k.startswith('W_s')]+[0.])
    threshold=max(1e-8,10*werror)
    for j in metrics.get('joint',[]):
        for g in j['GME']:
            minimum=ext[j['id']]['diagnostic'][dn.index(f"W_s{g['state']}")-1][0]
            require(g['minimum']==minimum and g['threshold']==threshold,'GME minimum/error mismatch')
            status='GME_CERTIFIED' if numeric and minimum is not None and minimum < -threshold else 'GME_NOT_CERTIFIED_BY_THIS_FAMILY'
            require(g['status']==status,'Invalid GME status')
    for j in metrics.get('joint',[]):
        a=arrays[f"series/{j['id']}.npz"]['values'];d=arrays[f"diagnostics/{j['id']}.npz"]['values']
        row=a[np.argmin(abs(a[:,0]-d[-1,0]))]
        require({x['mask'] for x in j.get('coherences',[])}=={6,7},'Missing coherence quality metadata')
        for x in j['coherences']:
            m=x['mask'];weight=float(row[sn.index(f'p_m{m}')])
            quality='undefined' if weight<=1e-6 else ('low_weight' if weight<1e-5 else 'ok')
            require(x['status']==quality and abs(x['weight']-weight)<1e-12 and x['time']==d[-1,0],'Wrong coherence quality flag')
            C=[float(d[-1,dn.index(f'C01_m{m}_{part}')]) for part in ('re','im')]
            require(np.allclose(x['unnormalized'],C,atol=1e-10,rtol=1e-9),'Wrong coherence metadata')
            if weight<=1e-6:require(x['conditional'] is None,'Wrong conditional metadata null')
            else:require(np.allclose(x['conditional'],np.array(C)/weight,atol=1e-10,rtol=1e-9),'Wrong conditional metadata')
    if metrics.get('fit') and metrics['fit'].get('selected') is not None:
        raw=(report/'selected_alpha.json').read_bytes()
        require(hashlib.sha256(raw).hexdigest()==metrics['fit']['selected_alpha_sha256'],'Selection hash mismatch')
        require(json.loads(raw)['alpha']==metrics['fit']['selected']['alpha'],'Selected alpha mismatch')
    verify_protocol_tables(metrics,checks)
    return dict(status='VERIFIED_EXPORTED_ARRAYS',cases=computed,
                limitations=man['limitations'],runtime_acceptance='requires external run.json and user review')


def verify_protocol_tables(metrics,checks):
    """Independent semantic audit; does not import analysis, comparability, or ic_status."""
    cases=metrics['cases'];byid={s['case']['id']:s for s in cases}
    numerical=bool(checks.get('pairs')) and all(p['pass_gate'] for p in checks['pairs'].values())
    threshold=max(1e-5,10*max([v for p in checks.get('pairs',{}).values() for fields in p.get('errors',{}).values() for k,v in fields.items() if k=='h']+[0.]))
    def assess(records,kind):
        horizons=[float(s['horizon']) for s in records];reasons=[]
        if any(s.get('failed') is not None for s in records):reasons.append('failed_case')
        if kind=='stationary':
            if not horizons or max(horizons)-min(horizons)>1e-9:reasons.append('different_horizons')
            if any(not s['stationarity']['pass_gate'] for s in records):reasons.append('not_stationary')
            refs=[s.get('reference') for s in records]
        else:
            if any(t<200-1e-9 for t in horizons):reasons.append('common_window_not_reached')
            refs=[s.get('transition_reference') for s in records]
        if any(r is None or not np.isfinite(list(r.values())).all() for r in refs):reasons.append('invalid_reference')
        refinements=[s.get('refinement_status','not_refined') for s in records]
        if 'failed' in refinements:reasons.append('refinement_failed')
        if any(x not in ('passed','failed','not_refined') for x in refinements):reasons.append('unknown_refinement')
        refined=bool(records) and all(x=='passed' for x in refinements)
        if not refined and not numerical:reasons.append('numerical_screen_unverified')
        return dict(policy='same_horizon_stationary_or_fixed_window_200_v1',kind=kind,comparable=not reasons,
            reasons=reasons,case_ids=[s['case']['id'] for s in records],horizons=horizons,
            window=[190.,200.] if kind=='transition_200' else ([horizons[0]-10,horizons[0]] if horizons and not reasons else None),
            evidence_level='REFINEMENT_CHECKED' if refined else 'SCREENING_ONLY')
    def audit_row(row,records,kind,value,label,negative):
        comp=assess(records,kind);require(row['comparison']==comp,'Wrong comparison class or provenance')
        resolved=value is not None and abs(value)>threshold
        if not comp['comparable']:status='not_comparable'
        elif kind=='transition_200':status='finite_time_difference' if resolved else 'no_resolved_finite_time_difference'
        elif resolved and comp['evidence_level']=='SCREENING_ONLY':status='SCREENING_SIGNAL'
        else:status=label if resolved else negative
        require(row['status']==status,'False comparison status')
    def equal(a,b,message):
        require((a is None and b is None) or (a is not None and b is not None and np.isfinite(a) and abs(a-b)<1e-9),message)
    for kind,tables in (('stationary',metrics),('transition_200',metrics.get('transition_comparisons',{}))):
        lookup={}
        for s in cases:
            c=s['case']
            if c['dt']==.01 and c.get('family') not in ('fit','validation','calibration'):
                key=(c['model'],c['phi_over_pi'],c['detuning'],c['dephasing']);require(key not in lookup,'Duplicate comparison input');lookup[key]=s
        refkey='reference' if kind=='stationary' else 'transition_reference'
        def val(s,k):return s[refkey][k] if s.get(refkey) is not None else None
        def delta(a,b):return None if a is None or b is None else a-b
        expected_gaps={(ctrl,*key[1:]) for key in lookup if key[0]=='QS' for ctrl in ('RR_QS','IC1_QS') if (ctrl,*key[1:]) in lookup}
        gm={};records_map={}
        for g in tables.get('gaps',[]):
            key=(g['control'],g['phi_over_pi'],g['detuning'],g['dephasing']);require(key not in gm,'Duplicate gap')
            require(key in expected_gaps,'Unexpected gap');q=lookup[('QS',*key[1:])];c=lookup[key]
            v=delta(val(q,'h'),val(c,'h'));equal(g['delta_h'],v,'Gap value mismatch');equal(g['QS_h'],val(q,'h'),'QS h mismatch');equal(g['control_h'],val(c,'h'),'Control h mismatch')
            for edge in ('I12','I02'):equal(g[edge+'_gap'],delta(val(q,edge),val(c,edge)),'Route gap mismatch')
            den=max(abs(val(q,'h')),1e-8) if val(q,'h') is not None else None
            equal(g['denominator_QS'],den,'Wrong denominator');equal(g['relative_gap'],v/den if v is not None else None,'Wrong relative gap')
            audit_row(g,[q,c],kind,v,'transport_gap','no_resolved_gap');gm[key]=v;records_map[key]=[q,c]
        require(set(gm)==expected_gaps,'Missing gap rows')
        seen=set();expected={key for key in lookup if key[1]!=0 and (key[0],0,*key[2:]) in lookup}
        for p in tables.get('phase',[]):
            key=(p['model'],p['phi_over_pi'],p['detuning'],p['dephasing']);require(key in expected and key not in seen,'Unexpected phase row');seen.add(key)
            a=lookup[key];b=lookup[(key[0],0,*key[2:])];v=delta(val(a,'h'),val(b,'h'));equal(p['delta_h'],v,'Phase mismatch');audit_row(p,[a,b],kind,v,'flux_response','no_resolved_response')
            fields=('pL01','pL12','pL02','ell01','ell12','ell02','inventory','pump','break')
            shift=max(abs(val(a,k)-val(b,k))/max(abs(val(b,k)),1e-8) for k in fields) if a.get(refkey) is not None and b.get(refkey) is not None else None
            equal(p['structural_relative_max'],shift,'Population shift mismatch')
            population='not_comparable' if not p['comparison']['comparable'] else ('population_near_matched' if shift<=.01 else 'population_coupled_response')
            require(p['population_status']==population,'Invalid population status')
        require(seen==expected,'Missing phase rows')
        expected={key for key in gm if key[1]!=0 and (key[0],0,*key[2:]) in gm};seen=set()
        for p in tables.get('gap_phase',[]):
            key=(p['control'],p['phi_over_pi'],p['detuning'],p['dephasing']);require(key in expected and key not in seen,'Unexpected gap phase');seen.add(key);base=(key[0],0,*key[2:])
            v=delta(gm[key],gm[base]);equal(p['value'],v,'Gap phase mismatch');audit_row(p,records_map[key]+records_map[base],kind,v,'gap_flux_response','no_resolved_gap_response')
        require(seen==expected,'Missing gap phase rows')
        expected={};seen=set()
        for ctrl in ('RR_QS','IC1_QS'):
            for eps in (-.5,0.,.5):
                for gamma in (0.,.25):
                    keys=[(ctrl,.5,eps,gamma),(ctrl,0,eps,gamma),(ctrl,.5,eps,.05),(ctrl,0,eps,.05)]
                    if all(k in gm for k in keys):expected[(ctrl,eps,gamma)]=keys
        for p in tables.get('interactions',[]):
            key=(p['control'],p['detuning'],p['dephasing']);require(key in expected and key not in seen,'Unexpected interaction');seen.add(key);keys=expected[key];values=[gm[k] for k in keys]
            v=values[0]-values[1]-values[2]+values[3] if all(x is not None for x in values) else None
            equal(p['value'],v,'Interaction mismatch');audit_row(p,[s for k in keys for s in records_map[k]],kind,v,'gap_flux_response','no_resolved_gap_response')
        require(seen==set(expected),'Missing interactions')
        expected={m for m in ('QS','RR_QS','IC1_QS') if all((m,phi,0.,.05) in lookup for phi in (0.,.5,-.5,1.))};seen=set()
        for p in tables.get('flux_spans',[]):
            m=p['model'];require(m in expected and m not in seen,'Unexpected span');seen.add(m)
            records=[lookup[(m,phi,0.,.05)] for phi in (0.,.5,-.5,1.)];vs=[val(s,'h') for s in records]
            span=max(vs)-min(vs) if all(v is not None for v in vs) else None;equal(p['span'],span,'Span mismatch')
            require(p['h_by_phi_over_pi']==dict(zip(('0.0','0.5','-0.5','1.0'),vs)),'Span components mismatch')
            equal(p['plus_minus_difference'],delta(vs[1],vs[2]),'Plus/minus mismatch');audit_row(p,records,kind,span,'flux_response','no_resolved_response')
        require(seen==expected,'Missing spans')
    fit=metrics.get('fit');validation=metrics.get('ic_validation');transport=metrics.get('ic_transport')
    structural='not_run';tr='not_evaluated'
    if fit is None:require(validation is None and transport is None,'Outcome without IC fit')
    elif fit.get('selected') is None:
        structural='no_match_found_within_declared_search';require(validation is None and transport is None,'Outcome without candidate')
    elif validation is None:
        structural='structural_candidate_found_validation_pending';require(transport is None,'Premature transport')
    elif not validation['structural_pass']:
        structural='structural_candidate_rejected_by_validation';require(transport is None,'Transport for rejected candidate')
    else:
        structural='structural_PASS';tr='transport_pending'
        if transport is not None:
            records=[byid[transport['QS_case_id']],byid[transport['IC_case_id']]];comp=assess(records,'stationary')
            require(transport['comparison']==comp and transport['evaluable']==comp['comparable'],'Wrong transport evaluability')
            if not comp['comparable']:tr='transport_not_evaluable'
            else:
                q=records[0]['reference']['h'];ic=records[1]['reference']['h'];error=abs(ic-q)/max(abs(q),1e-8)
                equal(transport['relative_error'],error,'Wrong held-out error');equal(transport['QS_h'],q,'Wrong held-out QS');equal(transport['IC_h'],ic,'Wrong held-out IC')
                tr='transport_close_5pct' if error<=.05 else ('transport_close_10pct' if error<=.10 else 'structural_matched_hop_mismatch')
    require(metrics.get('ic_structural_status')==structural and metrics.get('ic_transport_status')==tr,'Invalid IC status transition')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('report');args=parser.parse_args()
    print(json.dumps(verify(args.report),ensure_ascii=False,indent=2))
