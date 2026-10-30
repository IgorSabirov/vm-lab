"""Report-only verifier for IC retry; no engine imports."""
import json
import numpy as np
from .export import digest
from .ic_status import decide_ic_status


def verify_report(report):
    m=json.loads((report/'metrics.json').read_text());c=json.loads((report/'checks.json').read_text())
    summaries=m['trajectory_summaries'];work=m['work']
    if work['steps']!=sum(s['steps'] for s in summaries) or work['rhs_calls']!=4*work['steps']:
        raise ValueError('Work counters mismatch')
    if any(s['steps']!=round(s['horizon']/s['case']['dt']) or s['failed'] for s in summaries):
        raise ValueError('Incomplete trajectory')
    if any(s['scalar_records']!=round(s['horizon']/.2)+1 or s['diagnostic_records']!=round(s['horizon']/2)+1 for s in summaries):
        raise ValueError('Measurement counters mismatch')
    if c['volume_pass'] is not True or c['failures']:raise ValueError('Failed report checks')
    fit=m.get('fit')
    if fit:
        records=fit['records']
        if fit['hop_in_objective'] is not False or fit['calls']!=len(records):raise ValueError('Fit contract violated')
        if fit['computations']!=len({r['computation'] for r in records}) or fit['cache_hits']!=sum(r['cache_hit'] for r in records):
            raise ValueError('Fit accounting mismatch')
        for start in fit['starts']:
            rows=[r for r in records if r['start_factor']==start['factor']]
            stars=[r for r in rows if r['phase']=='star']
            if len(rows)>47 or len(stars)!=7:raise ValueError('Search budget/coverage violated')
            for axis in range(3):
                if len({r['alpha'][axis] for r in stars})<2:raise ValueError('Missing coordinate exploration')
                if start['coverage'][axis]['distinct']!=len({r['alpha'][axis] for r in rows}):raise ValueError('False coverage')
        target=np.array(m['target']);valid=[]
        for r in records:
            if len(r['alpha'])!=3 or min(r['alpha'])<1e-4 or max(r['alpha'])>2:raise ValueError('Rate bounds')
            source=next(s for s in summaries if s['case']['id']==f"RETRY_FIT_{r['computation']:03d}")
            valid_source=source['failed'] is None and source['stationarity']['pass_gate'] and source['reference'] is not None
            if r['valid']!=valid_source:raise ValueError('Fit validity differs from trajectory')
            if r['valid']:
                if max(abs(np.array(r['values'])-np.array([source['reference'][k] for k in m['target_fields']])))>1e-12:
                    raise ValueError('Fit values differ from trajectory reference')
                err=(np.array(r['values'])-target)/target
                if max(abs(err-np.array(r['residual'])))>1e-12 or abs(max(abs(err))-r['maximum_error'])>1e-12:
                    raise ValueError('False structural residual')
                valid.append(r)
        selected=fit['selected']
        if valid:
            best=min(valid,key=lambda r:(r['maximum_error'],r['objective'],tuple(r['alpha'])))
            if selected['computation']!=best['computation']:raise ValueError('Wrong selected candidate')
            if digest(report/'selected_alpha.json')!=fit['selected_alpha_sha256']:raise ValueError('Selection hash changed')
        if m['ic_status']!=decide_ic_status(fit,m.get('validation'),m.get('transport')):
            raise ValueError('False IC status')
        validation=m.get('validation')
        if validation:
            vs=[s for s in summaries if s['case']['family']=='retry_validation']
            if len(vs)!=2:raise ValueError('Incomplete validation pair')
            errors=[abs(np.array([s['reference'][k] for k in m['target_fields']])-target)/target for s in vs]
            if np.max(abs(np.array(errors)-validation['relative_errors']))>1e-12:raise ValueError('False validation errors')
            passed=bool(max(np.max(x) for x in errors)<=.01 and validation['pair']['pass_gate'] and all(s['stationarity']['pass_gate'] and s['failed'] is None for s in vs))
            if passed!=validation['structural_pass']:raise ValueError('False structural validation decision')
            if validation['selected_alpha_sha256']!=fit['selected_alpha_sha256']:raise ValueError('Validation candidate changed')
    return dict(status='VERIFIED_RETRY_REPORT',trajectory_count=len(summaries),steps=work['steps'])

