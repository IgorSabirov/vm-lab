const test = require('node:test');
const assert = require('node:assert/strict');
const {ensurePullRequest, validateProposal, validateReviewProposal} = require('./copilot_publish.cjs');

function fake() {
  const state = {branch: false, creates: 0, pr: null, rejectPR: true, changed: false};
  const github = {rest: {git: {
    getCommit: async ({commit_sha}) => ({data: commit_sha === 'base'
      ? {tree: {sha: 'original'}}
      : {tree: {sha: state.changed ? 'user-edit' : 'wanted'}, parents: [{sha: 'base'}]}}),
    createTree: async () => ({data: {sha: 'wanted'}}),
    getRef: async () => {if (!state.branch) throw Object.assign(Error('missing'), {status: 404}); return {data: {object: {sha: 'commit'}}};},
    createCommit: async () => ({data: {sha: 'commit'}}),
    createRef: async () => {state.branch = true; state.creates++;}
  }, pulls: {
    list: async () => ({data: state.pr ? [state.pr] : []}),
    create: async () => {if (state.rejectPR) throw Object.assign(Error('Actions PR denied'), {status: 403}); state.pr = {number: 1, html_url: 'https://github.com/example/repo/pull/1'}; return {data: state.pr};}
  }}};
  return {state, args: {github, owner: 'example', repo: 'repo', base: 'base', branch: 'fixed', files: [], title: 'report', body: 'evidence'}};
}

test('403 after committing is recoverable without a second commit or PR', async () => {
  const {state, args} = fake();
  await assert.rejects(ensurePullRequest(args), /Actions PR denied/);
  assert.equal(state.creates, 1);
  state.rejectPR = false;
  assert.equal((await ensurePullRequest(args)).number, 1);
  assert.equal((await ensurePullRequest(args)).number, 1);
  assert.equal(state.creates, 1);
});

test('recovery never overwrites a changed branch', async () => {
  const {state, args} = fake(); state.branch = true; state.changed = true;
  await assert.rejects(ensurePullRequest(args), /refusing to overwrite/);
  assert.equal(state.creates, 0); assert.equal(state.pr, null);
});

test('unverified or altered source output cannot be published', () => {
  assert.throws(() => validateProposal({source_sha: 'bad'}, 'a'.repeat(40)), /identity/);
  const base = 'a'.repeat(40);
  const d = {source_sha: base, report: 'x'.repeat(600), receipt: {source_sha: base,
    status: 'NATIVE_REPORT_GENERATED', returncode: 0, timed_out: false, report_sha256: 'bad'}};
  assert.throws(() => validateProposal(d, base), /digest/);
});

test('six-model publisher binds context and analysis and cannot promote links', () => {
  const digest = s => require('node:crypto').createHash('sha256').update(s).digest('hex');
  const base = 'a'.repeat(40), report = 'report '.repeat(100);
  const c = {source_sha: base, profile: {id: 'six-models-v1'}};
  const a = {summary: 'proposal'}, contextText = JSON.stringify(c), analysisText = JSON.stringify(a);
  const d = {source_sha: base, report, context: c, analysis: a,
    receipt: {source_sha: base, status: 'NATIVE_REPORT_GENERATED', returncode: 0,
      timed_out: false, task_id: 'six-models-v1', issue: 30, links_accepted: false,
      scientific_status_changed: false, report_sha256: digest(report),
      context_sha256: digest(contextText), analysis_sha256: digest(analysisText)}};
  validateReviewProposal(d, base, contextText, analysisText);
  assert.throws(() => validateReviewProposal(d, base, contextText+' ', analysisText), /mismatch/);
  d.receipt.links_accepted = true;
  assert.throws(() => validateReviewProposal(d, base, contextText, analysisText), /mismatch/);
  d.receipt.links_accepted = false;
  d.receipt.task_id = '../escape';
  assert.throws(() => validateReviewProposal(d, base, contextText, analysisText), /Unknown review task/);
});
