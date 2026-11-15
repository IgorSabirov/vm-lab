"""Bound a single-process numerical worker; JAX threads share its RSS."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

def rss(pid):
    try:
        return next(int(s.split()[1])*1024 for s in Path(f'/proc/{pid}/status').read_text().splitlines()
                    if s.startswith('VmRSS:'))
    except (FileNotFoundError,StopIteration): return 0

def run(command,log_path,limits,env=None):
    if rss(os.getpid())<=0: raise RuntimeError('RSS monitor unavailable')
    start=time.monotonic();peak=0;stop=None
    with Path(log_path).open('xb') as log:
        p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        while p.poll() is None:
            peak=max(peak,rss(p.pid))
            size=sum(f.stat().st_size for f in Path(log_path).parent.rglob('*') if f.is_file())
            if time.monotonic()-start>limits['wall_seconds']:stop='WALL_LIMIT'
            if peak>limits['memory_bytes']:stop='RSS_LIMIT'
            if size>limits['output_bytes']:stop='OUTPUT_LIMIT'
            if stop:os.killpg(p.pid,signal.SIGKILL);break
            time.sleep(0.1)
        code=p.wait()
    result={'exit_code':code,'stop':stop,'wall_seconds':time.monotonic()-start,
            'peak_sampled_rss_bytes':peak,'limits':limits}
    Path(str(log_path)+'.guard.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
