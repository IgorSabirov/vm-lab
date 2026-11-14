"""Linux supervisor for the engineering suite; never dispatches a science run."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent

def rss_tree(pid):
    try:
        status = Path(f'/proc/{pid}/status').read_text()
        rss = next(int(s.split()[1])*1024 for s in status.splitlines() if s.startswith('VmRSS:'))
    except (FileNotFoundError, ProcessLookupError, StopIteration):
        return 0
    # Some containers expose status but not task/PID/children. Keep parent RSS.
    children = []
    for path in Path('/proc').glob('[0-9]*/status'):
        try:
            s = path.read_text()
            parent = next(int(x.split()[1]) for x in s.splitlines() if x.startswith('PPid:'))
            if parent == pid:
                children.append(int(path.parent.name))
        except (FileNotFoundError, ProcessLookupError, StopIteration):
            continue
    return rss + sum(rss_tree(c) for c in children)

def main():
    if rss_tree(os.getpid()) <= 0:
        raise SystemExit('RSS monitor is unavailable; do not start')
    limits = json.loads((HERE/'ENGINEERING_PLAN.json').read_text())['limits']
    out = HERE/'results'
    if out.exists() and any(out.iterdir()):
        raise SystemExit('Preserve the previous evidence directory before a new engineering version')
    out.mkdir(exist_ok=True)
    start = time.monotonic()
    reason = None
    peak = 0
    with (out/'console.log').open('wb') as log:
        p = subprocess.Popen([sys.executable, str(HERE/'run_engineering.py')],
                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        while p.poll() is None:
            rss = rss_tree(p.pid)
            peak = max(peak, rss)
            size = sum(x.stat().st_size for x in out.rglob('*') if x.is_file())
            if time.monotonic()-start > limits['wall_seconds']: reason = 'WALL_LIMIT'
            if rss > limits['memory_bytes']: reason = 'RSS_LIMIT'
            if size > limits['output_bytes']: reason = 'OUTPUT_LIMIT'
            if reason:
                os.killpg(p.pid, signal.SIGKILL)
                break
            time.sleep(0.1)
        code = p.wait()
    record = {'exit_code':code, 'stop_reason':reason,
              'wall_seconds':time.monotonic()-start, 'sampled_peak_tree_rss_bytes':peak,
              'monitor_period_seconds':0.1, 'limits':limits,
              'scientific_acceptance':False, 'bbn_integrations':0}
    (out/'SUPERVISOR.json').write_text(json.dumps(record,indent=2)+'\n')
    print((out/'console.log').read_text())
    print(json.dumps(record,indent=2))
    return code if not reason else 124

if __name__ == '__main__':
    sys.exit(main())
