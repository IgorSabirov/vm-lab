#!/usr/bin/env python3
import os,subprocess,sys,resource
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def call(args,pythonpath=None):
    env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    if pythonpath:env['PYTHONPATH']=str(ROOT/pythonpath)
    # Enforce the finite bound required by existing environment checks when
    # cgroup limits are not exposed. This is a child-only technical-test limit.
    def cap():
        _,hard=resource.getrlimit(resource.RLIMIT_AS)
        limit=8*1024**3 if hard==resource.RLIM_INFINITY else min(hard,8*1024**3)
        resource.setrlimit(resource.RLIMIT_AS,(limit,limit))
    subprocess.run([sys.executable,*args],cwd=ROOT,env=env,check=True,preexec_fn=cap if 'test_e002*.py' in args else None)
def infra_modules(copilot):
    files = sorted((ROOT/'infra').glob('test*.py'))
    return [file.name for file in files
            if (file.name.startswith('test_copilot') or file.name == 'test_research_context.py') == copilot]


def main(s):
    if s == 'evidence':
        call(['tools/registry_links.py'])
        call(['tools/external_sources.py', 'validate'])
        return
    if s == 'copilot':
        commands = [['tools/compile_copilot_workflow.py'],
                    ['-m','unittest','discover','-s','tests','-p','test_copilot*.py']]
        commands.extend(['-m','unittest','discover','-s','infra','-p',name]
                        for name in infra_modules(True))
        failed = []
        for command in commands:
            try:
                call(command)
            except subprocess.CalledProcessError:
                failed.append(command)
        if failed:
            raise SystemExit(f'Copilot diagnostic failures: {failed}')
        return
    if s=='integrity':
        subprocess.run(['node','--test','tests/test_ci_failure_report.cjs'],cwd=ROOT,check=True)
        call(['-m','unittest','discover','-s','tests','-p','test_research_operations.py'])
        call(['tools/registry_links.py'])
        call(['tools/workflow_policy.py'])
        call(['tools/external_sources.py','validate'])
        call(['-m','unittest','discover','-s','tests','-p','test_project*.py'])
        call(['tools/r135_pipeline.py','--check'])
        call(['-m','unittest','discover','-s','tests','-p','test_r135_pipeline.py'])
        call(['-m','unittest','discover','-s','tests','-p','test_dependency_evidence.py'])
        call(['-m','unittest','discover','-s','tests','-p','test_external*.py'])
        call(['-m','unittest','discover','-s','tests','-p','test_registry_links.py'])
        call(['-m','unittest','discover','-s','tests','-p','test_ci_policy.py'])
    elif s=='infra':
        for name in infra_modules(False):
            call(['-m','unittest','discover','-s','infra','-p',name])
    elif s=='e002':call(['-m','unittest','discover','-s','tests','-p','test_e002*.py'])
    elif s=='now':call(['-m','unittest','discover','-s','experiments/now_integrated_v1/tests'],Path('experiments/now_integrated_v1'))
    elif s in {'x27_043','x27_051'}:
        p=Path('experiments/X27_PACKAGES_20261110')/('v'+s[-3:]);call(['-m','unittest','discover','-s',str(p/'tests')],p/'src')
    else:raise ValueError('Unknown active suite')
if __name__=='__main__':main(sys.argv[1])
