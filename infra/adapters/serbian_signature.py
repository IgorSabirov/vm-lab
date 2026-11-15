"""Existing bounded C++ build plus four explicitly declared matrix probes."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def run(root, output, config):
    root, output = Path(root), Path(output)
    subprocess.run([sys.executable, str(root/'tools/piecewise_flat_qg/build_and_check.py'),
                    '--build', str(output/'build'), '--report', str(output/'BUILD.json')],
                   check=True, timeout=310)
    spec = importlib.util.spec_from_file_location('pinned_signature', root/'tools/piecewise_flat_qg/signature_kernel.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    matrices = []
    for row in config['fixtures']:
        a, b, c = row['sides']
        off = (a*a+b*b-c*c)/2
        matrices.append([[a*a, off], [off, b*b]])
    observed = module.SignatureKernel(output/'build/libvm_signature.so').classify(matrices, strict=False)
    return {'method': 'SERBIAN_SIGNATURE_KERNEL', 'matrices': matrices,
            'observed': {k: v.tolist() for k, v in observed.items()},
            'build_passed': json.loads((output/'BUILD.json').read_text())['passed'],
            'interpretation': 'Representation and classifier diagnostics; no emergence of time claim'}
