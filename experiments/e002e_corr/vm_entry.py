"""Queue entry adapter; scientific source resides byte-for-byte in corr_payload.

The bridge launches only root run.py and excludes root results/. A dedicated
launch snapshot uses this adapter as run.py; its payload includes the reviewed
original run.py and published input reports. Main's old kernel is not modified.
"""
import json
import os
from pathlib import Path
import re
import resource
import sys


def bind(config,source):
    if not re.fullmatch('[0-9a-f]{40}',source or ''):
        raise ValueError('Missing verified launcher source')
    if config.get('source_commit') not in ('FROM_VERIFIED_VM_LAUNCHER',source):
        raise ValueError('Configured source differs from verified launcher')
    return dict(config,source_commit=source)


def main(audit=False):
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ[key]='1'
    root=Path(__file__).resolve().parent
    if Path(os.environ.get('VM_SOURCE_DIR','/nonexistent')).resolve()!=root:
        raise ValueError('Entry directory differs from launcher source')
    outer=json.loads((root/'config.json').read_text())
    ceiling=outer['address_space_limit_bytes']
    if type(ceiling) is not int or ceiling<=0:
        raise ValueError('Invalid address-space ceiling')
    _,hard=resource.getrlimit(resource.RLIMIT_AS)
    if hard!=resource.RLIM_INFINITY and ceiling>hard:
        raise ValueError('Cannot raise existing memory ceiling')
    resource.setrlimit(resource.RLIMIT_AS,(ceiling,ceiling))
    payload=root/'corr_payload'
    sys.path.insert(0,str(payload))
    from e002e_exp.runtime import ROOT,kernel_hash
    from e002e_corr_exp.plan import implementation_hash,protocol_hash
    if ROOT.resolve()!=payload.resolve():
        raise ValueError('Scientific modules loaded outside pinned payload')
    config=bind(outer['worker_config'],os.environ.get('VM_SOURCE_COMMIT'))
    if (implementation_hash()!=config['implementation_sha256'] or protocol_hash()!=config['protocol_sha256']
            or kernel_hash()!=outer['kernel_sha256']):
        raise ValueError('Payload implementation/protocol/kernel mismatch')
    if audit:
        print(json.dumps(dict(status='PAYLOAD_IDENTITY_VERIFIED',implementation_sha256=implementation_hash(),
                              kernel_sha256=kernel_hash(),source_commit=config['source_commit'],numerical_work=0)))
        return
    from e002e_corr_exp.task import run
    run(config,Path.cwd())


if __name__=='__main__':
    main(audit=sys.argv[1:]==['--audit'])
