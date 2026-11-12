#!/usr/bin/env python3
"""GitHub transport for the existing offline VM Compute worker (stdlib only)."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import time

ID = re.compile(r'[A-Za-z0-9_-]{12,64}')
SHA = re.compile(r'[0-9a-f]{40}')
TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}
MAX_FILE = 8 * 1024**2
MAX_TOTAL = 32 * 1024**2
MAX_FILES = 512


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def atomic_private(path, value):
    temp = path.with_name('.' + path.name + '-' + secrets.token_hex(8))
    with temp.open('xb') as handle:
        handle.write(json_bytes(value))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def safe_parts(path):
    p = PurePosixPath(path)
    if not path or p.is_absolute() or str(p) != path or any(
        x in ('.', '..') or x.startswith('.') or len(x) > 200 or
        any(ord(c) < 32 for c in x) for x in p.parts
    ):
        raise ValueError('Unsafe relative path')
    return p.parts


class Workspace:
    """All shared filesystem traversal uses directory FDs and refuses symlinks."""
    def __init__(self, path):
        self.path = Path(path)
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    @contextlib.contextmanager
    def directory(self, parts, create=False):
        fd = os.dup(self.fd)
        try:
            for part in parts:
                if create:
                    try:
                        os.mkdir(part, 0o750, dir_fd=fd)
                    except FileExistsError:
                        pass
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
            yield fd
        finally:
            os.close(fd)

    def read(self, path, limit=MAX_FILE):
        parts = safe_parts(path)
        with self.directory(parts[:-1]) as parent:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                raise ValueError('Expected bounded regular, non-hardlinked file: ' + path)
            data = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
        if len(data) > limit or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('File changed or exceeds limit: ' + path)
        return data

    def write(self, path, data, replace=True):
        parts = safe_parts(path)
        with self.directory(parts[:-1], create=True) as parent:
            if not replace:
                try:
                    if self.read(path) != data:
                        raise ValueError('Existing input differs: ' + path)
                    return
                except FileNotFoundError:
                    pass
            temp = '.github-' + secrets.token_hex(12)
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=parent)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    os.fchmod(handle.fileno(), 0o640)
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(temp, dir_fd=parent)
                except FileNotFoundError:
                    pass

    def names(self, path):
        with self.directory(safe_parts(path)) as fd:
            return sorted(os.listdir(fd))

    def files(self, path):
        def walk(fd, prefix, depth):
            if depth > 16:
                raise ValueError('Too many nested result directories')
            for name in sorted(os.listdir(fd)):
                if name.startswith('.'):
                    continue
                safe_parts(name)
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                relative = prefix + name
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        yield from walk(child, relative + '/', depth + 1)
                    finally:
                        os.close(child)
                else:
                    yield relative
        with self.directory(safe_parts(path)) as root:
            yield from walk(root, '', 0)


class Bridge:
    def __init__(self, config):
        self.config = config
        self.state = Path(config['state'])
        self.work = Workspace(config['work'])
        self.repo = self.state / 'repo.git'
        self.records = self.state / 'runs'
        self.records.mkdir(exist_ok=True)
        self.status_dir = config.get('status_dir', 'data/vm_lab_status')
        self.source_dir = config.get('source_dir', 'data/vm_lab_sources')
        self.queue_dir = config.get('queue_dir', 'data/vm_lab_queue')
        self.env = {
            'PATH': '/usr/bin:/bin', 'HOME': str(self.state), 'LANG': 'C.UTF-8',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'GIT_TERMINAL_PROMPT': '0', 'GIT_SSH_COMMAND': config['ssh_command'],
            'GIT_AUTHOR_NAME': 'VM Compute', 'GIT_AUTHOR_EMAIL': 'vm-compute@users.noreply.github.com',
            'GIT_COMMITTER_NAME': 'VM Compute', 'GIT_COMMITTER_EMAIL': 'vm-compute@users.noreply.github.com',
        }
        if not self.repo.exists():
            subprocess.run(['/usr/bin/git', 'init', '--bare', str(self.repo)],
                           env=self.env, check=True, capture_output=True)
            self.git('remote', 'add', 'origin', config['remote'])
        elif self.git('remote', 'get-url', 'origin').decode().strip() != config['remote']:
            raise ValueError('Existing clone belongs to another repository; clean setup required')

    def git(self, *args, data=None, extra_env=None):
        command = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'gc.auto=0',
                   '-c', 'protocol.file.allow=never', '-c', 'protocol.ext.allow=never',
                   '--git-dir=' + str(self.repo), *args]
        result = subprocess.run(command, input=data, env={**self.env, **(extra_env or {})},
                                capture_output=True, timeout=120)
        if result.returncode:
            raise RuntimeError('git ' + args[0] + ': ' + result.stderr.decode('utf-8', 'replace')[-700:])
        return result.stdout

    def save(self, record):
        record['updated'] = time.time()
        atomic_private(self.records / (record['run_id'] + '.json'), record)
        self.work.write(self.status_dir + '/' + record['run_id'] + '.json', json_bytes(record))

    def discover(self):
        for name in self.work.names(self.queue_dir)[:1000]:
            if not name.endswith('.json') or not ID.fullmatch(name[:-5]):
                continue
            path = self.records / name
            if path.exists():
                continue
            try:
                request = json.loads(self.work.read(self.queue_dir + '/' + name, 4096))
                if not isinstance(request, dict) or request.get('run_id') != name[:-5] or not isinstance(request.get('commit'),str) or not SHA.fullmatch(request['commit']):
                    raise ValueError('Expected run_id and a full 40-character commit SHA')
                plan = None
                if set(request) == {'run_id','commit'}:
                    if not self.config.get('allow_legacy_requests',False):
                        raise ValueError('New requests require an exact approved run plan')
                elif set(request) == {'run_id','commit','run_plan','run_plan_sha256'}:
                    from run_contract import check_authorization, canonical_hash
                    plan=json.loads(self.work.read(request['run_plan'],32768))
                    approval_path=self.state/'authorizations'/(name[:-5]+'.json')
                    if approval_path.is_symlink(): raise ValueError('Approval cannot be a symlink')
                    approval=json.loads(approval_path.read_text())
                    bound=check_authorization(plan,approval)
                    if bound != request['run_plan_sha256'] or plan['run_id'] != request['run_id'] or plan['source']['commit'] != request['commit']:
                        raise ValueError('Request differs from approved plan')
                    if plan['source'].get('repository') != self.config['repository'] or plan['executor'] != {'kind':'vm','id':self.config.get('executor_id','legacy-github-bridge')}:
                        raise ValueError('Plan is for another repository/executor')
                    if plan['command'] != {'entrypoint':'run.py','args':[]}:
                        raise ValueError('Bridge v1 only executes declared run.py')
                    # Cap enforcement belongs to the worker, never infer it from an Issue label.
                    limits=self.config.get('verified_worker_limits')
                    if not limits or not limits.get('evidence_ref'):
                        raise ValueError('Worker limit enforcement has not been attested')
                    for key in ('hard_wall_seconds','memory_limit_mib','disk_limit_mib'):
                        if limits.get(key, float('inf')) > plan['budget'][key]:
                            raise ValueError('Worker limit exceeds approved budget: '+key)
                else:
                    raise ValueError('Unexpected request fields')
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.save({'run_id': name[:-5], 'stage': 'rejected', 'last_error': str(exc)[:1000]})
                continue
            self.save({'run_id': request['run_id'], 'source_commit': request['commit'],
                       'repository': self.config['repository'], 'stage': 'accepted', 'created': time.time(),
                       'run_plan':plan,'authorization_mode':'EXACT_PRIVATE_APPROVAL' if plan else 'EXPLICIT_LEGACY_COMPATIBILITY'})

    def prepare(self, record):
        rid, commit = record['run_id'], record['source_commit']
        self.git('fetch', '--no-tags', '--depth=1', 'origin', commit)
        actual = self.git('rev-parse', 'FETCH_HEAD').decode().strip()
        if actual != commit:
            raise ValueError('Fetched commit differs from request')
        # No checkout, hooks, attributes, submodules or repository code on the networked host.
        tree = self.git('ls-tree', '-rz', '--full-tree', commit)
        allowed = []
        total = 0
        for item in tree.split(b'\0'):
            if not item:
                continue
            metadata, name = item.split(b'\t', 1)
            name = name.decode('utf-8')
            if name.split('/')[0] in {'infra', 'results'} or any(p.startswith('.') for p in PurePosixPath(name).parts):
                continue
            safe_parts(name)
            mode, kind, oid = metadata.decode().split()
            if kind != 'blob' or mode not in {'100644', '100755'}:
                raise ValueError('Source symlinks and submodules are unsupported')
            size = int(self.git('cat-file', '-s', oid))
            total += size
            if size > MAX_FILE or total > MAX_TOTAL or len(allowed) >= MAX_FILES:
                raise ValueError('Source snapshot exceeds limits')
            allowed.append((name, oid))
        files = {name: self.git('cat-file', 'blob', oid) for name, oid in allowed}
        if not {'run.py', 'config.json'} <= files.keys():
            raise ValueError('The source commit needs run.py and config.json')
        json.loads(files['config.json'])
        manifest = {name: digest(data) for name, data in files.items()}
        if record.get('run_plan'):
            from run_contract import canonical_hash, check_authorization
            plan=record['run_plan']
            approval=json.loads((self.state/'authorizations'/(rid+'.json')).read_text())
            check_authorization(plan,approval)  # Recheck expiry immediately before queuing.
            if self.git('rev-parse',commit+'^{tree}').decode().strip()!=plan['source']['tree_sha']:
                raise ValueError('Source tree differs from plan')
            if digest(files['config.json'])!=plan['source']['config_sha256'] or canonical_hash(manifest)!=plan['source']['input_manifest_sha256']:
                raise ValueError('Source/configuration digest differs from plan')

        prefix = self.source_dir + '/' + rid
        for name, data in files.items():
            self.work.write(prefix + '/' + name, data, replace=False)
        wrapper = (
            'import hashlib, os, runpy, sys\nfrom pathlib import Path\n'
            + 'root = Path(' + repr(str(self.work.path / prefix)) + ')\n'
            + 'expected = ' + repr(manifest) + '\n'
            + 'for name, sha in expected.items():\n'
            + '    p = root / name\n'
            + '    if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != sha:\n'
            + '        raise RuntimeError("Source input changed: " + name)\n'
            + 'os.environ["VM_SOURCE_COMMIT"] = ' + repr(commit) + '\n'
            + 'os.environ["VM_SOURCE_DIR"] = str(root)\n'
            + 'sys.path.insert(0, str(root))\nsys.argv = [str(root / "run.py")]\n'
            + 'runpy.run_path(sys.argv[0], run_name="__main__")\n'
        ).encode()
        record.update(input_sha256=manifest, wrapper_sha256=digest(wrapper))
        self.save(record)  # Persist identity before publishing a runnable job.
        self.queue_job(rid, wrapper)
        record.update(stage='queued', last_error=None)
        self.save(record)

    def queue_job(self, rid, wrapper):
        identity = {'source_sha256': digest(wrapper), 'args': []}
        try:
            old = json.loads(self.work.read('jobs/' + rid + '/request.json', 4096))
            if old != identity:
                raise ValueError('Job id already used for different code')
            return
        except FileNotFoundError:
            pass
        health = json.loads(self.work.read('worker-health.json', 4096))
        if time.time() - health.get('heartbeat', 0) > 15:
            raise RuntimeError('Existing worker is not responding')
        if shutil.disk_usage(self.work.path).free < 768 * 1024**2:
            raise RuntimeError('Less than 768 MiB free disk')
        with self.work.directory(('jobs',)) as jobs:
            temp = '.github-' + secrets.token_hex(12)
            os.mkdir(temp, 0o770, dir_fd=jobs)
            fd = os.open(temp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=jobs)
            try:
                os.fchmod(fd, 0o770)
                contents = {
                    'main.py': wrapper, 'request.json': json_bytes(identity),
                    'status.json': json_bytes({'state': 'queued', 'created': time.time(), 'source_sha256': digest(wrapper)}),
                }
                for name, data in contents.items():
                    out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o660, dir_fd=fd)
                    with os.fdopen(out, 'wb') as handle:
                        os.fchmod(handle.fileno(), 0o660)
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                os.fsync(fd)
                os.rename(temp, rid, src_dir_fd=jobs, dst_dir_fd=jobs)
                os.fsync(jobs)
            finally:
                os.close(fd)

    def collect(self, record, status):
        rid = record['run_id']
        files, errors, total = {}, [], 0
        candidates = []
        log_metadata = {'full_path': 'jobs/' + rid + '/output.log'}
        try:
            data, detail = self.export_log(log_metadata['full_path'])
            files['output.log'] = data
            total += len(data)
            log_metadata.update(detail)
        except FileNotFoundError as exc:
            if 'started' not in status:
                files['output.log'] = ('No process was started; worker state: ' + str(status.get('state')) + '\n').encode()
                log_metadata.update(method='no_process', original_bytes=0, omitted_bytes=0)
            else:
                errors.append('output.log: ' + str(exc))
        except (OSError, ValueError) as exc:
            errors.append('output.log: ' + str(exc))
        try:
            for name in self.work.files('results/' + rid + '/report'):
                candidates.append(('files/' + name, 'results/' + rid + '/report/' + name))
                if len(candidates) >= MAX_FILES:
                    errors.append('More than %d result files; excess omitted' % MAX_FILES)
                    break
        except FileNotFoundError:
            if status.get('state') == 'completed':
                errors.append('Successful job did not create report/')
        except (OSError, ValueError) as exc:
            errors.append('Result listing: ' + str(exc))
        for destination, source in candidates[:MAX_FILES - 1]:
            try:
                data = self.work.read(source)
                if total + len(data) > MAX_TOTAL:
                    raise ValueError('Total result export limit exceeded')
                files[destination] = data
                total += len(data)
            except (OSError, ValueError) as exc:
                errors.append(destination + ': ' + str(exc))
        if status.get('state') == 'completed':
            for required in ('files/README.md', 'files/metrics.json', 'files/data_manifest.json'):
                if required not in files:
                    errors.append('Required report file missing: ' + required)
        retained, retained_errors = self.retained_inventory(rid)
        manifest = {
            'run_id': rid, 'repository': record['repository'], 'source_commit': record['source_commit'],
            'input_sha256': record['input_sha256'], 'job': status, 'export_errors': errors,
            'report_profile': 'medium-v1', 'selection': 'Only report/ is published; full/ remains on VM',
            'full_data': retained, 'full_data_inventory_errors': retained_errors, 'log_export': log_metadata,
            'files': {name: {'sha256': digest(data), 'bytes': len(data)} for name, data in files.items()},
        }
        files['run.json'] = json_bytes(manifest)
        if record.get('run_plan'):
            from run_contract import canonical_hash
            plan=record['run_plan']
            process={'schema':'vm-lab-process-v1','run_id':rid,'source_commit':record['source_commit'],
                     'state':str(status.get('state','unknown')).upper(),
                     'technical_gate':'REVIEW_REQUIRED','scientific_confirmation':False,
                     'reason':'Execution receipt requires separate runtime/resource and scientific review',
                     'worker_limits_evidence':self.config.get('verified_worker_limits'),
                     'worker_status':status}
            files['RUN_PLAN.json']=json_bytes(plan)
            files['PROCESS.json']=json_bytes(process)
            receipt={'schema':'vm-lab-result-manifest-v1','run_id':rid,'source_commit':record['source_commit'],
                     'plan_sha256':canonical_hash(plan),
                     'files':[{'path':name,'sha256':digest(data),'size_bytes':len(data)} for name,data in sorted(files.items())]}
            files['RESULT_MANIFEST.json']=json_bytes(receipt)
        spool = self.state / 'exports' / rid
        spool.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            target = spool / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        for directory, _, _ in os.walk(spool):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        record.update(stage='exporting', job_state=status.get('state'),
                      export_files=list(files), export_sha256={name: digest(data) for name, data in files.items()},
                      export_errors=errors)
        self.save(record)

    def export_log(self, path):
        parts = safe_parts(path)
        with self.work.directory(parts[:-1]) as parent:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError('Log must be a regular non-hardlinked file')
            size = before.st_size
            if size <= MAX_FILE:
                data = handle.read(MAX_FILE + 1)
                detail = {'method': 'full', 'original_bytes': size, 'omitted_bytes': 0}
            else:
                part = MAX_FILE // 4
                first = handle.read(part)
                handle.seek(size - part)
                last = handle.read(part)
                omitted = size - len(first) - len(last)
                data = first + ('\n[... %d log bytes omitted; full log retained on VM ...]\n' % omitted).encode() + last
                detail = {'method': 'head_tail', 'original_bytes': size, 'head_bytes': len(first),
                          'tail_bytes': len(last), 'omitted_bytes': omitted}
            after = os.fstat(handle.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('Log changed while collecting')
        return data, detail

    def retained_inventory(self, rid):
        entries, errors = [], []
        root = 'results/' + rid + '/full'
        try:
            for name in self.work.files(root):
                path = root + '/' + name
                parts = safe_parts(path)
                with self.work.directory(parts[:-1]) as parent:
                    info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                entries.append({'path': path, 'bytes': info.st_size,
                                'type': 'file' if stat.S_ISREG(info.st_mode) and info.st_nlink == 1 else 'blocked'})
                if len(entries) >= 5000:
                    errors.append('Full-data inventory capped at 5000 entries')
                    break
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
        return entries, errors

    def publish(self, record):
        rid = record['run_id']
        files = {}
        for name in record['export_files']:
            data = (self.state / 'exports' / rid / name).read_bytes()
            if digest(data) != record['export_sha256'][name]:
                raise ValueError('Saved export changed: ' + name)
            files['results/' + rid + '/' + name] = data
        mode = self.config.get('publication_mode', 'result_branch')
        if mode not in {'result_branch', 'legacy_main'}:
            raise ValueError('Unknown publication mode')
        branch = 'results/' + rid if mode == 'result_branch' else 'main'
        commit = self.publish_files(files, 'VM results: ' + rid, branch=branch, immutable=(mode == 'result_branch'))
        record['publication_branch'] = branch
        record['integration_state'] = 'PR_REQUIRED' if mode == 'result_branch' else 'LEGACY_DIRECT_MAIN'
        record['compare_url'] = 'https://github.com/' + record['repository'] + '/compare/main...' + branch
        record.update(stage='published', results_commit=commit, last_error=None,
                      results_url='https://github.com/' + record['repository'] + '/tree/' + commit + '/results/' + rid)
        self.save(record)

    def publish_files(self, files, message, branch="main", immutable=False):
        if branch != "main" and not (branch.startswith("results/") and ID.fullmatch(branch[len("results/"):])):
            raise ValueError("Invalid result branch")
        if immutable:
            if any(not name.startswith(branch + "/") for name in files):
                raise ValueError("Result publication cannot edit code or registries")
            existing = self.git("ls-remote", "--heads", "origin", "refs/heads/" + branch).decode().strip()
            if existing:
                commit = existing.split()[0]
                self.git("fetch", "--no-tags", "--depth=1", "origin", "refs/heads/" + branch)
                actual_paths = set(self.git("ls-tree", "-r", "--name-only", commit, "--", branch + "/").decode().splitlines())
                if actual_paths != set(files):
                    raise ValueError("Existing run_id has a different artifact inventory")
                for name,data in files.items():
                    if self.git("show", commit + ":" + name) != data:
                        raise ValueError("Existing run_id has different immutable results")
                return commit
        self.git('fetch', '--no-tags', '--depth=1', 'origin', 'refs/heads/main')
        base = self.git('rev-parse', 'FETCH_HEAD').decode().strip()
        if immutable and self.git('ls-tree', '-r', '--name-only', base, '--', branch + '/').strip():
            raise ValueError('run_id is already published in main')
        index = self.state / ('index-' + secrets.token_hex(8))
        environment = {'GIT_INDEX_FILE': str(index)}
        try:
            self.git('read-tree', base, extra_env=environment)
            for name, data in files.items():
                safe_parts(name)
                oid = self.git('hash-object', '-w', '--stdin', data=data).decode().strip()
                self.git('update-index', '--add', '--cacheinfo', '100644', oid,
                         name, extra_env=environment)
            tree = self.git('write-tree', extra_env=environment).decode().strip()
            if tree == self.git('rev-parse', base + '^{tree}').decode().strip():
                commit = base  # Previous push succeeded before the process stopped.
            else:
                commit = self.git('commit-tree', tree, '-p', base,
                                  data=(message + '\n').encode()).decode().strip()
                self.git('push', 'origin', commit + ':refs/heads/' + branch)  # Never force-push.
            return commit
        finally:
            index.unlink(missing_ok=True)

    def tick(self):
        self.discover()
        for path in sorted(self.records.glob('*.json')):
            record = json.loads(path.read_text())
            if record['stage'] in {'published', 'rejected'} or record.get('retry_after', 0) > time.time():
                continue
            try:
                if record['stage'] == 'accepted':
                    self.prepare(record)
                if record['stage'] == 'queued':
                    status = json.loads(self.work.read('jobs/' + record['run_id'] + '/status.json', 16384))
                    if status.get('state') in TERMINAL:
                        self.collect(record, status)
                if record['stage'] == 'exporting':
                    self.publish(record)
            except (OSError, ValueError, RuntimeError, TypeError, KeyError, subprocess.SubprocessError) as exc:
                record.update(last_error=str(exc)[:1000], retry_after=time.time() + 30)
                self.save(record)

    def run(self, once=False):
        lock = (self.state / 'bridge.lock').open('a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.work.write(self.status_dir + '/health.json', json_bytes({
            'heartbeat': time.time(), 'service': 'vm-lab-sync',
            'repository': self.config['repository'], 'initializing': True, 'error': None,
        }))
        while True:
            error = None
            try:
                self.tick()
            except (OSError, ValueError, RuntimeError, TypeError, KeyError, subprocess.SubprocessError) as exc:
                error = str(exc)[:1000]
                print(error, flush=True)
            self.work.write(self.status_dir + '/health.json', json_bytes({
                'heartbeat': time.time(), 'service': 'vm-lab-sync',
                'repository': self.config['repository'], 'error': error,
            }))
            if once:
                return
            time.sleep(self.config.get('poll_seconds', 2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    os.umask(0o027)
    Bridge(json.loads(Path(args.config).read_text())).run(once=args.once)
