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
    sn=sc['series'];dn=sc['diagnostics'];ext=load_json(report/'extrema.json')
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
        require(summary['steps']==round(T/summary['case']['dt']) and summary['rhs_calls']==4*summary['steps'],'Step/RHS mismatch')
        require(np.max(abs(a[:,sn.index('h')]-a[:,sn.index('I02')]-a[:,sn.index('I12')]))<1e-9,'Sink current double-count/sign')
        require(np.max(abs(sum(a[:,sn.index(f'p_m{m}')] for m in range(8))-1))<1e-9,'Missing mask')
        for j,t in enumerate(d[:,0]):
            row=a[np.argmin(abs(a[:,0]-t))];require(abs(row[0]-t)<1e-8,'Missing aligned scalar')
            for edge in ('01','12','02'):
                require(abs(sum(d[j,dn.index(f'I{edge}_m{m}')] for m in range(8))-row[sn.index('I'+edge)])<1e-9,'Mask currents do not sum')
            for s in range(9):
                valid=d[j,dn.index(f'valid_s{s}')]>0.5
                for key in [f'N_s{s}_cut{k}' for k in range(3)]+[f'W_s{s}']:
                    require(bool(np.isfinite(d[j,dn.index(key)]))==valid,'Wrong null encoding')
        ref=summary['reference']
        if ref is not None:
            take=(a[:,0]>=T-10-1e-8)&np.isclose(a[:,0]/2,np.round(a[:,0]/2),atol=1e-9)
            mean=simpson(a[take,1:],x=a[take,0],axis=0)/10
            require(np.allclose(mean,[ref[k] for k in sn[1:]],atol=1e-10,rtol=1e-10),'Reference mean mismatch')
        for j,t in enumerate(e['time']):
            blocks=e['blocks'][j]
            require(np.max(abs(blocks[0]-blocks[1:].sum(axis=0)))<1e-9,'Node reductions do not sum')
            row=a[np.argmin(abs(a[:,0]-t))];dr=d[np.argmin(abs(d[:,0]-t))]
            require(abs(row[0]-t)<1e-8 and abs(dr[0]-t)<1e-8,'Evidence grid mismatch')
            for m in range(8):require(abs(np.trace(blocks[m+1]).real-row[sn.index(f'p_m{m}')])<1e-9,'Evidence mask weight mismatch')
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
    for cid,pair in checks.get('pairs',{}).items():
        coarse=byid[cid]['case']
        fine=next((s['case'] for s in metrics['cases'] if all(s['case'][k]==coarse[k] for k in ('model','phi_over_pi','detuning','dephasing')) and abs(s['case']['dt']-coarse['dt']/2)<1e-12),None)
        require(fine is not None,'Missing dt partner')
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
    numeric=bool(checks.get('pairs')) and all(p['pass_gate'] for p in checks['pairs'].values())
    werror=max([v for p in checks.get('pairs',{}).values() for values in p.get('errors',{}).values() for k,v in values.items() if k.startswith('W_s')]+[0.])
    threshold=max(1e-8,10*werror)
    for j in metrics.get('joint',[]):
        for g in j['GME']:
            minimum=ext[j['id']]['diagnostic'][dn.index(f"W_s{g['state']}")-1][0]
            require(g['minimum']==minimum and g['threshold']==threshold,'GME minimum/error mismatch')
            status='GME_CERTIFIED' if numeric and minimum is not None and minimum < -threshold else 'GME_NOT_CERTIFIED_BY_THIS_FAMILY'
            require(g['status']==status,'Invalid GME status')
    if metrics.get('fit') and metrics['fit'].get('selected') is not None:
        raw=(report/'selected_alpha.json').read_bytes()
        require(hashlib.sha256(raw).hexdigest()==metrics['fit']['selected_alpha_sha256'],'Selection hash mismatch')
        require(json.loads(raw)['alpha']==metrics['fit']['selected']['alpha'],'Selected alpha mismatch')
    # Recompute the published transport table without trusting supplied flags.
    refs={(s['case']['model'],s['case']['phi_over_pi'],s['case']['detuning'],s['case']['dephasing']):s['reference']
          for s in metrics['cases'] if s['case']['dt']==.01 and s['reference'] is not None}
    for g in metrics.get('gaps',[]):
        key=(g['phi_over_pi'],g['detuning'],g['dephasing']);q=refs[('QS',*key)];c=refs[(g['control'],*key)]
        require(abs(g['delta_h']-(q['h']-c['h']))<1e-10,'Gap table mismatch')
        require(abs(g['I12_gap']+g['I02_gap']-g['delta_h'])<1e-9,'Route gap mismatch')
        denom=max(abs(q['h']),1e-8)
        require(abs(g['denominator_QS']-denom)<1e-12 and abs(g['relative_gap']-(q['h']-c['h'])/denom)<1e-9,'Gap denominator mismatch')
    for p in metrics.get('phase',[]):
        key=(p['model'],p['phi_over_pi'],p['detuning'],p['dephasing']);base=(p['model'],0,p['detuning'],p['dephasing'])
        require(abs(p['delta_h']-(refs[key]['h']-refs[base]['h']))<1e-10,'Phase table mismatch')
    gm={(g['control'],g['phi_over_pi'],g['detuning'],g['dephasing']):g['delta_h'] for g in metrics.get('gaps',[])}
    for x in metrics.get('interactions',[]):
        c,e,g=x['control'],x['detuning'],x['dephasing'];v=gm[(c,.5,e,g)]-gm[(c,0,e,g)]-gm[(c,.5,e,.05)]+gm[(c,0,e,.05)]
        require(abs(x['value']-v)<1e-10,'Interaction table mismatch')
    return dict(status='VERIFIED_EXPORTED_ARRAYS',cases=computed,
                limitations=man['limitations'],runtime_acceptance='requires external run.json and user review')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('report');args=parser.parse_args()
    print(json.dumps(verify(args.report),ensure_ascii=False,indent=2))
