#!/usr/bin/env python3
"""Compile pinned gh-aw, cap ALL generated jobs, and record both file hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.2.2'
COMMIT = '399a445fe2d8926c616b54b1b82a16b5b2be4445'
BINARY_SHA256 = 'c2378d85466d29cdbdfebd0e513557b5cbec18d34f44e7cc00c2fa323687a153'
SOURCE = '.github/workflows/copilot-operator.md'
LOCK = '.github/workflows/copilot-operator.lock.yml'
MANIFEST = 'infra/copilot/COMPILE.json'


def bound_jobs(text):
    # Preserve the compiler's YAML formatting/frontmatter hash. The compiler does
    # not allow activation/pre_activation timeout overrides. Cap framework jobs
    # explicitly instead of exempting generated code from repository policy.
    chunks = re.split(r'(?=^  [a-zA-Z_][a-zA-Z_0-9-]*:\n)', text, flags=re.M)
    out = [chunks[0]]
    for part in chunks[1:]:
        # A job has steps/uses; don't rewrite top-level env or dispatch inputs.
        if re.search(r'^    (steps|uses):', part, re.M):
            if re.search(r'^    timeout-minutes:', part, re.M):
                part = re.sub(r'^    timeout-minutes:.*$',
                              lambda m: '    timeout-minutes: ' + str(min(10, int(m[0].split(':', 1)[1].strip()))),
                              part, flags=re.M)
            else:
                part = part.replace('\n', '\n    timeout-minutes: 5\n', 1)
        out.append(part)
    bounded = ''.join(out)
    return re.sub(r'^( +)retention-days:.*$', r'\1retention-days: 7', bounded, flags=re.M)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(root=ROOT):
    receipt = json.loads((root / MANIFEST).read_text())
    for path in (SOURCE, LOCK):
        if digest(root / path) != receipt['sha256'][path]:
            raise ValueError('Regenerate Copilot workflow and compile receipt: ' + path)
    if receipt['compiler_commit'] != COMMIT:
        raise ValueError('Unexpected compiler commit')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path)
    args = parser.parse_args()
    if not args.compiler:
        check()
        print('Copilot workflow source/lock integrity PASS')
        return
    binary = args.compiler.resolve()
    if digest(binary) != BINARY_SHA256:
        raise ValueError('Pinned Linux amd64 compiler checksum mismatch')
    subprocess.run([str(binary), 'compile', 'copilot-operator', '--action-mode', 'release',
                    '--action-tag', COMMIT, '--no-check-update', '--no-logo'], cwd=ROOT, check=True)
    path = ROOT / LOCK
    path.write_text(bound_jobs(path.read_text()))
    receipt = {'schema': 'vm-lab/copilot-compile/v1', 'compiler_version': VERSION,
               'compiler_commit': COMMIT, 'linux_amd64_sha256': BINARY_SHA256,
               'postprocess': 'Cap generated job timeouts at 10m; set missing job timeouts to 5m; artifact retention 7d.',
               'sha256': {p: digest(ROOT / p) for p in (SOURCE, LOCK)}}
    (ROOT / MANIFEST).write_text(json.dumps(receipt, indent=2) + '\n')
    check()


if __name__ == '__main__':
    main()
