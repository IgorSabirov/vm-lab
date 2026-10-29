"""Recheck the pinned E002 GitHub package and derive post-hoc diagnostics.

Usage: python3 audit.py DOWNLOADED_RUN --output audit.json
DOWNLOADED_RUN contains run.json, files/, output.log, and source/ fetched
from the result/source commits below. No VM reads or new simulations.
The pinned pre-run verifier recomputes all published CSV metrics; this
script adds source/inventory, timing, matching, and interpretation checks.
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.integrate import simpson

RESULT_COMMIT = '06b767966c5ecce5f2c38936361c8eee74ffca97'
SOURCE_COMMIT = '9809c90cd3d3042157a6aa2f28ec09889f7b7651'
RUN_ID = 'E002_GH_v001_r001'


def audit(root):
    receipt = json.loads((root / 'run.json').read_text())
    metrics = json.loads((root / 'files/metrics.json').read_text())
    cfg = metrics['protocol']
    actual = receipt['job']['finished'] - receipt['job']['started']
    forecast = cfg['runtime_forecast']
    assert forecast['lower_seconds'] <= actual <= forecast['upper_seconds']
    runtime = dict(actual_seconds=actual, expected_seconds=forecast['expected_seconds'],
        deviation_percent=100*(actual/forecast['expected_seconds']-1),
        lower_seconds=forecast['lower_seconds'], upper_seconds=forecast['upper_seconds'],
        internal_seconds=metrics['runtime_gate']['actual_seconds'],
        status='PASS')
    sys.path.insert(0, str(root / 'source/infra'))
    from github_result_reader import read_github_result
    from verify_e002_report import verify

    def fetch(repository, path, commit):
        assert repository == 'IgorSabirov/vm-lab' and commit == RESULT_COMMIT
        prefix = f'results/{RUN_ID}/'
        assert path.startswith(prefix)
        return (root / path.removeprefix(prefix)).read_bytes()

    verified = read_github_result(fetch, repository='IgorSabirov/vm-lab',
        result_commit=RESULT_COMMIT, run_id=RUN_ID, source_commit=SOURCE_COMMIT)
    assert verified['execution_succeeded']
    csv_check = verify(verified['artifacts'])
    for path, digest in receipt['input_sha256'].items():
        assert hashlib.sha256((root/'source'/path).read_bytes()).hexdigest() == digest, path
    config_bytes = (root/'source/config.json').read_bytes()
    assert hashlib.sha256(config_bytes).hexdigest() == metrics['config_sha256']
    assert json.loads(config_bytes) == cfg
    assert receipt['export_errors'] == receipt['full_data_inventory_errors'] == []
    manifest = json.loads((root/'files/data_manifest.json').read_text())
    inventory_a = {f['path']:f['bytes'] for f in receipt['full_data']}
    inventory_b = {f['vm_path']:f['bytes'] for f in manifest['full_files']}
    assert len(inventory_a) == len(receipt['full_data'])
    assert len(inventory_b) == len(manifest['full_files'])
    assert inventory_a == inventory_b
    assert all(len(f['sha256']) == 64 for f in manifest['full_files'])
    checks = json.loads((root/'files/checks.json').read_text())
    assert all(c['passed'] for c in checks)

    def arrays(folder, cid):
        with (root/'files'/folder/(cid+'.csv')).open(newline='') as f:
            rows = list(csv.DictReader(f))
        return {k:np.array([float(row[k]) for row in rows]) for k in rows[0]}

    cases = metrics['cases']
    refs = {}
    recovery = {}
    for cid, case in cases.items():
        a = arrays('pre', cid)
        refs[cid] = {k:float(simpson(v,x=a['time'])/(a['time'][-1]-a['time'][0]))
                    for k,v in a.items() if k!='time'}
        recovery[cid] = arrays('series', cid)
        s = case['summary']; spec = s['case']
        assert s['steps'] == round(spec['horizon']/spec['dt'])
        assert s['rhs_calls'] == 4*s['steps']
        assert s['records'] == 1501 and len(s['snapshots']) == 55
        assert s['pre_stationarity']['passed'] and s['final_stationarity']['passed']
        assert spec['dt'] == (0.005 if cid.endswith('_fine') else 0.01)
    assert sum(c['summary']['steps'] for c in cases.values()) == 2190000
    assert sum(c['summary']['rhs_calls'] for c in cases.values()) == 8760000

    # Reconstruct the matched dissipative losses from CSV means and fixed rates.
    # PP formation_current is a NET coherent conversion current, not a count of
    # forward coherent jumps. Equality to loss is used only on the steady window.
    matching = {}
    for variant, factor in [('RR',1),('RR2',2)]:
        a = refs[variant+'_none_fine']; b = refs['PP_none_fine']
        p = cfg['models'][variant]
        errors = {k:abs(a[k]-b[k])/max(abs(b[k]),1e-12)
                  for k in ['pL01','pL12','pL02','inventory','pump_flux','break_flux']}
        for e in ['01','12','02']:
            alpha,beta = p['rr_rates'][e]
            target = factor*b['formation_current'+e]
            population_r = 1-(1+p['delta']/p['eta'])*a['pL'+e]
            loss = (p['delta']+p['gamma_bg']+beta)*a['pL'+e]
            renew = alpha*population_r
            errors['loss_'+e] = abs(loss-target)/max(abs(target),1e-12)
            errors['renew_'+e] = abs(renew-target)/max(abs(target),1e-12)
        assert max(errors.values()) <= cfg['matching_tolerance']
        matching[variant] = dict(max_relative_error=max(errors.values()),
            baseline_hop_difference_percent=100*(a['I_hop_sink']/b['I_hop_sink']-1),
            loss_target_factor=factor)

    table = {}
    for variant in cfg['models']:
        cid=variant+'_link_fine'; none=variant+'_none_fine'
        case=cases[cid]; rec=case['recovery']; ref=refs[none]
        q=rec['integrals']; base=cases[none]['recovery']['integrals']
        a=recovery[cid]; t=a['time']; row={
            'Lambda_hop':rec['Lambda_hop'], 'Lambda_total':rec['Lambda_total'],
            'baseline_hop':ref['I_hop_sink'], 'baseline_F':ref['sink_flux'],
            'Qhop':q['I_hop_sink'], 'QF':q['sink_flux'], 'Qpump':q['pump_flux'],
            'excess_Qpump':q['pump_flux']-base['pump_flux'],
            'signed_absolute_hop_loss':base['I_hop_sink']-q['I_hop_sink'],
            'machine_share':rec['machine_share'],
            'DeltaQform':q['I_form_sink']-base['I_form_sink'],
            'DeltaQidle':q['I_idle_sink']-base['I_idle_sink']}
        for observable in ['I_hop_sink','sink_flux']:
            if ref[observable]<=1e-8: continue
            normalized=a[observable]/ref[observable]
            bad=np.flatnonzero(normalized < .9)
            last = int(bad[-1]) if len(bad) else -1
            tau = float(t[last+1]-200) if last+1<len(t) else None
            clipped = float(simpson(np.maximum(0,1-normalized),x=t))
            signed = float(simpson(1-normalized,x=t))
            row[observable+'_diagnostic'] = dict(
                min_fraction=float(normalized.min()),
                t_min=float(t[normalized.argmin()]-200),
                t90_stay_on_0p2_grid=tau,
                overshoot_area=clipped-signed)
        if ref['I_hop_sink']>1e-8:
            row['ledger_only_percent']=100*(1-q['I_hop_sink']/base['I_hop_sink'])
            row['Lambda_minus_ledger_percent']=rec['Lambda_hop']-row['ledger_only_percent']
        table[variant]=row

    pp=table['PP']['Lambda_hop']; rr=table['RR']['Lambda_hop']
    assert pp<=50 and rr>1e-8 and pp>.7*rr
    assert metrics['primary_outcome']=='repair_not_better_than_control'
    assert pp>.7*table['RR2']['Lambda_hop']
    assert metrics['RR2_outcome']=='repair_not_better_than_control'
    pairs=[]
    for left,right in [('PP','QP'),('PQ','QQ'),('PS','QS')]:
        l,r=table[left],table[right]
        ratio=l['Lambda_hop']/r['Lambda_hop']
        assert np.isclose(ratio,next(q['ratio'] for q in metrics['qualifiers']
                                    if q['left']==left and q['right']==right),atol=1e-8)
        pairs.append(dict(left=left,right=right,ratio=ratio,
            P_excess_percent=100*(ratio-1),Q_reduction_percent=100*(1-1/ratio),
            absolute_loss_P_excess_percent=100*(l['signed_absolute_hop_loss']/r['signed_absolute_hop_loss']-1)))
    refinement=[]
    for cid in metrics['refinements']:
        fid=cid.replace('_coarse','_fine'); a,b=recovery[cid],recovery[fid]
        delta=max(float(np.max(abs(a[k]-b[k]))) for k in a if k!='time')
        assert 0<delta<2e-5
        refinement.append(delta)
    return dict(result_commit=RESULT_COMMIT,source_commit=SOURCE_COMMIT,run_id=RUN_ID,
        runtime=runtime,technical_status='VERIFIED_GITHUB_PACKAGE',
        user_acceptance='NOT_ASSIGNED_BY_ASSISTANT',
        artifacts_verified=len(receipt['files']),artifact_bytes=sum(f['bytes'] for f in receipt['files'].values()),
        input_files_verified=len(receipt['input_sha256']),csv_verification=csv_check,
        checks_reported_pass=len(checks),full_inventory_files=len(inventory_a),
        full_inventory_bytes=sum(inventory_a.values()),matrix_snapshots=sum(len(c['summary']['snapshots']) for c in cases.values()),
        all_case_pre_and_final_stationarity_reported=True,
        refinement_pairs=len(refinement),max_published_recovery_delta=max(refinement),
        max_reported_all_observable_delta=max(v['max_observable_delta'] for v in metrics['refinements'].values()),
        matching_recomputed_from_csv=matching,
        primary_outcome=metrics['primary_outcome'],PP_RR_ratio=pp/rr,
        PP_improvement_percent=100*(1-pp/rr),formation_pairs=pairs,
        cases=table,
        J0_damage_retention=table['PP_J0']['QF']/cases['PP_J0_none_fine']['recovery']['integrals']['sink_flux'],
        J0_J1_baseline_ratio=table['PP_J0']['baseline_F']/table['PP']['baseline_F'],
        limitations=['Raw VM density matrices not read; their hashes are reported, not independently rehashed.',
          'Pre/post-window CSV arithmetic verified; density positivity and full-state stationarity rely on published diagnostics.',
          'All 23 published coarse/fine recovery arrays differ; counters and pinned source support separate integration, not execution attestation.',
          't90, excess pump and absolute deficits are post-hoc diagnostics; preregistered primary metric and threshold unchanged.',
          'QQ/PP comparison changes a generator term and its stationary state, not only measured coherence.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.root)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ['runtime','technical_status','artifacts_verified','csv_verification','primary_outcome','PP_improvement_percent']}))
