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
work = Path(os.environ['RUNNER_TEMP'])/'bbn-copilot-task'
work.mkdir()
for name in ["run_bbn.py", "science.py", "reproduction_tool.py"]:
    shutil.copy2(HERE/name, work/name)
bridge = Path(os.environ["GITHUB_WORKSPACE"])/"analysis/PRIMAT_LINX_BBN_BRIDGE_20261117"
for name in ["NETWORK_MAP.json", "BBN_HISTORY.schema.json", "validate_contract.py"]:
    shutil.copy2(bridge/name, work/name)
out = work/'results'
out.mkdir()
token = os.environ.get('COPILOT_GITHUB_TOKEN', '')
assert token, 'AUTH_MISSING: existing COPILOT_GITHUB_TOKEN is not available'
env = {k:v for k,v in os.environ.items() if not k.startswith(('COPILOT_', 'GH_AW_')) and k not in ('GH_TOKEN', 'GITHUB_TOKEN')}
env.update(COPILOT_GITHUB_TOKEN=token, COPILOT_HOME=str(Path(os.environ['RUNNER_TEMP'])/'bbn-copilot-profile'))
prompt = """Execute the owner-authorized frozen BBN + CLASS forward calculations for IgorSabirov/vm-lab issue #140 on GitHub Actions. Call bbn.execute exactly once with no arguments. If RUNNING, call bbn.status once and finish your session. The supervisor will wait for the worker and publish all outputs and actual receipts. Do not edit or substitute data."""
config = {'mcpServers': {'bbn': {'command': sys.executable,
          'env': {k:os.environ[k] for k in ('GITHUB_WORKSPACE','GITHUB_SHA','GITHUB_RUN_ID',
                  'PYTHONPATH','JAX_PLATFORMS','JAX_ENABLE_X64','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')},
          'args': [str(work/'reproduction_tool.py')], 'tools': ['execute', 'status']}}}
argv = [shutil.which('copilot'), '-C', str(work), '--model', 'auto', '--max-ai-credits', '30',
        '--disable-builtin-mcps', '--additional-mcp-config', json.dumps(config),
        '--excluded-tools', 'bash', 'powershell', 'edit', 'create', 'apply_patch', 'view', 'glob', 'grep',
        'web_fetch', 'task', 'ask_user', 'skill', 'read_bash', 'write_bash', 'list_bash', 'stop_bash',
        '--allow-tool', 'bbn(execute)', '--allow-tool', 'bbn(status)',
        '--deny-tool', 'shell', '--deny-tool', 'write', '--deny-tool', 'url',
        '--no-custom-instructions', '--no-ask-user', '--no-auto-update', '--disable-client-telemetry',
        '--log-level', 'warning', '-s']
started = time.perf_counter()
# Copilot may shut down its entire MCP process tree when a session ends. The
# only launch authority is the no-argument request sent by its execute tool.
# The Actions process owns the worker so its lifetime matches the job.
worker_env = {k:v for k,v in os.environ.items()
              if "TOKEN" not in k and "SECRET" not in k and not k.startswith(("COPILOT_", "GH_AW_"))}
request = out/"COPILOT_EXECUTE_REQUEST.json"
with (work/"cli.out").open("w") as cli_out, (work/"cli.err").open("w") as cli_err:
    with subprocess.Popen(argv, cwd=work, env=env, stdin=subprocess.PIPE,
                          stdout=cli_out, stderr=cli_err, text=True) as cli:
        cli.stdin.write(prompt)
        cli.stdin.close()
        while not request.exists() and cli.poll() is None:
            time.sleep(.2)
        if request.exists():
            with (out/"RUNNER.stdout.log").open("w") as sci_out, (out/"RUNNER.stderr.log").open("w") as sci_err:
                with subprocess.Popen([sys.executable, "-u", str(work/"run_bbn.py")],
                                      cwd=work, env=worker_env, stdout=sci_out, stderr=sci_err) as worker:
                    (out/"COPILOT_TOOL_START.json").write_text(json.dumps({
                        "tool":"bbn.execute", "pid":worker.pid, "command":["python","run_bbn.py"],
                        "credentials_removed":True,"arbitrary_arguments_supported":False}))
                    previous = None
                    while worker.poll() is None:
                        checkpoint = out/"PROGRESS.json"
                        if checkpoint.exists():
                            data = json.loads(checkpoint.read_text())
                            completed = list(data["timings"])
                            if completed != previous:
                                print("Completed stages:", completed, "errors:", list(data["errors"]), flush=True)
                                previous = completed
                        time.sleep(2)
                    if not (out/"EXECUTION_RECEIPT.json").exists():
                        (out/"EXECUTION_RECEIPT.json").write_text(json.dumps({
                            "status":"INCOMPLETE_WORKER_EXIT", "returncode":worker.returncode}))
        cli.wait()
p = subprocess.CompletedProcess(argv, cli.returncode,
        (work/"cli.out").read_text(), (work/"cli.err").read_text())
def redact(s):
    return re.sub(r'(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+', '[REDACTED]', s.replace(token, '[REDACTED]'))
(out/'COPILOT_RESPONSE.txt').write_text(redact(p.stdout))
(out/'COPILOT_STDERR.txt').write_text(redact(p.stderr))
(out/'COPILOT_PROMPT.txt').write_text(prompt)
receipt = {'cli_version': '1.0.103', 'model': 'native auto', 'returncode': p.returncode,
           'session_seconds': time.perf_counter()-started, 'max_ai_credits': 30,
           'tool_permissions': ['bbn(execute)', 'bbn(status)'],
           'shell_access': False, 'arbitrary_code_arguments': False,
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
