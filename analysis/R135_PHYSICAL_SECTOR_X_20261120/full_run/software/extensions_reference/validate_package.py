"""Replay the extension regression tests and the supplied P7 command example.

Native scientific controls have their own reproducible executors. This command
records those saved results by hash; it does not claim to rerun them.
"""
from __future__ import annotations

import argparse
import datetime
import json
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
REPO = SOFTWARE.parents[3]
sys.path.insert(0, str(SOFTWARE))
from r135.common import file_record, read_json, sha256, write_json
from r135.contracts import source_inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error('choose a new output directory')
    out.mkdir(parents=True)
    before = source_inventory()
    started = time.monotonic()
    commands = []

    def run(label, command, cwd=SOFTWARE):
        t0 = time.monotonic()
        completed = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        log = out / (label + '.log')
        log.write_text(completed.stdout)
        count = re.search(r'Ran (\d+) tests?', completed.stdout)
        skipped = re.search(r'OK \(skipped=(\d+)\)', completed.stdout)
        commands.append(dict(label=label, command=[str(x) for x in command],
                             cwd=str(cwd.relative_to(REPO)),
                             elapsed_seconds=time.monotonic()-t0,
                             exit_code=completed.returncode, log_sha256=sha256(log),
                             tests=int(count[1]) if count else None,
                             skipped=int(skipped[1]) if skipped else 0))
        if completed.returncode:
            write_json(out/'FAILED.json', {'commands': commands})
            raise RuntimeError(f'{label} failed; inspect {log}')

    run('core', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
    run('p0', [sys.executable, '-m', 'unittest', 'discover', '-s', '.',
               '-p', 'test_p0_register.py', '-v'])
    run('registry', [sys.executable, 'tools/registry_links.py',
                     '--summary', str(out/'registry.json')], REPO)
    with tempfile.TemporaryDirectory(prefix='r135-nonthermal-example-') as tmp:
        tmp = Path(tmp)
        cli = str(SOFTWARE/'r135_stage.py')
        run('example_seal', [sys.executable, cli, '--seal', '--stage', 'P7',
                            '--config', 'examples/nonthermal_control.json',
                            '--template', 'examples/request.coupled.validation.json',
                            '--out', str(tmp/'request.json')])
        run('example_run', [sys.executable, cli, '--stage', 'P7', '--request',
                           str(tmp/'request.json'), '--out', str(tmp/'result')])
        run('example_verify', [sys.executable, cli, '--verify', str(tmp/'result')])
        write_json(out/'example_balance.json', read_json(tmp/'result/balance.json'))

    after = source_inventory()
    if before != after:
        raise RuntimeError('executed source changed during validation')
    references = [
        'extensions_reference/p7_bbn_control/VALIDATION.json',
        'neutrino_reference/native_born_reference.json',
        'cascade_validation/results/summary.json',
        'perturbations_reference/native_control/report.json',
        'pockets_reference/control/summary.json',
    ]
    import numpy, scipy
    result = dict(
        schema='R135-extension-validation-v1', status='PASS',
        scope='DEVELOPMENT_TESTS_AND_DIAGNOSTIC_CONTROLS', physical_R135_run=False,
        scientific_acceptance='owner_review',
        recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        execution_identity='exact source inventory; extensions were uncommitted during this validation',
        source_sha256=before['sha256'], source_unchanged_during_validation=True,
        source_files=before['files'],
        test_sources=[file_record(p,REPO) for p in sorted((SOFTWARE/'tests').glob('test_*.py'))],
        environment=dict(python=platform.python_version(), numpy=numpy.__version__, scipy=scipy.__version__),
        commands=commands, elapsed_seconds=time.monotonic()-started,
        saved_native_controls=[file_record(SOFTWARE/p,SOFTWARE) for p in references],
        native_controls_reexecuted_by_this_command=False,
        limitations=['optional native tests skipped here are recorded in the core log',
                     'dedicated native controls use their own environments and source manifests',
                     'these development timings are not a full physical-run resource forecast'])
    write_json(out/'VALIDATION.json', result)
    print(json.dumps({k:result[k] for k in ('status','elapsed_seconds','commands')},indent=2))


if __name__ == '__main__':
    main()
