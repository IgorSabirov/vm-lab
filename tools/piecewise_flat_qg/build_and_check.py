"""SPDX-License-Identifier: GPL-3.0-or-later. Offline build of pinned upstream C++."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import time

p = argparse.ArgumentParser()
p.add_argument('--build', type=Path, required=True)
p.add_argument('--report', type=Path, required=True)
a = p.parse_args()
start = time.perf_counter()
here = Path(__file__).resolve().parent
repo = here.parents[1]
vendor = repo/'third_party/piecewise_flat_qg'
manifest = json.loads((vendor/'UPSTREAM.json').read_text())
archive = vendor/manifest['snapshot']
if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['snapshot_sha256']:
    raise RuntimeError('Upstream archive hash mismatch')
build = a.build.resolve(); build.mkdir(parents=True, exist_ok=True)
source = build/'source'; source.mkdir(exist_ok=True)
with tarfile.open(archive, 'r:xz') as tar:
    found = set()
    for member in tar:
        path = PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not member.isfile():
            raise RuntimeError('Unsafe source archive member')
        data = tar.extractfile(member).read()
        if hashlib.sha256(data).hexdigest() != manifest['files'].get(member.name):
            raise RuntimeError('Upstream source hash mismatch')
        target = source/member.name
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if p.is_relative_to(source)):
            raise RuntimeError('Symlink in output source tree')
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        found.add(member.name)
if found != set(manifest['files']):
    raise RuntimeError('Incomplete upstream source archive')
cpp = source/'cpp'; numeric = cpp/'symmetric_matrix_signature'; mesh = cpp/'triangulator'
compiler = shutil.which('g++') or shutil.which('c++')
if not compiler:
    raise RuntimeError('C++11 compiler required')
env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
stages = []
a.report.parent.mkdir(parents=True, exist_ok=True)

def run(name, command, cap=60):
    remaining = 300-(time.perf_counter()-start)
    if remaining <= 0:
        raise TimeoutError('300-second engineering cap exhausted')
    t = time.perf_counter()
    process = subprocess.run(command, cwd=build, env=env, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=min(cap, remaining))
    record = dict(name=name, command=[str(v) for v in command], returncode=process.returncode,
                  seconds=time.perf_counter()-t, output=process.stdout)
    stages.append(record)
    print(json.dumps({k:record[k] for k in ['name','returncode','seconds']}), flush=True)
    a.report.write_text(json.dumps(dict(complete=False, stages=stages), indent=2)+'\n')
    if process.returncode:
        raise RuntimeError(name+' failed; see '+str(a.report))
    return process.stdout

flags = ['-std=c++11', '-O2', '-fno-fast-math', '-Wall', '-Wextra', '-Wpedantic']
includes = ['-I'+str(numeric/'include'), '-I'+str(mesh/'library/include'),
            '-I'+str(mesh/'third_party_software/rapidxml')]
object_file = build/'signature.o'
run('compile_numerical_kernel', [compiler, *flags, '-Werror', '-fPIC', *includes, '-c',
                               str(numeric/'src/symmetric_matrix_signature.cpp'), '-o', str(object_file)])
library = build/'libvm_signature.so'
run('build_python_bridge', [compiler, *flags, '-Werror', '-fPIC', '-shared', *includes,
                            str(here/'signature_bridge.cpp'), str(object_file), '-o', str(library)])
tests = ['basic_test','validation_test','numerical_test','randomized_test','structural_test',
         'allocation_failure_test','pivoting_test','inertia_properties_test']
for name in tests:
    executable = build/name
    run('build_'+name, [compiler, *flags, *includes, str(numeric/'test'/(name+'.cpp')),
                       str(object_file), '-o', str(executable)])
    run(name, [str(executable)], cap=30)
mesh_objects = []
for path in sorted((mesh/'library/src').glob('*.cpp')):
    obj = build/('mesh_'+path.stem+'.o')
    run('compile_mesh_'+path.stem, [compiler, *flags, *includes, '-c', str(path), '-o', str(obj)])
    mesh_objects.append(str(obj))
for name in ['simplex-generator','ball-generator','sphere-generator']:
    run('build_'+name, [compiler, *flags, *includes, str(cpp/(name+'.cpp')), *mesh_objects,
                       str(object_file), '-o', str(build/name)])
run('build_mesh_probe', [compiler, *flags, *includes, str(here/'mesh_probe.cpp'), *mesh_objects,
                         '-o', str(build/'mesh_probe')])
mesh_result = json.loads(run('mesh_probe', [str(build/'mesh_probe')], cap=30))
run('check_python_adapter', [sys.executable, str(here/'check_adapter.py'), '--library', str(library),
                            '--output', str(build/'ADAPTER_CHECKS.json')], cap=30)
report = dict(complete=True, passed=True, upstream_source_files=len(found),
              upstream_archive_sha256=manifest['snapshot_sha256'],
              environment=dict(python=sys.version, platform=platform.platform(),
                               compiler=subprocess.check_output([compiler,'--version'], text=True).splitlines()[0],
                               build_flags=flags, numpy_threads=1),
              whole_cap_seconds=300, total_seconds=time.perf_counter()-start,
              stages=stages, mesh_probe=mesh_result,
              adapter=json.loads((build/'ADAPTER_CHECKS.json').read_text()),
              production_generators_built=True, production_generators_executed=False,
              vm_jobs_submitted=False, integrated_experiment_unchanged=True)
a.report.write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['complete','passed','total_seconds']}), flush=True)
