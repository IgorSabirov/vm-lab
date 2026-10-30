"""Check Copilot's concrete counterexample on verified E002c published blocks."""
import argparse
import hashlib
import json
import runpy
from pathlib import Path
import numpy as np

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--reader', type=Path, default=Path(__file__).with_name('validated_reproduce.py'))
    args = parser.parse_args()
    validate_reduced_blocks = runpy.run_path(str(args.reader))['validate_reduced_blocks']
    source = args.data_root / 'source'
    manifest = json.loads((source/'run.json').read_text())
    cases = json.loads((source/'selected_cases.json').read_text())
    max_hermiticity = 0.
    min_eigen = min_p = min_w = float('inf')
    sample = None
    for case in cases:
        relative = f"evidence/{case['id']}.npz"
        file = source/relative
        metadata = manifest['files']['files/'+relative]
        data = file.read_bytes()
        assert len(data) == metadata['bytes']
        assert hashlib.sha256(data).hexdigest() == metadata['sha256']
        blocks = np.load(file, allow_pickle=False)['blocks'][-1]
        validate_reduced_blocks(blocks)
        max_hermiticity = max(max_hermiticity, float(np.max(abs(blocks-blocks.conj().swapaxes(-1,-2)))))
        min_eigen = min(min_eigen, float(np.min(np.linalg.eigvalsh(blocks))))
        min_p = min(min_p, float(np.min(np.trace(blocks[1:],axis1=-2,axis2=-1).real)))
        for indices in [[1,2,4],[3,5,6]]:
            min_w = min(min_w, min(float(np.trace(b[np.ix_(indices,indices)]).real) for b in blocks[1:]))
        if sample is None:
            sample = blocks.copy()

    # Alter only an in-memory copy, not the hash-verified source file.
    bad = sample.copy()
    bad[0,0,7] += 1e-3j
    bad[1,0,7] += 1e-3j
    trace_error = float(abs(np.trace(bad[0])-1))
    sum_error = float(np.max(abs(bad[0]-bad[1:].sum(axis=0))))
    eig_change = float(np.max(abs(np.linalg.eigvalsh(bad)-np.linalg.eigvalsh(sample))))
    used = [(1,2),(5,6),(1,4),(3,6)]
    current_entries_change = max(float(np.max(abs(bad[:,i,j]-sample[:,i,j]))) for i,j in used)
    assert trace_error < 1e-10 and sum_error < 1e-12
    assert eig_change == 0 and current_entries_change == 0
    rejected = False
    try:
        validate_reduced_blocks(bad)
    except ValueError as exc:
        rejected = str(exc) == 'non-Hermitian reduced blocks'
    assert rejected
    extra_checks = {}
    negative = np.eye(8, dtype=complex)/8
    negative[0,0] = -0.01
    nonfinite = np.eye(8, dtype=complex)/8
    nonfinite[0,0] = np.nan
    for label, invalid, message in [('negative_eigenvalue', negative, 'non-PSD reduced blocks'),
                                    ('nonfinite', nonfinite, 'nonfinite reduced blocks')]:
        try:
            validate_reduced_blocks(invalid)
        except ValueError as exc:
            extra_checks[label] = str(exc) == message
        else:
            extra_checks[label] = False
    assert all(extra_checks.values())
    print(json.dumps(dict(status='PASS', verified_evidence_files=len(cases),
        current_data=dict(max_hermiticity_error=max_hermiticity,min_reduced_eigenvalue=min_eigen,
            min_mask_weight=min_p,min_mask_sector_weight=min_w),
        counterexample=dict(mutation_on_copy_only=True,old_trace_error=trace_error,
            old_mask_sum_error=sum_error,eigvalsh_change=eig_change,current_entries_change=current_entries_change,
            hermiticity_error=float(np.max(abs(bad-bad.conj().swapaxes(-1,-2))))),
        proposed_guard_rejects_counterexample=rejected,
        extra_guard_checks=extra_checks,
        limits='Validates reduced blocks, not full state or the Lindblad generator; manifest trust is external.'),indent=2))

if __name__ == '__main__':
    main()
