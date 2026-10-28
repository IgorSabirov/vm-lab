"""Accept execution reports only through a supplied GitHub file reader.

There is intentionally no VM client, filesystem reader, or fallback transport.
The production adapter calls the GitHub connector for each path at result_commit.
Local integration tests substitute a separate bare Git repository for GitHub.
"""
import hashlib
import json
import re


class UnconfirmedResult(RuntimeError):
    """No complete, matching report has been verified in GitHub."""


def _relative(path):
    return isinstance(path, str) and bool(path) and all(
        part and not part.startswith('.') and not any(ord(c) < 32 for c in part)
        for part in path.split('/')
    )


def read_github_result(fetch_file, *, repository, result_commit, run_id, source_commit):
    """fetch_file(repository, path, ref) -> bytes; every read pins the same ref.

    Return a verified report, including artifacts obtained from GitHub. A valid
    failed/cancelled/interrupted execution is a confirmed report, not a success.
    Missing files, wrong versions, changed bytes and incomplete exports fail closed.
    """
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise UnconfirmedResult('Invalid repository')
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,64}', run_id):
        raise UnconfirmedResult('Invalid run id')
    for value in (source_commit, result_commit):
        if not re.fullmatch(r'[0-9a-f]{40}', value):
            raise UnconfirmedResult('A full immutable commit SHA is required')
    prefix = 'results/' + run_id + '/'

    def get(path):
        try:
            data = fetch_file(repository, path, result_commit)
        except Exception as exc:
            raise UnconfirmedResult('GitHub report is unavailable: ' + path) from exc
        if not isinstance(data, bytes):
            raise UnconfirmedResult('GitHub adapter must return exact bytes')
        return data

    try:
        report = json.loads(get(prefix + 'run.json'))
    except (ValueError, UnicodeError) as exc:
        raise UnconfirmedResult('Invalid GitHub report JSON') from exc
    if not isinstance(report, dict) or any(report.get(key) != value for key, value in {
        'repository': repository, 'run_id': run_id, 'source_commit': source_commit,
    }.items()):
        raise UnconfirmedResult('Report does not match the requested repository, run or code version')
    if report.get('export_errors') != []:
        raise UnconfirmedResult('GitHub export is incomplete; inspect export_errors in GitHub')
    job = report.get('job')
    if not isinstance(job, dict) or job.get('state') not in {'completed', 'failed', 'cancelled', 'interrupted'}:
        raise UnconfirmedResult('Report has no terminal execution state')
    if job['state'] == 'completed' and (type(job.get('exit_code')) is not int or job['exit_code'] != 0):
        raise UnconfirmedResult('Completed report has an invalid exit code')
    files = report.get('files')
    if not isinstance(files, dict) or 'output.log' not in files or len(files) > 512:
        raise UnconfirmedResult('Report has no exported log')
    if report.get('report_profile') != 'medium-v1':
        raise UnconfirmedResult('Unknown report profile')
    if job['state'] == 'completed' and not {
        'files/README.md', 'files/metrics.json', 'files/data_manifest.json'
    } <= files.keys():
        raise UnconfirmedResult('Successful execution lacks the required detailed report')
    artifacts = {}
    total = 0
    for name, expected in files.items():
        if not _relative(name) or (name != 'output.log' and not name.startswith('files/')):
            raise UnconfirmedResult('Artifact path escapes the result directory')
        if not isinstance(expected, dict) or type(expected.get('bytes')) is not int or not 0 <= expected['bytes'] <= 8 * 1024**2:
            raise UnconfirmedResult('Invalid artifact metadata')
        total += expected['bytes']
        if total > 32 * 1024**2:
            raise UnconfirmedResult('Artifact set exceeds the supported export size')
        data = get(prefix + name)
        if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected.get('sha256'):
            raise UnconfirmedResult('GitHub artifact size/hash mismatch: ' + name)
        artifacts[name] = data
    return {
        'result_source': 'github', 'repository': repository, 'result_commit': result_commit,
        'source_commit': source_commit, 'run_id': run_id, 'report': report,
        'execution_succeeded': job['state'] == 'completed' and job['exit_code'] == 0,
        'artifacts': artifacts,
    }
