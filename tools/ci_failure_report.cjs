// Trusted workflow code only. Never execute failed PR code or its artifacts.
module.exports = async function report({github, context, core}) {
  const {owner, repo} = context.repo;
  const run = context.payload.workflow_run;
  const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun,
    {owner, repo, run_id: run.id, per_page: 100});
  const failed = jobs.filter(j => j.conclusion === 'failure')
    .map(j => `- [${j.name}](${j.html_url})`).join('\n');
  await core.summary.addHeading('Technical CI failure')
    .addRaw(failed + '\nNo scientific status changed.').write();
  for (const pr of run.pull_requests || []) {
    const live = (await github.rest.pulls.get({owner, repo, pull_number: pr.number})).data;
    if (live.state !== 'open' || live.head.sha !== run.head_sha) continue;
    const marker = `<!-- vm-lab:failed-run:${run.id} -->`;
    const comments = await github.paginate(github.rest.issues.listComments,
      {owner, repo, issue_number: pr.number, per_page: 100});
    if (comments.some(c => c.user?.login === 'github-actions[bot]' && (c.body || '').startsWith(marker))) continue;
    await github.rest.issues.createComment({owner, repo, issue_number: pr.number,
      body: `${marker}\nTechnical checks failed at ${run.head_sha}.\n${failed}\n\nThis does not refute a scientific result. [Execution](${run.html_url}).`});
  }
};
