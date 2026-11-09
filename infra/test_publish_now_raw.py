import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import publish_now_raw as p


class LocalGit(p.Git):
    """Exercise actual Git objects, commits and pushes against a local fixture."""
    remote = None

    def __init__(self, directory, config):
        super().__init__(directory, {**config, 'remote': self.remote})

    def __call__(self, *args, **kwargs):
        if args[0] in ('fetch', 'push', 'ls-remote'):
            args = ('-c', 'protocol.file.allow=always', *args)
        return super().__call__(*args, **kwargs)


class PublicationTest(unittest.TestCase):
    def test_real_push_rerun_and_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote = root / 'remote.git'
            subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            LocalGit.remote = str(remote)
            seed = LocalGit(str(root / 'seed.git'), {'ssh_command': 'false'})
            empty = seed('mktree', data=b'').decode().strip()
            commit = seed('commit-tree', empty, data=b'fixture\n').decode().strip()
            seed('push', 'origin', commit + ':refs/heads/main')
            process = root / 'results' / p.RUN / 'PROCESS.json'
            process.parent.mkdir(parents=True)
            process.write_text(json.dumps({'source_commit': p.SOURCE, 'exit_code': 0,
                'run': {'complete': True, 'task_count': 3083, 'runtime_gate': 'REVIEW_REQUIRED',
                        'scientific_confirmation': False}}))
            binary = root / 'binary.dat'
            binary.write_bytes(bytes(range(256)) + b'\r\n\x00')
            text = root / 'text.json'
            text.write_bytes(b'{"unchanged":true}\r\n')
            config = root / 'config.json'
            config.write_text(json.dumps({'repository': 'IgorSabirov/vm-lab',
                'remote': 'ssh://git@ssh.github.com:443/IgorSabirov/vm-lab.git',
                'ssh_command': 'false'}))
            mapping = {'PROCESS.json': process, 'main_output/binary.dat': binary,
                       'main_output/text.json': text}
            with patch.object(p, 'Git', LocalGit), patch.object(p, 'inventory',
                    return_value=(mapping, {'rows': 3083, 'traces': 235, 'geometry': 235})):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    p.publish(root, config)
                    first = seed('ls-remote', 'origin', 'refs/heads/main')
                    p.publish(root, config)
                    self.assertEqual(first, seed('ls-remote', 'origin', 'refs/heads/main'))
                self.assertEqual(output.getvalue().count('PUBLISHED_AND_VERIFIED'), 2)
                seed('fetch', 'origin', 'refs/heads/main')
                self.assertEqual(seed('show', 'FETCH_HEAD:' + p.DEST + '/main_output/binary.dat'),
                                 binary.read_bytes())
                self.assertEqual(seed('show', 'FETCH_HEAD:' + p.DEST + '/main_output/text.json'),
                                 text.read_bytes())
                manifest = json.loads(seed('show', 'FETCH_HEAD:' + p.DEST + '/PUBLICATION_MANIFEST.json'))
                self.assertEqual(manifest['runtime_gate'], 'REVIEW_REQUIRED')
                self.assertFalse(manifest['scientific_confirmation'])
                binary.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'Existing destination differs'):
                    p.publish(root, config)

    def test_inventory_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            out = work / 'results' / p.RUN / 'main_output'
            for folder, count in [('rows', 3083), ('traces', 235), ('geometry', 235)]:
                (out / folder).mkdir(parents=True)
                for number in range(count):
                    (out / folder / str(number)).write_bytes(b'{}')
            items, counts = p.inventory(work)
            self.assertEqual(counts['rows'], 3083)
            self.assertEqual(len([n for n in items if n.startswith('main_output/')]), 3553)
            (out / 'rows/0').unlink()
            with self.assertRaisesRegex(ValueError, 'Unexpected output inventory'):
                p.inventory(work)
            (out / 'rows/0').symlink_to(out / 'rows/1')
            with self.assertRaisesRegex(ValueError, 'Symlink refused'):
                p.inventory(work)
            with self.assertRaisesRegex(ValueError, 'Symlink refused'):
                p.read_regular(out / 'rows/0')


if __name__ == '__main__':
    unittest.main()
