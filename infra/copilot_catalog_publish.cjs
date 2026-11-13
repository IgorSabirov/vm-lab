// Data-only publisher. Generated responses cannot choose paths or commands.
const fs = require('node:fs');
const crypto = require('node:crypto');
const {ensurePullRequest} = require('./copilot_publish.cjs');
const FILES = ['REGISTRY.json','INDEX.md','COVERAGE.json','CONTEXT.json','COPILOT_SELECTION.json','RAW_RESPONSE.txt','RECEIPT.json'];
const digest = s => crypto.createHash('sha256').update(s).digest('hex');
function validate(files, base) {
  if (!/^[a-f0-9]{40}$/.test(base) || Object.keys(files).sort().join() !== [...FILES].sort().join())
    throw Error('Fixed file set and base required');
  const r = JSON.parse(files['RECEIPT.json']);
  const c = JSON.parse(files['CONTEXT.json']);
  const d = JSON.parse(files['REGISTRY.json']);
  const selection = JSON.parse(files['COPILOT_SELECTION.json']);
  if (r.source_sha !== base || c.source_sha !== base || d.source_sha !== base ||
      r.task_id !== 'now-code-catalog-v1' || r.issue !== 41 || r.status !== 'CATALOG_PROPOSAL_GENERATED' ||
      r.returncode !== 0 || r.timed_out || r.scientific_status_changed !== false ||
      r.upstream_execution_performed !== false || d.complete_github_coverage !== false)
    throw Error('Catalog identity or completion mismatch');
  if (Buffer.byteLength(JSON.stringify(files)) > 4000000) throw Error('Oversized catalog');
  for (const name of FILES.filter(n=>n!=='RECEIPT.json'))
    if (digest(files[name]) !== r.files[name]) throw Error('Digest mismatch: '+name);
  if (/(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+/.test(JSON.stringify(files))) throw Error('Credential-shaped output');
  const ids=new Set();
  if (!Array.isArray(d.entries) || d.entries.length<1 || d.entries.length>1000) throw Error('Invalid catalog size');
  for(const row of d.entries) {
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(row.repository) ||
        row.id !== row.repository.toLowerCase() || row.url !== 'https://github.com/'+row.repository ||
        ids.has(row.id) || row.execution_performed !== false || row.scientific_acceptance !== false)
      throw Error('Invalid catalog entry');
    ids.add(row.id);
  }
  if (!Array.isArray(selection.shortlist) || selection.shortlist.some(x=>!ids.has(x.id)))
    throw Error('Invented selection');
  if(r.unique_links!==d.entries.length || r.selected_links!==selection.shortlist.length)
    throw Error('Count mismatch');
  return r;
}
async function main({github,context,core}) {
  const base=process.env.EXPECTED_SHA;
  const files=Object.fromEntries(FILES.map(n=>[n,fs.readFileSync('proposal/'+n,'utf8')]));
  const receipt=validate(files,base);
  const run='https://github.com/'+context.repo.owner+'/'+context.repo.repo+'/actions/runs/'+context.runId;
  const pr=await ensurePullRequest({github,...context.repo,base,
    branch:'copilot/catalog-now-code-v1-'+context.runId,
    files:FILES.map(name=>({path:'infra/external/catalog/'+name,mode:'100644',type:'blob',content:files[name]})),
    title:'[Copilot] NOW: public scientific-code link catalog',
    body:'Related #41. '+receipt.unique_links+' unique links; '+receipt.selected_links+' navigation suggestions by native Copilot. All collected links retained. No upstream execution or scientific acceptance.\n\nBase: '+base+'\nRun: '+run+'\n\nRead INDEX.md and COVERAGE.json; metadata is not a verified physical interface.'});
  core.info(pr.html_url);
  await core.summary.addLink('Catalog PR',pr.html_url).write();
}
module.exports={FILES,validate,main};
