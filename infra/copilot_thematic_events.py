#!/usr/bin/env python3
"""Read GitHub changes as data for the thematic review; never execute branch code.

Events preserve delivered revisions. Reconciliation catches durable changes for
which GitHub did not emit an Actions event (notably GITHUB_TOKEN writes). It
cannot reconstruct an intermediate edited/deleted body that GitHub never saved.
"""
import argparse
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone

REPOSITORY = 'IgorSabirov/vm-lab'
REPORT_BRANCH = 'copilot/thematic-reports'
REPORT_PREFIX = 'infra/copilot/reports/thematic/'
STATE_PATH = REPORT_PREFIX + 'MONITOR.json'
SIGNAL_PATH = '.github/workflows/thematic-events.yml'
SIGNAL_ARTIFACT = 'research-change-event'
IMPLEMENTATION_BRANCH = 'infra/copilot-thematic-review-20261121'
IMPLEMENTATION_REPAIR_BRANCH = 'infra/copilot-thematic-storage-20261121'
IMPLEMENTATION_ISSUES = {186}
IMPLEMENTATION_PATHS = {'.github/workflows/thematic-events.yml', '.github/workflows/copilot-thematic.yml',
    '.github/workflows/copilot-pr-validation.yml', 'infra/copilot/THEMATIC_REVIEW.md', 'infra/copilot/README.md'}
SHA = re.compile(r'^[0-9a-f]{40}$')
MAX_RAW_TEXT_BYTES = 10_000_000
BINARY_EXTENSIONS = {'.zip', '.gz', '.xz', '.bz2', '.7z', '.tar', '.npy', '.npz',
                     '.h5', '.hdf5', '.parquet', '.fits', '.bin', '.png', '.jpg',
                     '.jpeg', '.gif', '.webp', '.ico', '.pdf', '.mp4', '.sqlite',
                     '.woff', '.woff2', '.ttf', '.pkl', '.pickle', '.pt', '.pth'}


def encoded(value):
    return urllib.parse.quote(str(value), safe='')


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def numeric_array(value):
    return (isinstance(value, list) and all(numeric_array(x) for x in value)) or value is None or isinstance(value, (int, float))


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


class APIError(RuntimeError):
    def __init__(self, status, path, message=''):
        self.status = status
        self.code = status  # compatible with urllib HTTPError and publisher reads
        # Only the bounded top-level diagnostic is retained, never an echoed
        # request payload or the validation errors' arbitrary value fields.
        message = re.sub(r'(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+', '[REDACTED]', str(message))
        message = re.sub(r'(?i)bearer\s+\S+', 'Bearer [REDACTED]', message)
        message = ' '.join(message.split())[:500]
        super().__init__(f'GitHub API returned HTTP {status} for {path}' + (': ' + message if message else ''))


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlparse(newurl).netloc != 'api.github.com':
            redirected.remove_header('Authorization')
        return redirected


