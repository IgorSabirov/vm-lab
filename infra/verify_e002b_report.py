"""Independent CSV arithmetic for E002b-A. No experiment module imports."""
import csv
import json
from pathlib import Path
import numpy as np
from scipy.integrate import simpson


def verify(root):
    root=Path(root);m=json.loads((root/'metrics.json').read_text());cfg=m['protocol']
    checks=json.loads((root/'checks.json').read_text());refs={}
    assert set(m['cases'])=={c['id'] for c in cfg['cases']}
    def read(path):
        with path.open(newline='') as f: rows=list(csv.DictReader(f))
        a={k:np.array([float(r[k]) for r in rows]) for k in rows[0]}
        assert all(np.isfinite(v).all() for v in a.values())
        return a
    for cid,c in m['cases'].items():
        p=read(root/'pre'/f'{cid}.csv');t=p['time']
        expected=np.arange(round(cfg['baseline_window']/cfg['observable_interval'])+1)*cfg['observable_interval']+cfg['horizon']-cfg['baseline_window']
        assert len(t)==len(expected) and np.allclose(t,expected,atol=1e-10,rtol=0)
        ref={k:float(simpson(v,x=t)/(t[-1]-t[0])) for k,v in p.items() if k!='time'}
        refs[cid]=ref
        for k,v in ref.items():assert np.isclose(v,c['reference'][k],atol=1e-12,rtol=1e-12),(cid,k)
        a=read(root/'series'/f'{cid}.csv');tt=a['time']
        assert len(tt)==round(cfg['horizon']/cfg['observable_interval'])+1
        assert np.allclose(tt,np.arange(len(tt))*cfg['observable_interval'],atol=1e-10,rtol=0)
        assert c['steps']==round(cfg['horizon']/c['case']['dt']) and c['rhs_calls']==4*c['steps']
        for k,v in a.items():
            if k=='time':continue
            for label,value in [('min',min(v)),('max',max(v)),('mean',v.mean())]:
                assert np.isclose(c['statistics'][k][label],value,atol=1e-12,rtol=1e-12)
    assert m['actual_steps']==sum(c['steps'] for c in m['cases'].values())==cfg['runtime_forecast']['main_steps']
    structural_checks=[c for c in checks if c['name'] not in {'runtime_gate','report_budget'}]
    valid=not m['failure'] and all(c['passed'] for c in structural_checks)
    limits=cfg['matching']
    for candidate in cfg['candidates']:
        a,b=refs[candidate+'_fine'],refs['RR_'+candidate+'_fine']
        errors={}
        for e in ['01','12','02']:
            target=sum(a['event_rate__'+k+'_'+e] for k in ['break','background','idle'])
            actual=sum(b['event_rate__'+k+'_'+e] for k in ['break','background','idle'])
            errors['pL_'+e]=abs(b['pL'+e]-a['pL'+e])/max(abs(a['pL'+e]),1e-12)
            errors['loss_'+e]=abs(actual-target)/max(abs(target),1e-12)
            errors['renew_'+e]=abs(b['event_rate__renew_'+e]-target)/max(abs(target),1e-12)
        hop=abs(b['I_hop_sink']-a['I_hop_sink'])/max(abs(a['I_hop_sink']),1e-12)
        result=m['provisional_pair_decisions'][candidate]
        for k,v in errors.items():assert np.isclose(v,result['relative_errors'][k],atol=1e-12,rtol=1e-12)
        assert np.isclose(hop,result['hop_relative_error'],atol=1e-12)
        weak=min(a['I_hop_sink'],b['I_hop_sink'])<=limits['weak_hop_floor']
        if not valid or weak:state,grade='matching_numerical_failure','ineligible'
        elif any(v>limits['population_relative'] if k.startswith('pL_') else v>limits['loss_relative'] if k.startswith('loss_') else v>limits['renew_relative'] for k,v in errors.items()):
            state,grade='no_matched_control','ineligible'
        elif hop>limits['hop_max_relative']:state,grade='structural_matched_hop_mismatch','ineligible'
        else:state,grade='matched_control_found','preferred_le_5pct' if hop<=limits['hop_preferred_relative'] else 'limited_gt5_le10pct'
        assert (result['state'],result['grade'])==(state,grade)
        accepted=m['pair_decisions'][candidate]
        assert accepted['damage_eligible']==(state=='matched_control_found' and not m['acceptance_blockers'])
        assert accepted['state']==('matching_numerical_failure' if m['acceptance_blockers'] else state)
    expected_blockers={c['name'] for c in checks if not c['passed']}
    if m['failure']:expected_blockers.add('task_failure')
    if cfg['mode']!='production':expected_blockers.add('test_mode_not_scientific')
    assert set(m['acceptance_blockers'])==expected_blockers
    assert m['automatic_damage_launch'] is False
    manifest=json.loads((root/'data_manifest.json').read_text())
    assert len(manifest['full_files'])==manifest['full_file_count']
    assert sum(x['bytes'] for x in manifest['full_files'])==manifest['full_bytes']
    return {'arithmetic_passed':True,'cases':len(m['cases']),'steps':m['actual_steps'],'scientific_status':m['acceptance_status']}


if __name__=='__main__':
    import sys
    print(json.dumps(verify(sys.argv[1])))
