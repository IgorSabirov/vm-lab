// Trusted publisher: model output remains data; write paths are fixed here.
const fs = require('node:fs');
const crypto = require('node:crypto');
const digest = text => crypto.createHash('sha256').update(text).digest('hex');
const PREFIX = 'infra/copilot/reports/';

function validateProposal(d, base) {
  if (!/^[a-f0-9]{40}$/.test(base) || d.source_sha !== base || d.receipt?.source_sha !== base)
    throw Error('Source identity mismatch');
  if (d.receipt.status !== 'NATIVE_REPORT_GENERATED' || d.receipt.returncode !== 0 || d.receipt.timed_out)
    throw Error('No successful generation');
  if (typeof d.report !== 'string' || Buffer.byteLength(d.report) < 500 || Buffer.byteLength(d.report) > 35000)
    throw Error('Invalid report');
  if (/(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+/.test(JSON.stringify(d)))
    throw Error('Credential-shaped output');
  if (digest(d.report) !== d.receipt.report_sha256) throw Error('Report digest mismatch');
}

async function ensurePullRequest({github, owner, repo, base, branch, files, title, body}) {
  const git = github.rest.git;
  const parent = await git.getCommit({owner, repo, commit_sha: base});
  const tree = await git.createTree({owner, repo, base_tree: parent.data.tree.sha, tree: files});
  let ref;
  try { ref = await git.getRef({owner, repo, ref: `heads/${branch}`}); }
  catch (e) { if (e.status !== 404) throw e; }
  if (ref) {
    const existing = await git.getCommit({owner, repo, commit_sha: ref.data.object.sha});
    if (existing.data.tree.sha !== tree.data.sha || existing.data.parents.length !== 1 || existing.data.parents[0].sha !== base)
      throw Error('Existing branch changed; refusing to overwrite it');
  } else {
    const commit = await git.createCommit({owner, repo, message: title, tree: tree.data.sha, parents: [base]});
    await git.createRef({owner, repo, ref: `refs/heads/${branch}`, sha: commit.data.sha});
  }
  const prs = await github.rest.pulls.list({owner, repo, head: `${owner}:${branch}`, state: 'all', per_page: 100});
  if (prs.data.length > 1) throw Error('Ambiguous publication');
  if (prs.data.length === 1) return prs.data[0];
  return (await github.rest.pulls.create({owner, repo, head: branch, base: 'main', draft: true, title, body})).data;
}

async function main({github, context, core, mode}) {
  const base = process.env.EXPECTED_SHA;
  if (!/^[a-f0-9]{40}$/.test(base)) throw Error('Invalid publication base');
  let d, files, title, branch, description;
  if (mode === 'saved') {
    d = {report: fs.readFileSync(PREFIX + 'FIRST_PILOT.md', 'utf8'),
         receipt: JSON.parse(fs.readFileSync(PREFIX + 'FIRST_PILOT_RECEIPT.json', 'utf8'))};
    d.source_sha = d.receipt.source_sha;
    validateProposal(d, d.source_sha);
    const receipt = {schema: 'vm-lab-native-publication-check-v1', source_sha: base,
      publication_run_id: String(context.runId), generation_run_id: d.receipt.run_id,
      generation_source_sha: d.source_sha, report_sha256: digest(d.report),
      reused_report: PREFIX + 'FIRST_PILOT.md', new_model_invocations: 0,
      scientific_status_changed: false, publication_result: 'SEE_ASSOCIATED_PULL_REQUEST'};
    files = [{path: PREFIX + 'PUBLICATION_CHECK.json', mode: '100644', type: 'blob', content: JSON.stringify(receipt, null, 2) + '\n'}];
    title = '[Copilot] Verify Actions publication using the saved native report';
    branch = `copilot/publication-check-${context.runId}`;
    description = 'Reuse the existing Copilot report and verify its digest. No new model request. This PR records an Actions publication check, not a scientific result. The PR author and linked run establish who published it.';
  } else if (mode === 'generated') {
    const raw = fs.readFileSync('proposal/native-proposal.json', 'utf8');
    if (Buffer.byteLength(raw) > 50000) throw Error('Oversized proposal');
    d = JSON.parse(raw);
    validateProposal(d, base);
    files = [
      {path: PREFIX + 'FIRST_PILOT.md', mode: '100644', type: 'blob', content: d.report},
      {path: PREFIX + 'FIRST_PILOT_RECEIPT.json', mode: '100644', type: 'blob', content: JSON.stringify(d.receipt, null, 2) + '\n'}];
    title = '[Copilot] IsingCauset: first native report and existing registry links';
    branch = `copilot/native-pilot-${context.runId}`;
    description = 'Copilot authored the report from pinned source data via native Auto. Trusted Actions gathered evidence, ran checks and published these fixed report files. No model execution tools, registry edits, science acceptance or VM use.';
  } else throw Error('Unknown publication mode');
  const run = `https://github.com/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
  const pr = await ensurePullRequest({github, ...context.repo, base, branch, files, title,
    body: `Related #16. ${description}\n\nBase: ${base}\nRun: ${run}\n\nPublication is not scientific acceptance. No merge is performed by this workflow.`});
  core.info(pr.html_url);
  await core.summary.addLink('Copilot publication PR', pr.html_url).write();
}

module.exports = {validateProposal, ensurePullRequest, main};