class GitHub:
    """Small injectable API boundary shared with preparation and publication."""
    def __init__(self, repository, token=None):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Invalid repository')
        self.repository = repository
        self.token = token if token is not None else os.environ.get('GITHUB_TOKEN', os.environ.get('GH_TOKEN', ''))
        self.opener = urllib.request.build_opener(_SafeRedirect())
        self._trees = {}
        self._blobs = {}

    def request(self, method, path, data=None, raw=False):
        if '://' in path or path.startswith('//') or '\\' in path:
            raise ValueError('Only GitHub API paths are accepted')
        path = path if path.startswith('/') else f'/repos/{self.repository}/' + path
        headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                   'User-Agent': 'vm-lab-thematic-review'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        payload = None if data is None else json.dumps(data, ensure_ascii=False).encode('utf-8')
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request('https://api.github.com' + path, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=90) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            try:
                diagnostic = json.loads(error.read(4096))
                message = diagnostic.get('message', '') if isinstance(diagnostic, dict) else ''
            except (ValueError, OSError):
                message = ''
            raise APIError(error.code, path, message) from None
        return body if raw else (json.loads(body) if body else None)

    def get(self, path):
        return self.request('GET', path)

    def pages(self, path, key=None):
        parsed = urllib.parse.urlsplit(path)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        query['per_page'] = '100'
        rows, previous = [], None
        page = 1
        while True:
            query['page'] = str(page)
            value = self.get(urllib.parse.urlunsplit(('', '', parsed.path, urllib.parse.urlencode(query), '')))
            if key and (not isinstance(value, dict) or key not in value):
                raise ValueError('Missing paginated result field: ' + path)
            batch = value[key] if key else value
            if not isinstance(batch, list):
                raise ValueError('Unexpected paginated response: ' + path)
            fingerprint = digest(batch)
            if batch and fingerprint == previous:
                raise ValueError('Pagination did not advance: ' + path)
            rows.extend(batch)
            if len(batch) < 100:
                return rows
            previous = fingerprint
            page += 1

    def blob(self, sha):
        if not SHA.fullmatch(sha):
            raise ValueError('Invalid blob SHA')
        if sha not in self._blobs:
            value = self.get('git/blobs/' + sha)
            if value.get('encoding') != 'base64':
                raise ValueError('Unexpected blob encoding')
            self._blobs[sha] = base64.b64decode(value['content']).decode('utf-8')
        return self._blobs[sha]

    def tree(self, sha):
        if not SHA.fullmatch(sha):
            raise ValueError('Invalid tree ref')
        if sha not in self._trees:
            value = self.get('git/trees/' + sha + '?recursive=1')
            if value.get('truncated'):
                raise ValueError('GitHub tree is truncated; complete corpus coverage is unavailable')
            self._trees[sha] = value['tree']
        return self._trees[sha]


def load_state(api):
    try:
        value = api.get('contents/' + STATE_PATH + '?ref=' + encoded(REPORT_BRANCH))
    except APIError as error:
        if error.status == 404:
            return None
        raise
    raw = base64.b64decode(value['content']).decode('utf-8') if value.get('encoding') == 'base64' else api.blob(value['sha'])
    result = json.loads(raw)
    if result.get('schema') == 'vm-lab-split-utf8-v1':
        # Imported only after this module's API boundary is initialized: the
        # publisher shares GitHub but owns the one exact storage format.
        from copilot_thematic_publish import restore_stored
        result = json.loads(restore_stored(api, STATE_PATH, raw))
    if result.get('schema') != 'vm-lab-thematic-monitor-v1' or result.get('repository') != api.repository:
        raise ValueError('Monitor state identity mismatch')
    return result


