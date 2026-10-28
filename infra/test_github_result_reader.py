import hashlib
import json
import unittest

from github_result_reader import read_github_result, UnconfirmedResult


class GitHubOnlyResults(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.inputs = {'repository': 'owner/vm-lab', 'run_id': 'github_reader_test',
                       'source_commit': '1' * 40, 'result_commit': '2' * 40}
        self.prefix = 'results/github_reader_test/'
        self.data = {'output.log': b'ok\n', 'files/result.bin': b'\x00\xff\x10\x80',
                     'files/result.json': b'{"answer":42}\n', 'files/README.md': b'Test report\n',
                     'files/metrics.json': b'{"answer":42}', 'files/data_manifest.json': b'{"selection":"all"}'}
        self.report = {key: self.inputs[key] for key in ('repository', 'run_id', 'source_commit')}
        self.report.update(job={'state': 'completed', 'exit_code': 0}, export_errors=[], report_profile='medium-v1',
                           files={k: {'sha256': hashlib.sha256(v).hexdigest(), 'bytes': len(v)} for k, v in self.data.items()})

    def fetch(self, repository, path, ref):
        self.calls.append((repository, path, ref))
        self.assertEqual(repository, self.inputs['repository'])
        self.assertEqual(ref, self.inputs['result_commit'])
        if path == self.prefix + 'run.json':
            return json.dumps(self.report).encode()
        return self.data[path[len(self.prefix):]]

    def read(self, fetch=None):
        return read_github_result(fetch or self.fetch, **self.inputs)

    def test_every_byte_is_fetched_at_one_github_commit(self):
        result = self.read()
        self.assertTrue(result['execution_succeeded'])
        self.assertEqual(result['result_source'], 'github')
        self.assertEqual(result['artifacts'], self.data)
        self.assertEqual(len(self.calls), 7)

    def test_no_fallback_when_github_is_unavailable(self):
        def unavailable(*_):
            raise ConnectionError('GitHub unavailable; VM data must not be used')
        with self.assertRaisesRegex(UnconfirmedResult, 'GitHub report is unavailable'):
            self.read(unavailable)

    def test_missing_artifact_is_not_success(self):
        del self.data['files/result.bin']
        with self.assertRaises(UnconfirmedResult):
            self.read()

    def test_tampered_artifact_is_rejected(self):
        self.data['files/result.bin'] = b'changed'
        with self.assertRaisesRegex(UnconfirmedResult, 'mismatch'):
            self.read()

    def test_wrong_source_version_is_rejected_before_artifact_reads(self):
        self.report['source_commit'] = '3' * 40
        with self.assertRaises(UnconfirmedResult):
            self.read()
        self.assertEqual(len(self.calls), 1)

    def test_partial_export_is_not_success(self):
        self.report['export_errors'] = ['a result exceeds the size limit']
        with self.assertRaisesRegex(UnconfirmedResult, 'incomplete'):
            self.read()

    def test_worker_failure_is_confirmed_but_not_successful(self):
        self.report['job'] = {'state': 'failed', 'exit_code': 7}
        result = self.read()
        self.assertFalse(result['execution_succeeded'])
        self.assertEqual(result['report']['job']['exit_code'], 7)

    def test_parent_path_is_rejected_without_fetching_it(self):
        self.report['files']['files/../../secret'] = {'bytes': 1, 'sha256': '0' * 64}
        with self.assertRaises(UnconfirmedResult):
            self.read()
        self.assertFalse(any('..' in path for _, path, _ in self.calls))


if __name__ == '__main__':
    unittest.main(verbosity=2)
