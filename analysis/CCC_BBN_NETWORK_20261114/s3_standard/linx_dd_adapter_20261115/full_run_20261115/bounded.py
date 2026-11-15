"""Bound one numerical process; ensure timeout/cancellation cannot orphan it."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

def rss(pid):
    try:return next(int(s.split()[1])*1024 for s in Path(f'/proc/{pid}/status').read_text().splitlines() if s.startswith('VmRSS:'))
    except (FileNotFoundError,StopIteration):return 0

def run(command,log_path,limits,env=None):
    if rss(os.getpid())<=0:raise RuntimeError('RSS monitor unavailable')
    start=time.monotonic();peak=0;stop=None;p=None
    def interrupted(signum,frame):raise InterruptedError('Supervisor signal '+str(signum))
    previous={s:signal.signal(s,interrupted) for s in (signal.SIGTERM,signal.SIGINT)}
    try:
        with Path(log_path).open('xb') as log:
            p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
            try:
                while p.poll() is None:
                    peak=max(peak,rss(p.pid))
                    size=sum(f.stat().st_size for f in Path(log_path).parent.rglob('*') if f.is_file())
                    if time.monotonic()-start>limits['wall_seconds']:stop='WALL_LIMIT'
                    if peak>limits['memory_bytes']:stop='RSS_LIMIT'
                    if size>limits['output_bytes']:stop='OUTPUT_LIMIT'
                    if stop:break
                    time.sleep(0.1)
            except BaseException:
                stop='SUPERVISOR_INTERRUPTED';raise
            finally:
                if p.poll() is None:
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                p.wait()
    finally:
        for s,h in previous.items():signal.signal(s,h)
        if p is not None:
            result={'pid':p.pid,'exit_code':p.returncode,'process_exited':p.returncode is not None,'stop':stop,
                    'wall_seconds':time.monotonic()-start,'peak_sampled_rss_bytes':peak,'limits':limits}
            Path(str(log_path)+'.guard.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