def signal_event(api, run_id, include_timestamp=False):
    """Download an untrusted signal as JSON; no extraction or code execution."""
    run = api.get('actions/runs/' + str(int(run_id)))
    if (run.get('repository', {}).get('full_name') != api.repository or
            run.get('path', '').split('@', 1)[0] != SIGNAL_PATH or
            run.get('event') not in {'push', 'pull_request', 'pull_request_review', 'pull_request_review_comment'}):
        raise ValueError('Unrecognized signal workflow identity')
    artifacts = api.pages(f'actions/runs/{int(run_id)}/artifacts', key='artifacts')
    found = [x for x in artifacts if x['name'] == SIGNAL_ARTIFACT and not x.get('expired')]
    if len(found) != 1:
        raise ValueError('Signal event artifact missing or ambiguous')
    raw = api.request('GET', f"actions/artifacts/{int(found[0]['id'])}/zip", raw=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if set(archive.namelist()) != {'EVENT.json', 'META.json'} or sum(x.file_size for x in archive.infolist()) > 50_000_000:
            raise ValueError('Invalid signal archive')
        metadata = json.loads(archive.read('META.json'))
        event = json.loads(archive.read('EVENT.json'))
    if (metadata.get('repository') != api.repository or str(metadata.get('run_id')) != str(run_id)
            or metadata.get('event_name') != run['event']
            or run['head_sha'] not in {metadata.get('source_sha'), metadata.get('execution_sha')}
            or event.get('repository', {}).get('full_name') != api.repository):
        raise ValueError('Signal event metadata mismatch')
    if 'pull_request' in event and metadata.get('source_sha') != event['pull_request']['head']['sha']:
        raise ValueError('Signal PR head identity mismatch')
    if include_timestamp:
        return run['event'], event, run.get('created_at')
    return run['event'], event


def own_path(path):
    return (path.startswith(REPORT_PREFIX) or path in IMPLEMENTATION_PATHS or
            path.startswith(('infra/copilot_thematic', 'tests/test_copilot_thematic')) and path.endswith('.py'))


def own_branch(branch):
    return branch in {REPORT_BRANCH, IMPLEMENTATION_BRANCH, IMPLEMENTATION_REPAIR_BRANCH, 'infra/copilot-repo-native-review-20261121'} or branch.startswith('copilot/thematic-')


def own_comment(comment):
    return (comment.get('user', {}).get('login') == 'github-actions[bot]' and
            (comment.get('body') or '').startswith(('<!-- vm-lab:copilot-thematic-report -->',
                                                    '<!-- vm-lab-thematic-report:')))


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def restore_recovery_batches(saved, target):
    """An absent/expired/partial artifact must not hide durable branch output."""
    saved, target = Path(saved), Path(target)
    if not all((saved / name).is_file() for name in ('EVENTS.json', 'CONTEXT.json')):
        return {'status': 'ARTIFACT_UNAVAILABLE_USING_ARCHIVED_DATA', 'copied_files': 0}
    attempt = json.loads((target / 'ATTEMPT.json').read_text())
    for name, field in [('EVENTS.json', 'events_sha256'), ('CONTEXT.json', 'context_sha256')]:
        if hashlib.sha256((saved / name).read_bytes()).hexdigest() != attempt[field]:
            raise ValueError('Recovery input identity mismatch: ' + name)
    copied = 0
    for path in saved.rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlink in recovery artifact')
        name = path.relative_to(saved).as_posix()
        if path.is_file() and re.fullmatch(r'batches/[0-9]{4,6}/(RAW_RESPONSE.txt|RESPONSE.json|RECEIPT.json|PROMPT.txt|STDERR.txt)', name):
            dest = target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copyfile(path, dest)
                copied += 1
    return {'status': 'VERIFIED_SAVED_DATA', 'copied_files': copied}


def collect(api, event_name, event, source_sha, state=None, now=None, start_at=None):
    if not SHA.fullmatch(source_sha):
        raise ValueError('Expected trusted main source SHA')
    now = now or utc_now()
    initial = state is None
    state = copy.deepcopy(state or {'schema': 'vm-lab-thematic-monitor-v1', 'repository': api.repository,
        'started_at': start_at or now, 'observed_at': start_at or now, 'source_versions': {}, 'branch_heads': {}})
    if state.get('repository') != api.repository:
        raise ValueError('Monitor repository mismatch')
    versions = state.setdefault('source_versions', {})
    revision_versions = state.setdefault('source_revision_versions', {})
    current = state.setdefault('source_current', {})
    changes, omissions, ignored, refs = {}, [], [], {source_sha: 'main'}
    processed_commits, processed_discussions = set(), set()
    implementation_discussions = set(IMPLEMENTATION_ISSUES)
    since = state['observed_at']
    # Inclusive overlap handles timestamp rounding/API propagation; hashes dedup it.
    since = (datetime.fromisoformat(since.replace('Z', '+00:00')) - timedelta(minutes=2)).isoformat().replace('+00:00', 'Z')

    def add(identifier, kind, text, revision, url, baseline=False, **extra):
        item = {'id': identifier, 'kind': kind, 'text': text or '', 'revision': str(revision or ''), 'url': url, **extra}
        # Delivery route, timestamp and added/modified wording do not constitute
        # new evidence. Deletion, changed status and different content do.
        content = {k: v for k, v in item.items() if k not in {'revision', 'url', 'operation', 'previous_path'}}
        content['deleted'] = item.get('operation') in {'removed', 'deleted'}
        fingerprint = digest(content)
        prior = versions.get(identifier, [])
        prior = [prior] if isinstance(prior, str) else prior
        version_key = digest([str(revision or ''), fingerprint])
        seen = revision_versions.setdefault(identifier, [])
        if version_key in seen:
            return
        # Immutable document commits distinguish real A -> B -> A changes from
        # repeated delivery of the same commit. Discussion revisions are ordered
        # timestamps; a late old event cannot replace a newer live snapshot.
        latest = current.get(identifier)
        if kind != 'document' and latest:
            if fingerprint == latest['content_sha256']:
                latest['revision'] = max(str(revision or ''), latest['revision'])
                return
            if str(revision or '') < latest['revision'] and fingerprint in prior:
                return
        seen.append(version_key)
        versions[identifier] = prior + ([fingerprint] if fingerprint not in prior else [])
        if kind != 'document' and (not latest or str(revision or '') >= latest['revision']):
            current[identifier] = {'content_sha256': fingerprint, 'revision': str(revision or '')}
        item['content_sha256'] = fingerprint
        item['version_sha256'] = version_key
        if not baseline:
            changes[identifier + ':' + version_key] = item

    def add_file(file, revision):
        path, status = file['filename'], file.get('status', 'modified')
        if own_path(path):
            reason = 'generated_report' if path.startswith(REPORT_PREFIX) else 'thematic_automation_implementation'
            ignored.append({'kind': reason, 'reason': reason, 'path': path, 'revision': revision})
            return
        extra = {'path': path, 'operation': status}
        if file.get('previous_filename'):
            extra['previous_path'] = file['previous_filename']
        blob_sha = file.get('sha')
        if status == 'removed' and not blob_sha:
            try:
                parent = api.get('git/commits/' + revision).get('parents', [])
                if parent:
                    blob_sha = next((x['sha'] for x in api.tree(parent[0]['sha'])
                                     if x['path'] == path and x['type'] == 'blob'), None)
            except APIError as error:
                if error.status != 404:
                    raise
        extra['blob_sha'] = blob_sha
        reason = None
        if Path(path).suffix.lower() in BINARY_EXTENSIONS:
            reason = 'binary_or_raw_numeric_artifact'
        elif not blob_sha or not SHA.fullmatch(blob_sha):
            reason = 'missing_blob_identity'
        text = ''
        if not reason:
            try:
                text = api.blob(blob_sha)
                # Long theory/registry/code documents remain whole. Only raw
                # tabular exports are metadata-only at this threshold; corpus
                # preparation splits ordinary long text into visible batches.
                if Path(path).suffix.lower() in {'.csv', '.tsv', '.jsonl', '.ndjson'} and len(text.encode()) > MAX_RAW_TEXT_BYTES:
                    extra['size_bytes'] = len(text.encode())
                    reason, text = 'large_raw_table_metadata_only', ''
                elif Path(path).suffix.lower() == '.json' and len(text.encode()) > MAX_RAW_TEXT_BYTES:
                    try:
                        value = json.loads(text)
                        if isinstance(value, list) and numeric_array(value):
                            extra['size_bytes'] = len(text.encode())
                            reason, text = 'large_raw_numeric_array_metadata_only', ''
                    except (ValueError, RecursionError):
                        pass  # Unrecognized text is passed whole, never silently dropped.
            except UnicodeDecodeError:
                reason = 'not_utf8_text'
        if reason:
            omissions.append({'path': path, 'revision': revision, 'blob_sha': blob_sha, 'reason': reason})
            extra['content_read'] = False
            extra['omission_reason'] = reason
        else:
            extra['content_read'] = True
        url = (f'https://github.com/{api.repository}/commit/{revision}' if status == 'removed' else
               f'https://github.com/{api.repository}/blob/{revision}/{urllib.parse.quote(path)}')
        add('file:' + path, 'document', text, revision, url, **extra)

    def commit(sha):
        if sha in processed_commits:
            return
        if not SHA.fullmatch(sha):
            raise ValueError('Invalid changed commit SHA')
        processed_commits.add(sha)
        for file in api.pages('commits/' + sha, key='files'):
            add_file(file, sha)

    def commits_between(before, after):
        if not after or after == '0' * 40:
            return
        refs.setdefault(after, 'changed ' + after[:12])
        if before and before != '0' * 40:
            refs.setdefault(before, 'before ' + before[:12])

        def final_tree_changes():
            old = {x['path']: x for x in api.tree(before) if x['type'] == 'blob'}
            new = {x['path']: x for x in api.tree(after) if x['type'] == 'blob'}
            for path in sorted(set(old) | set(new)):
                if old.get(path, {}).get('sha') != new.get(path, {}).get('sha'):
                    item = new.get(path) or old[path]
                    add_file({'filename': path, 'sha': item['sha'],
                              'status': 'removed' if path not in new else
                                        'added' if path not in old else 'modified'}, after)

        if before and before != '0' * 40 and before != after:
            try:
                path = 'compare/' + encoded(before) + '...' + encoded(after)
                comparison = api.get(path + '?per_page=100&page=1')
                if comparison.get('status') not in {'ahead', 'behind', 'diverged', 'identical'}:
                    raise ValueError('Unknown GitHub comparison status')
                values = comparison['commits']
                if comparison.get('total_commits', len(values)) > len(values):
                    values = api.pages(path, key='commits')
                if comparison['status'] in {'behind', 'diverged'}:
                    final_tree_changes()
            except APIError as error:
                if error.status not in {404, 409, 422}:
                    raise
                # A force push can destroy the common history. Exact final trees
                # still provide additions/modifications/deletions; disclose that
                # unavailable intermediate versions were not recovered.
                final_tree_changes()
                omissions.append({'before': before, 'revision': after, 'reason': 'unavailable_intermediate_commit_history'})
                return
        else:
            values = [{'sha': after}]
        for value in reversed(values):
            commit(value['sha'])

    def body(item, kind, identifier, operation=None, baseline=False, event_revision=None, parent_number=None):
        if own_comment(item):
            ignored.append({'kind': 'generated_comment', 'id': identifier})
            return
        text = item.get('body') or ''
        if kind in {'issue', 'pull_request'}:
            text = (item.get('title') or '') + '\n\n' + text
        # Review bodies have no reliable updated_at in REST. A live review
        # snapshot is versioned by observation time; a delivered review uses its
        # signal run's creation time, preserving ordering when it arrives late.
        revision = (event_revision or now) if kind == 'pull_request_review' else (
            item.get('updated_at') or item.get('submitted_at') or item.get('created_at'))
        add(identifier, kind, text, revision,
            item.get('html_url') or '', state=item.get('state'), operation=operation or 'snapshot', baseline=baseline, number=item.get('number') or parent_number)

    def discussion(issue, force=False):
        number = int(issue['number'])
        if number in processed_discussions:
            return
        processed_discussions.add(number)
        if number in IMPLEMENTATION_ISSUES:
            ignored.append({'kind': 'issue', 'number': number, 'reason': 'thematic_automation_implementation'})
            return
        pr = None
        if 'pull_request' in issue:
            pr = api.get('pulls/' + str(number))
            if pr['head']['ref'] == IMPLEMENTATION_BRANCH:
                implementation_discussions.add(number)
            if own_branch(pr['head']['ref']):
                ignored.append({'kind': 'generated_report_pr', 'number': number})
                return
            refs[pr['head']['sha']] = 'PR #' + str(number)
        body(pr or issue, 'pull_request' if pr else 'issue', ('pr:' if pr else 'issue:') + str(number))
        for comment in api.pages(f'issues/{number}/comments'):
            if force or (comment.get('updated_at') or comment.get('created_at') or '') >= since:
                body(comment, 'issue_comment', 'issue-comment:' + str(comment['id']))
        if pr:
            for review in api.pages(f'pulls/{number}/reviews'):
                # submitted_at does not advance when a review is dismissed/edited.
                body(review, 'pull_request_review', 'review:' + str(review['id']))
            for comment in api.pages(f'pulls/{number}/comments'):
                if force or (comment.get('updated_at') or comment.get('created_at') or '') >= since:
                    body(comment, 'pull_request_review_comment', 'review-comment:' + str(comment['id']))

    # The triggering event is evidence even if a newer snapshot was reconciled.
    event_revision = now
    if event_name == 'workflow_run':
        event_name, event, event_revision = signal_event(api, event['workflow_run']['id'], include_timestamp=True)
    if event_name == 'push' and not own_branch(event.get('ref', '').removeprefix('refs/heads/')):
        if SHA.fullmatch(event.get('after', '')) and event.get('after') != '0' * 40:
            refs[event['after']] = event.get('ref', 'push').removeprefix('refs/heads/')
        commits_between(event.get('before'), event.get('after'))
        for value in event.get('commits', []):
            commit(value['id'])
    elif event_name in {'issues', 'issue_comment'}:
        issue = event['issue']
        generated_pr = False
        implementation = int(issue['number']) in IMPLEMENTATION_ISSUES
        if 'pull_request' in issue:
            branch = api.get('pulls/' + str(int(issue['number'])))['head']['ref']
            generated_pr = own_branch(branch)
            implementation = implementation or branch == IMPLEMENTATION_BRANCH
        if implementation:
            implementation_discussions.add(int(issue['number']))
            ignored.append({'kind': 'issue', 'number': issue['number'], 'reason': 'thematic_automation_implementation'})
        # A deleted issue cannot be read back, but its delivered body is retained.
        if not generated_pr and not implementation:
            body(issue, 'pull_request' if 'pull_request' in issue else 'issue',
                 ('pr:' if 'pull_request' in issue else 'issue:') + str(issue['number']),
                 'deleted' if event.get('action') == 'deleted' and event_name == 'issues' else None)
        if event_name == 'issue_comment' and not implementation:
            body(event['comment'], 'issue_comment', 'issue-comment:' + str(event['comment']['id']),
                 'deleted' if event.get('action') == 'deleted' else None,
                 parent_number=event.get('issue', {}).get('number'))
    elif event_name in {'pull_request', 'pull_request_review', 'pull_request_review_comment'}:
        pr = event['pull_request']
        if pr['head']['ref'] == IMPLEMENTATION_BRANCH:
            implementation_discussions.add(int(pr['number']))
            ignored.append({'kind': 'pull_request', 'number': pr['number'], 'reason': 'thematic_automation_implementation'})
        if not own_branch(pr['head']['ref']):
            refs[pr['head']['sha']] = 'PR #' + str(pr['number'])
            body(pr, 'pull_request', 'pr:' + str(pr['number']))
            if event_name == 'pull_request' and event.get('action') in {'opened', 'reopened', 'synchronize'}:
                commits_between(event.get('before') or pr['base']['sha'], pr['head']['sha'])
            elif event_name == 'pull_request_review':
                body(event['review'], 'pull_request_review', 'review:' + str(event['review']['id']), event_revision=event_revision)
            elif event_name == 'pull_request_review_comment':
                body(event['comment'], 'pull_request_review_comment', 'review-comment:' + str(event['comment']['id']),
                     'deleted' if event.get('action') == 'deleted' else None)

    # Durable branch changes: all branches, no title/path/keyword science gate.
    branches = api.pages('branches')
    current_heads = {}
    for branch in branches:
        name, head = branch['name'], branch['commit']['sha']
        if own_branch(name):
            continue
        current_heads[name] = head
        previous = state.get('branch_heads', {}).get(name)
        if previous and previous != head:
            refs[head] = name
            commits_between(previous, head)
        elif not initial and previous is None:
            refs[head] = name
            for value in api.pages('commits?sha=' + encoded(head) + '&since=' + encoded(since)):
                commit(value['sha'])
            commit(head)
    state['branch_heads'] = current_heads
    # Include all active PR snapshots in the corpus, even when their text did not change.
    pulls = api.pages('pulls?state=open')
    for pr in pulls:
        if pr['head']['ref'] == IMPLEMENTATION_BRANCH:
            implementation_discussions.add(int(pr['number']))
        if not own_branch(pr['head']['ref']):
            refs[pr['head']['sha']] = 'PR #' + str(pr['number'])
    issues = api.pages('issues?state=all&since=' + encoded(since))
    for issue in issues:
        if (issue.get('updated_at') or '') >= state['started_at']:
            discussion(issue)
    # Review edits are not guaranteed to update the parent issue timestamp.
    review_pulls = api.pages('pulls?state=all') if initial or event_name in {'schedule', 'workflow_dispatch'} else pulls
    for pr in review_pulls:
        if pr['head']['ref'] == IMPLEMENTATION_BRANCH:
            implementation_discussions.add(int(pr['number']))
        if not own_branch(pr['head']['ref']):
            for review in api.pages(f"pulls/{int(pr['number'])}/reviews"):
                body(review, 'pull_request_review', 'review:' + str(review['id']),
                     baseline=initial and (review.get('submitted_at') or '') < state['started_at'])
    for endpoint, kind, prefix in [('issues/comments', 'issue_comment', 'issue-comment:'),
                                   ('pulls/comments', 'pull_request_review_comment', 'review-comment:')]:
        for comment in api.pages(endpoint + '?since=' + encoded(since)):
            if (comment.get('updated_at') or comment.get('created_at') or '') < state['started_at']:
                continue
            parent = (comment.get('issue_url') or comment.get('pull_request_url') or '').rstrip('/').rsplit('/', 1)[-1]
            if parent.isdigit() and int(parent) in implementation_discussions:
                ignored.append({'kind': kind, 'id': comment['id'], 'reason': 'thematic_automation_implementation'})
                continue
            # Generated publisher comments have a checked author+marker. Other
            # bot comments remain evidence; never exclude all bot activity.
            body(comment, kind, prefix + str(comment['id']))
    state['observed_at'] = max(now, state.get('observed_at', now))
    material = sorted(changes.values(), key=lambda x: (x['id'], x['version_sha256']))
    package_id = digest([(x['id'], x['version_sha256']) for x in material]) if material else ''
    return {'schema': 'vm-lab-thematic-events-v1', 'repository': api.repository,
        'source_sha': source_sha, 'package_id': package_id, 'event_name': event_name,
        'observed_at': now, 'changes': material,
        'source_refs': [{'sha': sha, 'label': label} for sha, label in sorted(refs.items())],
        'coverage': {'initial_baseline': initial, 'started_at': state['started_at'],
            'reconciled_since': since, 'branches': len(current_heads), 'active_prs': len(pulls),
            'commits': len(processed_commits), 'changed_versions': len(material),
            'omitted_contents': omissions, 'ignored_generated_outputs': ignored,
            'complete_content': not omissions,
            'limitation': 'Reconciliation observes persistent GitHub versions; undelivered overwritten/deleted intermediate bodies cannot be reconstructed.'},
        'next_state': state}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['collect', 'recover-batches'])
    parser.add_argument('--output', type=Path, default=Path('thematic-output'))
    parser.add_argument('--state', type=Path)
    parser.add_argument('--saved', type=Path, default=Path('thematic-recovery'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.command == 'recover-batches':
        print(json.dumps(restore_recovery_batches(args.saved, args.output)))
        return
    try:
        api = GitHub(os.environ.get('GITHUB_REPOSITORY', REPOSITORY))
        state = json.loads(args.state.read_text()) if args.state else load_state(api)
        event_path = os.environ.get('GITHUB_EVENT_PATH')
        event = json.loads(Path(event_path).read_text()) if event_path else {}
        result = collect(api, os.environ.get('GITHUB_EVENT_NAME', 'schedule'), event,
                         os.environ['GITHUB_SHA'], state=state,
                         start_at=os.environ.get('THEMATIC_START_AT'))
        from copilot_address_status import route_changes
        result = route_changes(result)
        dump(args.output / 'EVENTS.json', result)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                output.write('package_id=' + result['package_id'] + '\n')
        print(f"Collected {len(result['changes'])} changed versions; {len(result['coverage']['omitted_contents'])} contents explicitly unavailable.")
    except Exception as error:
        dump(args.output / 'COLLECTION_FAILURE.json', {'schema': 'vm-lab-thematic-collection-failure-v1',
             'error': str(error), 'scientific_status_changed': False})
        raise


if __name__ == '__main__':
    main()
