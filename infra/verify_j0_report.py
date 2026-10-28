"""Semantic verification of GitHub artifacts; transport hashes checked separately."""
import csv
import io
import json
import numpy as np
from scipy.integrate import simpson


def verify(artifacts):
    get=lambda name:json.loads(artifacts['files/'+name])
    m=get('metrics.json');man=get('data_manifest.json');checks=get('checks.json')
    cfg=m['protocol'];planned={c['id']:c for c in cfg['cases']}
    assert set(m['cases'])==set(planned)
    assert m['run_id']==man['run_id'] and m['source_commit']==man['source_commit']
    assert man['full_file_count']==len(man['full_files'])
    assert man['full_bytes']==sum(f['bytes'] for f in man['full_files'])
    assert len({f['vm_path'] for f in man['full_files']})==len(man['full_files'])
    arrays={}
    for cid,r in m['cases'].items():
        s=r['summary']; assert s is not None and r['case']==planned[cid]
        rows=list(csv.DictReader(io.StringIO(artifacts['files/ledger/'+cid+'.csv'].decode())))
        names=list(rows[0]);a={k:np.array([float(x[k]) for x in rows]) for k in names};t=a['time'];arrays[cid]=a
        n=round(planned[cid]['horizon']/cfg['integration']['observable_interval'])+1
        assert len(t)==n==s['scalar_records']
        assert np.allclose(t,np.arange(n)*cfg['integration']['observable_interval'],atol=1e-10,rtol=0)
        assert s['steps']==round(planned[cid]['horizon']/planned[cid]['dt'])
        assert s['snapshots']==round(planned[cid]['horizon']/cfg['integration']['rho_interval'])+1
        for k in names[1:]:
            assert np.isclose(a[k][-1],s['final_observables'][k],atol=1e-13,rtol=1e-12)
            for field,val in [('min',min(a[k])),('max',max(a[k])),('mean',a[k].mean()),('stddev',a[k].std())]:
                assert np.isclose(val,r['statistics'][k][field],atol=1e-13,rtol=1e-12)
        integ=s['integrals']
        for k in ['sink_flux','I_hop_sink','I_form_sink','I_idle_sink','pump_flux','break_flux']:
            assert np.isclose(simpson(a[k],x=t),integ[k],atol=1e-11,rtol=1e-11)
        stored=a['n2'][0]-a['n2'][-1]
        assert np.isclose(stored,integ['stored_sink'],atol=1e-13)
        residual=integ['sink_flux']-sum(integ[k] for k in ['I_hop_sink','I_form_sink','I_idle_sink'])-stored
        assert np.isclose(residual,integ['sink_balance_residual'],atol=1e-12)
        stat=s['stationarity'];lim=cfg['stationarity'];recent=a['sink_flux'][t>=t[-1]-10-1e-9]
        fluxrange=float(np.ptp(recent));bound=lim['absolute_flux_range']+lim['relative_flux_range']*abs(recent[-1])
        assert np.isclose(fluxrange,stat['absolute_flux_range'],atol=1e-13)
        assert np.isclose(bound,stat['flux_range_bound'],atol=1e-13)
        expected=bool(t[-1]>=10 and stat['max_relative_rhs']<=lim['relative_rhs'] and fluxrange<=bound and stat['relative_rho_change']<=lim['relative_rho_change'])
        assert stat['passed']==expected
    refs={r['model']:r for r in m['comparisons']['refinements']}
    for mid,r in refs.items():
        coarse=arrays[mid+'_mix'];fine=arrays[mid+'_fine']
        for key in coarse:
            if key=='time':continue
            error=float(np.max(np.abs(coarse[key]-fine[key])))
            assert np.isclose(error,r['per_observable'][key],rtol=1e-10,atol=1e-13)
        assert r['passed']==(r['max_all_observable_difference']<=cfg['acceptance']['refinement_observables'])
    for r in m['interventions']:
        mids=['j0_'+r['variant'],'j1_'+r['variant']]
        expected=all(m['cases'][mid+'_'+label]['summary']['stationarity']['passed'] for mid in mids for label in ['mix','fine']) and all(refs[mid]['passed'] for mid in mids)
        assert r['steady_comparison_eligible']==expected
        f0=arrays['j0_'+r['variant']+'_mix']['sink_flux'][-1];f1=arrays['j1_'+r['variant']+'_mix']['sink_flux'][-1]
        assert np.isclose(r['F_J0'],f0,atol=1e-13) and np.isclose(r['F_J1'],f1,atol=1e-13)
        if abs(f1)>cfg['ratio_denominator_floor']:assert np.isclose(r['ratio'],f0/f1,atol=1e-12)
        else:assert r['ratio'] is None
    for r in checks:
        if r['name'].startswith(('zero_hop_','null_flux_','inventory_ledger_')):
            assert r['passed']==(r['actual']<=r['limit'])
        if r['name'].startswith('ledger_'):assert r['passed']==(abs(r['residual'])<=r['limit'])
    assert m['actual_steps']==sum(r['summary']['steps'] for r in m['cases'].values())
    return dict(passed=True,cases=len(planned),steps=m['actual_steps'])
