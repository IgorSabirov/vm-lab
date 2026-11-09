#!/usr/bin/env python3
"""Publish research workspace to IgorSabirov/vm-lab; host-side, resumable, no science runs.

Uses only the existing /etc/vm-lab-sync/config.json transport. No data deletion,
force push, new compression, external upload, credential export or service changes.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import uuid
import zipfile

REPOSITORY = 'IgorSabirov/vm-lab'
REMOTES = {'ssh://git@ssh.github.com:443/IgorSabirov/vm-lab.git', 'git@github.com:IgorSabirov/vm-lab.git'}
WORK = Path('/var/lib/vm-compute/work')
STATE = Path('/var/lib/vm-compute/publication/now-workspace-v01')
CHUNK = 48 * 1024**2
BATCH = 128 * 1024**2
RESERVE = 512 * 1024**2
ROOTS = ('code', 'data', 'results', 'jobs')
CACHE = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'site-packages', '.cache'}
SENSITIVE_NAME = re.compile(r'(^|[._-])(credentials?|secrets?|tokens?|passwords?|private[_-]?key)([._-]|$)|^id_(rsa|ed25519|ecdsa)$|^\.env($|\.)', re.I)
SECRET = re.compile(rb'-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----|(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})|https?://[^\s/]+\.sslip\.io/[a-fA-F0-9]{40,}/|(?i:bearer)[ \t]+[A-Za-z0-9_.-]{24,}|(?i:[\"\x27]?(?:token|password|api[_-]?key|secret)[\"\x27]?[ \t]*[:=][ \t]*[\"\x27])[A-Za-z0-9_./+-]{24,}')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_bytes(encoded(value))
    os.replace(temp, path)


def signature(path):
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode):
        raise RuntimeError('not_regular')
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def scan_stream(stream, budget):
    tail = b''
    while True:
        data = stream.read(1024**2)
        if not data:
            break
        budget[0] -= len(data)
        if budget[0] < 0:
            raise RuntimeError('archive_scan_limit')
        if SECRET.search(tail + data):
            raise RuntimeError('credential_pattern')
        tail = data[-4096:]


def scan_file(path):
    # Scan original bytes and supported archive members without extracting them.
    with path.open('rb') as stream:
        scan_stream(stream, [6 * 1024**3])
    name = path.name.lower()
    budget = [1024**3]
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                if SENSITIVE_NAME.search(Path(item.filename).name):
                    raise RuntimeError('credential_member_name')
                if item.filename.lower().endswith(('.zip', '.npz', '.gz', '.xz', '.bz2', '.tar', '.7z')):
                    raise RuntimeError('nested_archive_requires_review')
                with archive.open(item) as stream:
                    scan_stream(stream, budget)
    elif name.endswith(('.tar', '.tar.gz', '.tgz', '.tar.xz', '.txz', '.tar.bz2')):
        with tarfile.open(path, 'r:*') as archive:
            for item in archive:
                if item.isdir():
                    continue
                if not item.isfile() or SENSITIVE_NAME.search(Path(item.name).name):
                    raise RuntimeError('unsafe_archive_member')
                if item.name.lower().endswith(('.zip', '.npz', '.gz', '.xz', '.bz2', '.tar', '.7z')):
                    raise RuntimeError('nested_archive_requires_review')
                with archive.extractfile(item) as stream:
                    scan_stream(stream, budget)
    elif name.endswith(('.gz', '.xz', '.bz2', '.7z', '.rar', '.zst')):
        raise RuntimeError('unsupported_compression_requires_review')


def inventory(work, max_bytes):
    files, exclusions, total = [], [], 0
    for root in ROOTS:
        base = work / root
        if not base.exists() or base.is_symlink():
            exclusions.append({'path': root, 'reason': 'missing_or_symlink_root'})
            continue
        for directory, dirs, names in os.walk(base, followlinks=False):
            keep = []
            for name in sorted(dirs):
                path = Path(directory) / name
                if path.is_symlink() or name in CACHE or name.startswith('.') or SENSITIVE_NAME.search(name):
                    exclusions.append({'path': str(path.relative_to(work)), 'reason': 'excluded_directory'})
                else:
                    keep.append(name)
            dirs[:] = keep
            for name in sorted(names):
                path = Path(directory) / name
                rel = str(path.relative_to(work))
                if path.is_symlink() or name.startswith('.') or SENSITIVE_NAME.search(name) or name.endswith(('.pyc', '.pyo', '.pem', '.key')):
                    exclusions.append({'path': rel, 'reason': 'excluded_file'})
                    continue
                try:
                    sig = signature(path)
                except (OSError, RuntimeError):
                    exclusions.append({'path': rel, 'reason': 'not_readable_regular'})
                    continue
                if total + sig[2] > max_bytes:
                    exclusions.append({'path': rel, 'reason': 'capacity_limit', 'bytes': sig[2]})
                    continue
                total += sig[2]
                files.append({'path': rel, 'signature': sig, 'bytes': sig[2], 'status': 'PENDING', 'parts': []})
    return files, exclusions, total


class Git:
    def __init__(self, directory, cfg):
        self.directory = directory
        self.env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
                    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                    'GIT_TERMINAL_PROMPT': '0', 'GIT_SSH_COMMAND': cfg['ssh_command'],
                    'GIT_AUTHOR_NAME': 'VM Compute', 'GIT_AUTHOR_EMAIL': 'vm-compute@users.noreply.github.com',
                    'GIT_COMMITTER_NAME': 'VM Compute', 'GIT_COMMITTER_EMAIL': 'vm-compute@users.noreply.github.com'}
        self.run('init', '--bare', str(directory))
        self.run('remote', 'add', 'origin', cfg['remote'])
        self.run('config', 'remote.origin.promisor', 'true')
        self.run('config', 'remote.origin.partialclonefilter', 'blob:none')

    def run(self, *args, data=None, check=True):
        result = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'gc.auto=0',
                                 '-c', 'protocol.ext.allow=never', '-c', 'protocol.file.allow=never',
                                 '-c', 'pack.threads=1', '--git-dir=' + str(self.directory), *args],
                                input=data, env=self.env, capture_output=True, timeout=1200)
        if check and result.returncode:
            # Raw stderr stays on the host: it may contain transport credentials.
            log = self.directory.parent / 'transport-error.log'
            log.write_bytes(result.stderr)
            os.chmod(log, 0o600)
            raise RuntimeError('git_' + args[0] + '_failed_code_' + str(result.returncode))
        return result if not check else result.stdout

    def blob(self, data):
        return self.run('hash-object', '-w', '--stdin', data=data).decode().strip()

    def commit(self, entries, message):
        for attempt in range(4):
            self.run('fetch', '--no-tags', '--depth=1', '--filter=blob:none', 'origin', 'refs/heads/main')
            parent = self.run('rev-parse', 'FETCH_HEAD').decode().strip()
            self.run('read-tree', parent)
            lines = b''.join(('100644 blob ' + oid + '\t' + path).encode() + b'\0' for path, oid in entries.items())
            self.run('update-index', '-z', '--index-info', data=lines)
            tree = self.run('write-tree').decode().strip()
            commit = self.run('commit-tree', tree, '-p', parent, data=(message + '\n').encode()).decode().strip()
            self.run('update-ref', 'refs/heads/export', commit)
            pushed = self.run('push', 'origin', commit + ':refs/heads/main', check=False)
            if pushed.returncode == 0:
                remote = self.run('ls-remote', 'origin', 'refs/heads/main').decode().split()[0]
                if remote != commit:
                    self.run('fetch', '--no-tags', '--depth=64', '--filter=blob:none', 'origin', 'refs/heads/main')
                    self.run('merge-base', '--is-ancestor', commit, 'FETCH_HEAD')
                return commit
            (self.directory.parent / 'transport-error.log').write_bytes(pushed.stderr)
        raise RuntimeError('push_failed_after_4_attempts')


def publish(max_gib=5, new_snapshot=False):
    os.umask(0o077)
    STATE.mkdir(parents=True, exist_ok=True)
    lock = (STATE / 'lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    cfg = json.loads(Path('/etc/vm-lab-sync/config.json').read_text())
    if cfg.get('repository') != REPOSITORY or cfg.get('remote') not in REMOTES:
        raise RuntimeError('unexpected_repository_or_remote')
    state_path = STATE / 'STATE.json'
    if state_path.exists() and not new_snapshot:
        state = json.loads(state_path.read_text())
    else:
        files, exclusions, total = inventory(WORK, max_gib * 1024**3)
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8]
        state = {'schema': 'NOW_WORKSPACE_EXPORT_v0.1', 'snapshot': stamp, 'repository': REPOSITORY,
                 'destination': 'results/VM_WORKSPACE_SNAPSHOTS/' + stamp, 'roots': ROOTS,
                 'max_bytes': max_gib * 1024**3, 'selected_bytes': total, 'files': files,
                 'exclusions': exclusions, 'status': 'IN_PROGRESS', 'commits': [],
                 'publisher_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 'scope': 'Research workspace only; no host configuration, secrets, virtualenvs or new experiments.'}
        save(state_path, state)
    if state['status'].startswith('COMPLETE'):
        print(state['status'], state['destination'], flush=True)
        return
    temp = None
    git = None
    entries = {}
    batch_bytes = 0

    def begin():
        nonlocal temp, git
        if shutil.disk_usage(STATE).free < RESERVE + BATCH * 3:
            raise RuntimeError('insufficient_staging_disk')
        temp = tempfile.TemporaryDirectory(prefix='batch-', dir=STATE)
        git = Git(Path(temp.name) / 'repo.git', cfg)

    def flush(final=False):
        nonlocal temp, git, entries, batch_bytes
        if git is None:
            begin()
        if final:
            bad = any(f['status'] != 'PUBLISHED' for f in state['files']) or any(e['reason'] in ('capacity_limit', 'not_readable_regular', 'missing_or_symlink_root') for e in state['exclusions'])
            state['status'] = 'PARTIAL_REQUIRES_ATTENTION' if bad else ('COMPLETE_WITH_EXCLUSIONS' if state['exclusions'] else 'COMPLETE')
        public = {k: v for k, v in state.items() if k != 'commits'}
        entries[state['destination'] + '/MANIFEST.json'] = git.blob(encoded(public))
        commit = git.commit(entries, 'Preserve NOW research workspace ' + state['snapshot'])
        state['commits'].append(commit)
        save(state_path, state)
        print('PUSHED', commit, 'files', sum(f['status'] == 'PUBLISHED' for f in state['files']), '/', len(state['files']), flush=True)
        temp.cleanup()
        temp = git = None
        entries, batch_bytes = {}, 0

    try:
        for number, record in enumerate(state['files']):
            if record['status'] == 'PUBLISHED':
                continue
            path = WORK / record['path']
            try:
                if signature(path) != record['signature']:
                    raise RuntimeError('source_changed_since_inventory')
                scan_file(path)
                whole = hashlib.sha256()
                parts = []
                with path.open('rb') as stream:
                    offset = 0
                    while True:
                        data = stream.read(CHUNK)
                        if not data and offset:
                            break
                        whole.update(data)
                        parts.append({'offset': offset, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
                        offset += len(data)
                        if not data or offset == record['bytes']:
                            break
                if signature(path) != record['signature']:
                    raise RuntimeError('source_changed_during_scan')
                record['sha256'] = whole.hexdigest()
                record['parts'] = parts
                record['status'] = 'IN_PROGRESS'
                for i, part in enumerate(parts):
                    if git is None:
                        begin()
                    if signature(path) != record['signature']:
                        raise RuntimeError('source_changed_before_read')
                    with path.open('rb') as stream:
                        stream.seek(part['offset'])
                        data = stream.read(part['bytes'])
                    if hashlib.sha256(data).hexdigest() != part['sha256']:
                        raise RuntimeError('source_hash_changed')
                    dest = state['destination'] + ('/files/' + record['path'] if len(parts) == 1 else '/chunks/' + hashlib.sha256(record['path'].encode()).hexdigest() + '/' + str(i).zfill(6))
                    part['repository_path'] = dest
                    part['git_blob_sha1'] = git.blob(data)
                    entries[dest] = part['git_blob_sha1']
                    batch_bytes += len(data)
                    if i == len(parts) - 1:
                        record['status'] = 'PUBLISHED'
                    if batch_bytes >= BATCH:
                        flush()
            except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
                record['status'], record['reason'] = 'DEFERRED', type(exc).__name__
            except RuntimeError as exc:
                if str(exc).startswith(('git_', 'push_', 'insufficient_')):
                    raise
                record['status'], record['reason'] = 'DEFERRED', str(exc)
            if number % 100 == 0:
                print('PROGRESS', number, '/', len(state['files']), flush=True)
        flush(final=True)
        print(state['status'], state['destination'], flush=True)
    finally:
        if temp is not None:
            error = Path(temp.name) / 'transport-error.log'
            if error.exists():
                shutil.copyfile(error, STATE / 'transport-error.log')
            temp.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-gib', type=int, choices=range(1, 6), default=5)
    parser.add_argument('--new-snapshot', action='store_true')
    args = parser.parse_args()
    publish(args.max_gib, args.new_snapshot)
