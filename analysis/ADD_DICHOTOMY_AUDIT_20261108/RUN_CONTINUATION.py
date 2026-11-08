#!/usr/bin/env python3
"""Reproduce the bounded R126 continuation, including the EXPECTED FT10 failure."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OUT = HERE / 'results'
OUT.mkdir(exist_ok=True)
jobs = [
    ('transport_gates', ['--stage','gates'], 0),
    ('orbits_C2_L2_L3', ['--stage','orbits','--lengths','2,3'], 0),
    ('orbits_C2_L4_L5', ['--stage','orbits','--lengths','4,5'], 0),
    ('orbits_other_modes_L2_L4', ['--stage','orbits','--lengths','2,3,4',
        '--modes','LITERAL_DEF4,FIG2A_FULL,PRESERVE_EDGES_LITERAL_BITS','--horizon','32'],0),
    ('named_witnesses', ['--stage','witnesses'],0),
    ('structural_all_words_L1_L5', ['--stage','structural','--lengths','5'],0),
    ('spectra', ['--stage','spectra'],0),
    ('FT10_literal_diagnostics', [],1),
]
start = time.perf_counter()
execution = {'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_sha256':hashlib.sha256((HERE/'CONTINUATION_AUDIT.py').read_bytes()).hexdigest(),
    'job_timeout_seconds':60,'overall_timeout_seconds':180,'VM_jobs':0,'jobs':[]}
for name, args, expected_rc in jobs:
    if name == 'FT10_literal_diagnostics':
        cmd = [sys.executable,str(HERE/'source/ADD_FT10_MINIMAL.py'), '--run-minimal',
               '--json-out',str(OUT/(name+'.json'))]
    else:
        cmd = [sys.executable,str(HERE/'CONTINUATION_AUDIT.py'),*args,'--out',str(OUT/(name+'.json'))]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd,capture_output=True,text=True,
                          timeout=min(60,180-(time.perf_counter()-start)))
    (OUT/(name+'.log')).write_text(proc.stdout+proc.stderr)
    item = {'name':name,'returncode':proc.returncode,'expected_returncode':expected_rc,
            'seconds':time.perf_counter()-t0,'command':cmd}
    execution['jobs'].append(item)
    print(json.dumps(item),flush=True)
    assert proc.returncode == expected_rc, (name,proc.stderr)

def read(name):
    return json.loads((OUT/(name+'.json')).read_text())

checks = {}
rows = read('orbits_C2_L2_L3')['exhaustive']+read('orbits_C2_L4_L5')['exhaustive']
checks['bits_only_all_E0_return_without_transient_L2_L5'] = all(
    r['modes']['FIG2A_BITS_ONLY']['unresolved']==r['modes']['FIG2A_BITS_ONLY']['transients']==0 for r in rows)
checks['bits_only_first_step_counts_match_received'] = [r['modes']['FIG2A_BITS_ONLY']['first'].get('none',0) for r in rows]==[162,1952,24218,301804]
checks['all_word_coverage_includes_1118480_states'] = sum(
    r['all_labelled_words'] for r in read('structural_all_words_L1_L5')['structural']['all_states_not_only_E0'])==1118480
checks['active_period2_counterexample_found'] = read('structural_all_words_L1_L5')['structural']['active_period2_E0_witness'] is not None
g = read('transport_gates')['gates']['tau_port_worldlines']
checks['literal_named_square_fails_all_tagged_cases'] = g['LITERAL_DEF4']['exact_named_pass']==0
checks['bits_only_named_square_fails_all_tagged_cases'] = g['FIG2A_BITS_ONLY']['exact_named_pass']==0
checks['full_figure_named_square_passes_all_tagged_cases'] = g['FIG2A_FULL']['exact_named_pass']==16
ft=read('FT10_literal_diagnostics')
checks['FT10_transport_failure_preserved_not_converted_to_PASS'] = ft['status']=='FAIL' and ft['tests']['FT10B_name_algebra']['status']=='PASS' and ft['tests']['FT10C_C1_split_merge']['status']=='PASS'
s=read('spectra')['spectra']['matrices']
checks['quiet_traces_match_independent_enumeration'] = s['Q_bits_only']['traces_L1_L6'][1:5]==[r['modes']['FIG2A_BITS_ONLY']['first']['none'] for r in rows]
checks['pair_matrix_has_received_194_states_2424_edges'] = s['Q_bits_only']['dimension']==194 and s['Q_bits_only']['transition_edges']==2424
checks['all_stage_reports_use_final_source_hash'] = all(read(n)['source_sha256']==execution['source_sha256'] for n,_,_ in jobs if n!='FT10_literal_diagnostics')
execution['checks'] = checks
execution['audit_validation'] = 'PASS' if all(checks.values()) else 'FAIL'
execution['source_conformance'] = 'NOT_ATTESTED'
execution['NOW_integration'] = 'BLOCKED'
execution['wall_seconds'] = time.perf_counter()-start
(OUT/'execution.json').write_text(json.dumps(execution,ensure_ascii=False,indent=2)+'\n')
assert all(checks.values()),checks
print(json.dumps({'audit_validation':execution['audit_validation'],'checks':len(checks),
                  'wall_seconds':execution['wall_seconds']}),flush=True)
