"""Independent semantic checks after the GitHub transport/hash verifier."""
import csv
import io
import json
import math


def verify(artifacts):
    get=lambda name:json.loads(artifacts['files/'+name])
    m=get('metrics.json');manifest=get('data_manifest.json');checks=get('checks.json')
    config=m['protocol']
    expected={c['id']:c for c in config['cases']}
    assert set(m['cases'])==set(expected), 'case lost/added'
    assert len(expected)==m['planned_cases']==m['actual_cases'], 'case count'
    assert m['source_commit']==manifest['source_commit'] and m['run_id']==manifest['run_id'], 'identity'
    assert manifest['full_file_count']==len(manifest['full_files']), 'manifest count'
    assert manifest['full_bytes']==sum(x['bytes'] for x in manifest['full_files']), 'manifest size sum'
    assert len({x['vm_path'] for x in manifest['full_files']})==len(manifest['full_files']), 'manifest duplicate'
    total=0
    for cid,case in expected.items():
        data=m['cases'][cid];s=data['summary'];assert data['status']=='completed'
        steps=round(case['horizon']/case['dt']);total+=steps
        assert s['steps']==steps and s['rhs_calls']==4*steps
        assert s['scalar_records']==round(case['horizon']/config['integration']['observable_interval'])+1
        assert s['snapshots']==round(case['horizon']/config['integration']['rho_interval'])+1
        snaps=[x for x in manifest['full_files'] if '/states/'+cid+'/' in x['vm_path']]
        assert len(snaps)==s['snapshots'], 'manifest missing case checkpoint'
        wanted={f'rho_step{step:06d}.npz' for step in range(0,steps+1,round(config['integration']['rho_interval']/case['dt']))}
        assert {x['vm_path'].split('/')[-1] for x in snaps}==wanted, 'checkpoint grid'
        rows=list(csv.DictReader(io.StringIO(artifacts['files/series/'+cid+'.csv'].decode())))
        assert len(rows)==data['coverage']['published_records']
        times=[float(r['time']) for r in rows]
        assert times[0]==0 and times[-1]==case['horizon'] and all(b>a for a,b in zip(times,times[1:]))
        for key in rows[0]:
            if key=='time':continue
            values=[float(r[key]) for r in rows]
            assert all(math.isfinite(v) for v in values)
            st=data['statistics'][key]
            assert math.isclose(values[-1],s['final_observables'][key],rel_tol=1e-12,abs_tol=1e-12), 'final differs'
            assert math.isclose(min(values),st['min'],rel_tol=1e-12,abs_tol=1e-12), 'min differs'
            assert math.isclose(max(values),st['max'],rel_tol=1e-12,abs_tol=1e-12), 'max differs'
        for row in rows:
            v={k:float(x) for k,x in row.items()}
            assert abs(v['dn2_dt']-(v['I_hop_sink']+v['I_form_sink']+v['I_idle_sink']-v['sink_flux']))<1e-9, 'node balance'
            assert abs(v['B_L_total']+v['M_L_total']+v['E_L_total']-v['sum_pL'])<1e-9, 'partition'
        st=s['stationarity'];tol=config['stationarity']
        predicted=(case['horizon']>=10 and st['max_relative_rhs']<=tol['relative_rhs'] and st['relative_flux_range']<=tol['relative_flux_range'] and st['relative_rho_change']<=tol['relative_rho_change'])
        assert st['passed']==predicted, 'stationarity PASS mismatch'
    assert total==m['actual_steps']==m['planned_steps'], 'total steps'
    for check in checks:
        if check['name'].startswith('operators_'):
            assert check['passed']==(check['actual_max']<=check['limit'])
        if check['name'].startswith('refinement_'):
            assert check['passed']==(check['max_all_observable_difference']<=config['acceptance']['refinement_observables'])
    return {'passed':True,'cases':len(expected),'steps':total,'scope':'Published CSV endpoints/extrema, balances, case/step/checkpoint grid, manifest totals and selected threshold labels. Does not authenticate raw VM contents or prove honest execution.'}
