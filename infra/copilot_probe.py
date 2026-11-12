#!/usr/bin/env python3
"""One bounded text-only native CLI control; no repository access or publication."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time


def main():
    cli = shutil.which('copilot')
    if not cli:
        raise SystemExit('CLI_MISSING')
    token = os.environ.get('COPILOT_GITHUB_TOKEN', '')
    if not token:
        raise SystemExit('AUTH_MISSING')
    output = Path('copilot-probe.json').resolve()
    started = time.monotonic()
    # Keep runner networking/CA settings. Do not inherit provider overrides or
    # another GitHub identity. The model receives no repository content/tools.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('COPILOT_', 'GH_AW_')) and k not in ('GH_TOKEN', 'GITHUB_TOKEN')}
    with tempfile.TemporaryDirectory(prefix='copilot-native-control-') as tmp:
        cwd = Path(tmp) / 'empty'
        cwd.mkdir()
        env.update(COPILOT_GITHUB_TOKEN=token, COPILOT_HOME=str(Path(tmp) / 'profile'))
        argv = [cli, '-C', str(cwd), '--model', 'auto', '--max-ai-credits', '30',
                '--disable-builtin-mcps', '--available-tools',
                '--deny-tool', 'shell', '--deny-tool', 'write', '--deny-tool', 'url',
                '--disallow-temp-dir', '--no-custom-instructions', '--no-ask-user',
                '--no-auto-update', '--disable-client-telemetry', '--log-level', 'warning',
                '-s', '-p', 'Reply with exactly VM_LAB_COPILOT_OK. Do not use any tools.']
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
        timed_out = False
        try:
            stdout, stderr = p.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(p.pid, signal.SIGTERM)
            try:
                stdout, stderr = p.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                stdout, stderr = p.communicate()
    def redact(text):
        text = text.replace(token, '[REDACTED]')
        return re.sub(r'(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+', '[REDACTED]', text)
    stdout, stderr = redact(stdout).strip(), redact(stderr).strip()
    ok = p.returncode == 0 and not timed_out and stdout == 'VM_LAB_COPILOT_OK'
    d = {'status': 'NATIVE_INFERENCE_PASS' if ok else 'NATIVE_INFERENCE_FAILED',
         'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
         'cli_version': '1.0.103', 'model_selector': 'native auto',
         'tools': [], 'repository_content_sent': False, 'max_ai_credits': 30,
         'timeout_seconds': 120, 'timed_out': timed_out, 'returncode': p.returncode,
         'elapsed_seconds': round(time.monotonic() - started, 3),
         'stdout': stdout[:4000], 'stderr': stderr[:4000]}
    output.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(d, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
