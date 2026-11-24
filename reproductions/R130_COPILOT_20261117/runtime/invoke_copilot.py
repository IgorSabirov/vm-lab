"""Use the existing native Copilot credential and pinned CLI for one execution task."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
source = HERE.parent
work = Path(os.environ['RUNNER_TEMP'])/'r130-copilot-task'
work.mkdir()
for name in ['source', 'reference']:
    shutil.copytree(source/name, work/name)
for name in ['SOURCE_MANIFEST.json', 'HANDOFF.md']:
    shutil.copy2(source/name, work/name)
shutil.copy2(HERE/'run_reproduction.py', work/'run_reproduction.py')
out = work/'results'
out.mkdir()
token = os.environ.get('COPILOT_GITHUB_TOKEN', '')
assert token, 'AUTH_MISSING: existing COPILOT_GITHUB_TOKEN is not available'
env = {k:v for k,v in os.environ.items() if not k.startswith(('COPILOT_', 'GH_AW_')) and k not in ('GH_TOKEN', 'GITHUB_TOKEN')}
env.update(COPILOT_GITHUB_TOKEN=token, COPILOT_HOME=str(Path(os.environ['RUNNER_TEMP'])/'r130-copilot-profile'))
prompt = '''The repository owner IgorSabirov explicitly requests execution of the frozen R130 reproduction on GitHub and publication of the new raw results (issue #85). This is an execution task, not a review.
Your working directory contains run_reproduction.py, immutable source/, reference/, SOURCE_MANIFEST.json and HANDOFF.md. Dependencies are already installed. A trusted publisher runs after your session and commits everything in results/ to the same repository.
Use the bash tool to execute exactly: python run_reproduction.py
The command performs all three blocks, both calibrations, 6032 operator inputs, 10920 short trajectories and 30 long trajectories, independent verification, plots and reference comparison. Do not edit code or change the command. Do not launch a duplicate. Let this command finish; if the tool returns a running session, use read_bash until it exits. Do not stop it because the command is taking time. There is no project runtime cutoff.
Report the real exit status and final status line. A mismatch or error must be reported honestly. You do not need to commit or access the network yourself; the next workflow job publishes all results. Do not ask for confirmation; execution and publication are already authorized. Do not call subagents.'''
argv = [shutil.which('copilot'), '-C', str(work), '--model', 'auto', '--max-ai-credits', '30',
        '--disable-builtin-mcps', '--available-tools', 'bash', 'read_bash', 'list_bash',
        '--allow-tool', 'shell(python run_reproduction.py)', '--deny-tool', 'write', '--deny-tool', 'url',
        '--no-custom-instructions', '--no-ask-user', '--no-auto-update', '--disable-client-telemetry',
        '--log-level', 'warning', '-s']
started = time.perf_counter()
p = subprocess.run(argv, cwd=work, env=env, input=prompt, capture_output=True, text=True)
def redact(s):
    return re.sub(r'(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+', '[REDACTED]', s.replace(token, '[REDACTED]'))
(out/'COPILOT_RESPONSE.txt').write_text(redact(p.stdout))
(out/'COPILOT_STDERR.txt').write_text(redact(p.stderr))
(out/'COPILOT_PROMPT.txt').write_text(prompt)
receipt = {'cli_version': '1.0.103', 'model': 'native auto', 'returncode': p.returncode,
           'session_seconds': time.perf_counter()-started, 'max_ai_credits': 30,
           'tool_permissions': ['shell(python run_reproduction.py)'],
           'source_commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
           'actual_execution_receipt_exists': (out/'EXECUTION_RECEIPT.json').exists()}
(out/'COPILOT_RECEIPT.json').write_text(json.dumps(receipt, indent=2)+'\n')
files = sorted(q for q in out.rglob('*') if q.is_file() and q.name != 'MANIFEST.sha256')
(out/'MANIFEST.sha256').write_text(''.join(hashlib.sha256(q.read_bytes()).hexdigest()+'  '+q.relative_to(out).as_posix()+'\n' for q in files))
print(json.dumps(receipt), flush=True)
print(redact(p.stdout), flush=True)
print(redact(p.stderr), file=sys.stderr, flush=True)
if not receipt['actual_execution_receipt_exists']:
    raise SystemExit('COPILOT_DID_NOT_EXECUTE: see saved response and stderr')
status = json.loads((out/'EXECUTION_RECEIPT.json').read_text())['status']
raise SystemExit(0 if p.returncode == 0 and status.startswith('COMPLETE_') else 1)
