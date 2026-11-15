const test = require('node:test');
const assert = require('node:assert/strict');
const report = require('../tools/ci_failure_report.cjs');
function fixture(head = 'abc') {
  const comments = [], sent = [], reads = [];
  const github = {rest: {actions: {listJobsForWorkflowRun: 'jobs'},
    pulls: {get: async () => ({data: {state: 'open', head: {sha: head}}})},
    issues: {listComments: 'comments', createComment: async args => {
      sent.push(args); comments.push({user: {login: 'github-actions[bot]'}, body: args.body});
    }}}, paginate: async kind => {reads.push(kind); return kind === 'jobs'
      ? [{conclusion: 'failure', name: 'infra', html_url: 'https://example.test/job'}] : comments;}};
  const summary = {addHeading() {return this;}, addRaw() {return this;}, async write() {}};
  return {github, core: {summary}, context: {repo: {owner: 'o', repo: 'r'},
    payload: {workflow_run: {id: 123, head_sha: 'abc', pull_requests: [{number: 4}]}}}, sent, reads};
}
test('same delivery publishes once with exact failed head', async () => {
  const f = fixture(); await report(f); await report(f);
  assert.equal(f.sent.length, 1); assert.match(f.sent[0].body, /at abc/);
});
test('old failure cannot label a newer PR head', async () => {
  const f = fixture('new'); await report(f);
  assert.equal(f.sent.length, 0); assert.ok(!f.reads.includes('comments'));
});
test('publication failure is not reported as success', async () => {
  const f = fixture(); f.github.rest.issues.createComment = async () => {throw new Error('403');};
  await assert.rejects(report(f), /403/);
});
