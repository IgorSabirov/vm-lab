#!/usr/bin/env python3
"""Publish the completed NOW run as byte-identical files. Run on VM host.

Uses the existing /etc/vm-lab-sync/config.json transport. No service changes,
no scientific computation, no archives, no force push. Standard library only.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

RUN = 'now_long_main_da72a3a_20261108'
SOURCE = 'da72a3a89176b77ceca75779923029534fd26b99'
DEST = 'results/NOW_LONG_da72a3a_20261108_RAW'
WORK = Path('/var/lib/vm-compute/work')
CONFIG = Path('/etc/vm-lab-sync/config.json')
EXTRAS = ('ARCHIVE.json', 'PROCESS.json', 'process.log', 'FOUR_CANDIDATE_RETURN.json')


def read_regular(path):
    # Reject links in every component, including the directory chain.
    for parent in reversed((path, *path.parents)):
        if parent.is_symlink():
            raise ValueError('Symlink refused: ' + str(parent))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError('Expected regular non-hardlinked file: ' + str(path))
        if before.st_size >= 100 * 1024**2:
            raise ValueError('File too large for this direct Git publication: ' + str(path))
        data = handle.read(100 * 1024**2)
        after = os.fstat(handle.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(data) != before.st_size:
            raise ValueError('File changed: ' + str(path))
    return data


def inventory(work):
    root = work / 'results' / RUN
    output = root / 'main_output'
    items = {}
    def visit(directory, prefix):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('Expected real directory: ' + str(directory))
        for entry in sorted(directory.iterdir()):
            if entry.name.startswith('.') or any(ord(c) < 32 for c in entry.name):
                raise ValueError('Unexpected path: ' + str(entry))
            if entry.is_symlink():
                raise ValueError('Symlink refused: ' + str(entry))
            name = prefix + '/' + entry.name
            if entry.is_dir():
                visit(entry, name)
            else:
                items[name] = entry
    visit(output, 'main_output')
    for name in EXTRAS:
        items[name] = root / name
    for name in ('output.log', 'status.json', 'request.json'):
        items['worker/' + name] = work / 'jobs' / RUN / name
    for name in ('now_long_forecast_da72a3a.json', 'now_long_calibration_plan_4292723.json'):
        items['inputs/' + name] = work / 'data' / name
    for name in ('PROCESS.json', 'process.log'):
        items['calibration/' + name] = work / 'results/now_long_cal_da72a3a_20261108' / name
    counts = {folder: sum(n.startswith('main_output/' + folder + '/') for n in items)
              for folder in ('rows', 'traces', 'geometry')}
    if counts != {'rows': 3083, 'traces': 235, 'geometry': 235}:
        raise ValueError('Unexpected output inventory: ' + str(counts))
    return items, counts


class Git:
    def __init__(self, directory, config):
        self.directory = directory
        self.env = {
            'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'GIT_TERMINAL_PROMPT': '0', 'GIT_SSH_COMMAND': config['ssh_command'],
            'GIT_AUTHOR_NAME': 'VM Compute',
            'GIT_AUTHOR_EMAIL': 'vm-compute@users.noreply.github.com',
            'GIT_COMMITTER_NAME': 'VM Compute',
            'GIT_COMMITTER_EMAIL': 'vm-compute@users.noreply.github.com',
        }
        self('init', '--bare', directory)
        self('remote', 'add', 'origin', config['remote'])

    def __call__(self, *args, data=None, check=True):
        result = subprocess.run([
            '/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'gc.auto=0',
            '-c', 'protocol.ext.allow=never', '-c', 'protocol.file.allow=never',
            '--git-dir=' + self.directory, *args], input=data, env=self.env,
            capture_output=True, timeout=600)
        if check and result.returncode:
            # Do not echo configuration, credential paths or remote error contents.
            raise RuntimeError('git ' + args[0] + ' failed (code ' + str(result.returncode) + ')')
        return result.stdout if check else result

    def tree(self, commit):
        result = {}
        for line in self('ls-tree', '-rz', commit, '--', DEST).split(b'\0'):
            if line:
                meta, name = line.split(b'\t', 1)
                mode, kind, oid = meta.decode().split()
                result[name.decode()] = (mode, kind, oid)
        return result


def publish(work=WORK, config_path=CONFIG):
    process = json.loads(read_regular(work / 'results' / RUN / 'PROCESS.json'))
    if (process.get('source_commit') != SOURCE or process.get('exit_code') != 0
            or not process['run'].get('complete') or process['run'].get('task_count') != 3083):
        raise ValueError('Run identity or completion mismatch')
    config = json.loads(read_regular(config_path))
    if config.get('repository') != 'IgorSabirov/vm-lab':
        raise ValueError('Wrong repository in transport config')
    if config.get('remote') not in (
            'ssh://git@ssh.github.com:443/IgorSabirov/vm-lab.git',
            'git@github.com:IgorSabirov/vm-lab.git'):
        raise ValueError('Unexpected Git remote')
    items, counts = inventory(work)
    with tempfile.TemporaryDirectory(prefix='now-raw-publish-') as temp:
        git = Git(temp + '/repo.git', config)
        expected, manifest = {}, {}
        for number, (name, path) in enumerate(sorted(items.items()), 1):
            data = read_regular(path)
            oid = git('hash-object', '-w', '--stdin', data=data).decode().strip()
            expected[DEST + '/' + name] = ('100644', 'blob', oid)
            manifest[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                              'git_blob_sha1': oid}
            if number % 250 == 0:
                print('Prepared', number, '/', len(items), flush=True)
        metadata = {
            'schema': 1, 'run_id': RUN, 'source_commit': SOURCE,
            'runtime_gate': process['run']['runtime_gate'],
            'scientific_confirmation': process['run']['scientific_confirmation'],
            'counts': counts, 'files': manifest,
            'file_count': len(manifest), 'total_bytes': sum(v['bytes'] for v in manifest.values()),
            'publication': 'Original bytes, original relative paths; no archive or encoding conversion.',
            'omitted': ['FULL_OUTPUT.zip (redundant archive; ARCHIVE.json retained)'],
        }
        data = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode()
        oid = git('hash-object', '-w', '--stdin', data=data).decode().strip()
        expected[DEST + '/PUBLICATION_MANIFEST.json'] = ('100644', 'blob', oid)
        # Recheck the full source snapshot before any remote write.
        current, _ = inventory(work)
        if current != items:
            raise ValueError('Source inventory changed')
        for name, path in items.items():
            if hashlib.sha256(read_regular(path)).hexdigest() != manifest[name]['sha256']:
                raise ValueError('Source changed: ' + name)
        for attempt in range(3):
            git('fetch', '--no-tags', '--depth=1', 'origin', 'refs/heads/main')
            base = git('rev-parse', 'FETCH_HEAD').decode().strip()
            existing = git.tree(base)
            if existing:
                if existing != expected:
                    raise ValueError('Existing destination differs; refusing to overwrite')
                commit = base
                break
            git('read-tree', base)
            index_data = b''.join(('100644 ' + value[2] + '\t' + name).encode() + b'\0'
                                  for name, value in sorted(expected.items()))
            git('update-index', '-z', '--index-info', data=index_data)
            tree = git('write-tree').decode().strip()
            if git.tree(tree) != expected:
                raise ValueError('Staged tree verification failed')
            commit = git('commit-tree', tree, '-p', base, data=(
                'Publish complete NOW da72a3a raw output and receipts\n').encode()).decode().strip()
            result = git('push', 'origin', commit + ':refs/heads/main', check=False)
            if result.returncode == 0:
                break
            # A race or lost acknowledgement is resolved against a fresh main.
        else:
            raise RuntimeError('Push not confirmed after three attempts; safe to rerun')
        git('fetch', '--no-tags', '--depth=1', 'origin', 'refs/heads/main')
        head = git('rev-parse', 'FETCH_HEAD').decode().strip()
        if git.tree(head) != expected:
            raise ValueError('Remote tree does not match the complete source snapshot')
        print('PUBLISHED_AND_VERIFIED', json.dumps({
            'commit': commit, 'verified_main': head, 'files': len(items),
            'bytes': metadata['total_bytes'], 'counts': counts,
            'runtime_gate': metadata['runtime_gate'],
            'url': 'https://github.com/IgorSabirov/vm-lab/tree/' + head + '/' + DEST,
        }), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    # The host entry point needs permission to read both the results and the existing key.
    # Never invoke it through the isolated scientific worker.
    lock_path = '/run/lock/now-long-raw-publication.lock'
    with open(lock_path, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        publish()


if __name__ == '__main__':
    main()
