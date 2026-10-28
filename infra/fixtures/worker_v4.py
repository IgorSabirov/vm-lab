"""Background runner. Deployed only inside the dedicated systemd sandbox."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
os.umask(7)
work = Path(sys.argv[1])
jobs = work / 'jobs'
jobs.mkdir(exist_ok=True)
active = None
stopping = False

def atomic(path, value):
    temp = path.with_name(path.name + '.worker-tmp')
    with open(temp, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False)
    os.replace(temp, path)

def terminate(*_):
    global stopping
    stopping = True
signal.signal(signal.SIGTERM, terminate)
signal.signal(signal.SIGINT, terminate)

def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 3
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()
last_heartbeat = 0
for directory in jobs.iterdir():
    if not directory.is_dir() or directory.is_symlink():
        continue
    try:
        status = json.loads((directory / 'status.json').read_text())
        if status.get('state') == 'running':
            status.update(state='interrupted', reason='worker restarted', finished=time.time())
            atomic(directory / 'status.json', status)
    except (OSError, ValueError):
        pass
while not stopping:
    now = time.time()
    if now - last_heartbeat > 2:
        atomic(work / 'worker-health.json', {'heartbeat': now, 'pid': os.getpid(), 'uid': os.getuid(), 'active_job': active[0].name if active else None, 'python': sys.version.split()[0]})
        last_heartbeat = now
    if active:
        directory, process, status, log = active
        reason = None
        if (directory / 'cancel').exists():
            reason = 'cancelled by user'
        elif shutil.disk_usage(work).free < 512 * 1024 ** 2:
            reason = 'disk free space below 512 MiB'
        if reason:
            stop_group(process)
        code = process.poll()
        if code is not None:
            stop_group(process)
            log.close()
            status.update(state='cancelled' if reason else 'completed' if code == 0 else 'failed', exit_code=code, finished=time.time(), reason=reason)
            atomic(directory / 'status.json', status)
            active = None
    else:
        for directory in sorted(jobs.iterdir()):
            if not re.fullmatch('[A-Za-z0-9_-]{12,64}', directory.name) or directory.is_symlink() or (not directory.is_dir()):
                continue
            try:
                status = json.loads((directory / 'status.json').read_text())
                if status.get('state') != 'queued':
                    continue
                if (directory / 'cancel').exists():
                    status.update(state='cancelled', finished=time.time())
                    atomic(directory / 'status.json', status)
                    continue
                request = json.loads((directory / 'request.json').read_text())
                args = request['args']
                if not isinstance(args, list) or len(args) > 100 or any((not isinstance(x, str) or len(x) > 4096 or '\x00' in x for x in args)):
                    raise ValueError('Invalid argv')
                if (directory / 'main.py').is_symlink():
                    raise ValueError('Symlinked script')
                output = work / 'results' / directory.name
                output.mkdir(parents=True, exist_ok=True)
                if output.is_symlink():
                    raise ValueError('Symlinked output')
                env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(output), 'PYTHONUNBUFFERED': '1', 'PYTHONNOUSERSITE': '1', 'OPENBLAS_NUM_THREADS': os.environ.get('VM_LAB_THREADS', '4'), 'OMP_NUM_THREADS': os.environ.get('VM_LAB_THREADS', '4'), 'MPLBACKEND': 'Agg', 'MPLCONFIGDIR': str(output / '.matplotlib'), 'VM_WORK': str(work), 'VM_JOB_ID': directory.name}
                log = open(directory / 'output.log', 'ab', buffering=0)
                process = subprocess.Popen([sys.executable, '-u', str(directory / 'main.py'), *args], cwd=output, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
                status.update(state='running', started=time.time(), pid=process.pid, output_directory=str(output))
                atomic(directory / 'status.json', status)
                active = (directory, process, status, log)
                break
            except (OSError, ValueError, KeyError) as exc:
                try:
                    atomic(directory / 'status.json', {'state': 'failed', 'reason': str(exc), 'finished': time.time()})
                except OSError:
                    pass
    time.sleep(0.25)
if active:
    directory, process, status, log = active
    stop_group(process)
    log.close()
    status.update(state='interrupted', reason='worker stopped', finished=time.time())
    atomic(directory / 'status.json', status)

