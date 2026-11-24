"""Exercise the complete CMB audit/replay path using diagnostic real spectra.

Ten logical P9 task slots reuse two explicitly identified CLASS controls.
No extra CLASS solves or physical five-corner histories are claimed.
"""
from __future__ import annotations

import argparse
import inspect
from pathlib import Path
import shutil
import sys
import time

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOFTWARE))
from r135.backends import run_external_cmb
from r135.common import canonical_hash, read_json, sha256, write_json
from r135.external_cmb import ACT, SPT
from r135.external_cmb_audit import audit_external_cmb, CORNERS, ENGINES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, required=True,
                        help='complete fresh output of validate_native.py, including raw CLASS files')
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('choose a new output directory')
    args.out.mkdir(parents=True)
    start = time.monotonic()
    source = read_json(args.control/'VALIDATION.json')
    if source.get('status') != 'PASS' or source.get('physical_R135_run') is not False:
        raise ValueError('use the explicitly diagnostic real CLASS control')
    config = {'_mode': 'validation', 'external_cmb': {
        'variants': [ACT, SPT], 'cache': str(args.cache.resolve()), 'offline': True,
        'spt_tau_prior': 'include', 'profile_nuisance': False,
        'python': sys.executable, 'python_sha256': sha256(Path(sys.executable))}}
    tasks, labels = {}, {}
    stage = args.out/'stage'
    for engine in ENGINES:
        for index, corner in enumerate(CORNERS):
            tag = f'{engine}/{corner}'
            label = 'baseline' if index == 0 else 'As_plus_2_percent'
            directory = stage/'class'/engine/corner
            # Complete original receipts and raw outputs are copied unchanged.
            shutil.copytree(args.control/'class'/label, directory)
            path = directory/'spectra.json'
            tasks[tag] = {'path': str(path.resolve()), 'sha256': sha256(path)}
            labels[tag] = label
    write_json(args.out/'config.json', config)
    produced, _ = run_external_cmb(config, tasks, {}, stage)
    report = audit_external_cmb(stage, config,
                               {'external_cmb': config['external_cmb']}, args.out/'independent_replay')
    if not report['native_likelihood_replayed'] or report['status'] != 'PARTIAL':
        raise RuntimeError('audit did not replay real native likelihoods or overstated physical completion')
    summary = {'schema': 'R135-external-CMB-audit-control-v1', 'status': 'PASS',
        'scope': 'DIAGNOSTIC_REAL_NATIVE_REPLAY_WITH_RELOCATED_CLASS_INPUTS',
        'physical_R135_run': False, 'unique_CLASS_solutions': 2, 'new_CLASS_solves': 0,
        'logical_P9_slots': labels, 'source_control_sha256': sha256(args.control/'VALIDATION.json'),
        'source_adapter_sha256': sha256(SOFTWARE/'r135/external_cmb.py'),
        'source_auditor_sha256': sha256(SOFTWARE/'r135/external_cmb_audit.py'),
        'runner_sha256': sha256(Path(__file__)),
        'produced_evaluations_sha256': canonical_hash(produced), 'audit': report,
        'elapsed_seconds': time.monotonic() - start,
        'limitations': ['ten diagnostic slots reuse two real spectra; no physical five-corner interpretation',
                        'no CLASS precision refinement or common cosmological optimization',
                        'no confidence calibration or combined Planck/ACT/SPT likelihood']}
    write_json(args.out/'VALIDATION.json', summary)
    print({k: summary[k] for k in ('status', 'elapsed_seconds', 'unique_CLASS_solutions', 'new_CLASS_solves')})


if __name__ == '__main__':
    main()
