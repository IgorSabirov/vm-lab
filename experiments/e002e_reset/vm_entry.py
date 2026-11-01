"""Dedicated immutable launch snapshot; main's original run.py stays unchanged."""
import json,os,re,resource,sys
from pathlib import Path


def bind(config,source):
    if not re.fullmatch('[0-9a-f]{40}',source or ''):raise ValueError('Invalid launch source')
    if config.get('source_commit') not in ('FROM_VERIFIED_VM_LAUNCHER',source):raise ValueError('Launch source mismatch')
    return dict(config,source_commit=source)


def main(audit=False):
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='1'
    root=Path(__file__).resolve().parent
    if Path(os.environ.get('VM_SOURCE_DIR','/nonexistent')).resolve()!=root:raise ValueError('Launch directory mismatch')
    outer=json.loads((root/'config.json').read_text());ceiling=outer['address_space_limit_bytes']
    if type(ceiling) is not int or ceiling<=0:raise ValueError('Invalid memory ceiling')
    _,hard=resource.getrlimit(resource.RLIMIT_AS)
    if hard!=resource.RLIM_INFINITY and ceiling>hard:raise ValueError('Cannot raise memory ceiling')
    resource.setrlimit(resource.RLIMIT_AS,(ceiling,ceiling))
    payload=root/'reset_payload';sys.path.insert(0,str(payload))
    from e002e_exp.runtime import ROOT,kernel_hash
    from e002e_reset_exp.plan import implementation_hash,protocol_hash
    config=bind(outer['worker_config'],os.environ.get('VM_SOURCE_COMMIT'))
    if ROOT.resolve()!=payload.resolve():raise ValueError('Modules loaded outside payload')
    if (kernel_hash()!=outer['kernel_sha256'] or implementation_hash()!=config['implementation_sha256']
            or protocol_hash()!=config['protocol_sha256']):raise ValueError('Payload identity mismatch')
    if audit:
        print(json.dumps(dict(status='PAYLOAD_IDENTITY_VERIFIED',numerical_work=0,source_commit=config['source_commit'])))
        return
    from e002e_reset_exp.task import run
    run(config,Path.cwd())


if __name__=='__main__':main(audit=sys.argv[1:]==['--audit'])
