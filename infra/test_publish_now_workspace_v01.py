"""Offline smoke checks; all remotes and files are temporary and local."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


p = module('publish_now_workspace_v01')
r = module('restore_now_workspace_v01')


class ExportTests(unittest.TestCase):
    def test_inventory_excludes_symlinks_and_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in p.ROOTS:
                (root / name).mkdir()
            (root / 'code/a.py').write_text('print(1)')
            (root / 'code/token.txt').write_text('never_export')
            (root / 'data/link').symlink_to(root / 'code/a.py')
            files, excluded, size = p.inventory(root, 1024)
            self.assertEqual([f['path'] for f in files], ['code/a.py'])
            self.assertEqual(len(excluded), 2)
            self.assertEqual(size, 8)

    def test_archive_scan_detects_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'archive.zip'
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as out:
                out.writestr('log.txt', 'ghp_' + 'x' * 40)
            with self.assertRaisesRegex(RuntimeError, 'credential_pattern'):
                p.scan_file(path)

    def test_git_push_preserves_existing_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original_run = subprocess.run
            def local_only(command, **kwargs):
                # Permit only file transport for this temporary remote; no network.
                command = ['protocol.file.allow=always' if s == 'protocol.file.allow=never' else s for s in command]
                return original_run(command, **kwargs)
            with patch.object(p.subprocess, 'run', side_effect=local_only):
                remote = root / 'remote.git'
                cfg = {'remote': str(remote), 'ssh_command': '/usr/bin/false'}
                a = p.Git(root / 'a.git', cfg)
                a.run('init', '--bare', str(remote))
                oid = a.blob(b'original')
                tree = a.run('mktree', data=('100644 blob ' + oid + '\tkeep.txt\n').encode()).decode().strip()
                commit = a.run('commit-tree', tree, data=b'initial\n').decode().strip()
                a.run('push', 'origin', commit + ':refs/heads/main')
                b = p.Git(root / 'b.git', cfg)
                new = b.blob(b'new data')
                last = b.commit({'results/snapshot/file.bin': new}, 'export')
                paths = b.run('ls-tree', '-r', '--name-only', last).decode().splitlines()
                self.assertEqual(paths, ['keep.txt', 'results/snapshot/file.bin'])
                self.assertEqual(b.run('show', last + ':results/snapshot/file.bin'), b'new data')

    def test_chunk_restore_and_path_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / 'repo'
            repo.mkdir()
            parts = []
            for i, raw in enumerate([b'ab', b'cd']):
                (repo / str(i)).write_bytes(raw)
                parts.append({'offset': i * 2, 'bytes': 2, 'sha256': hashlib.sha256(raw).hexdigest(), 'repository_path': str(i)})
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'status': 'COMPLETE', 'files': [{'path': 'data/x.bin', 'status': 'PUBLISHED', 'bytes': 4, 'sha256': hashlib.sha256(b'abcd').hexdigest(), 'parts': parts}]}))
            r.restore(repo, manifest, root / 'out')
            self.assertEqual((root / 'out/data/x.bin').read_bytes(), b'abcd')
            with self.assertRaises(ValueError):
                r.below(repo, '../escape')


if __name__ == '__main__':
    unittest.main()
