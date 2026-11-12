/* Deterministic advisory only. Untrusted Issue text is data, never code. */
module.exports = async ({github, context, core}) => {
  const {owner,repo}=context.repo;
  const issue=context.payload.issue;
  if (!issue || issue.pull_request) return;
  const {data:file}=await github.rest.repos.getContent({owner,repo,path:'analysis/REGISTRY_LINKS/INDEX.json',ref:context.payload.repository.default_branch});
  const graph=JSON.parse(Buffer.from(file.content,'base64').toString('utf8'));
  const text=(issue.title+'\n'+(issue.body||'')).slice(0,100000);
  const references=[...new Set(text.match(/\b(?:result:R\d{3}|construct:C\d{3}|question:U\d{3}|link:L\d{2}|premise:[A-G]\d{2}|obligation:N\d{2}|decision:D\d{3})\b/g)||[])];
  const byKey=new Map(graph.nodes.map(n=>[n.key,n]));
  const marker='<!-- vm-lab:registry-advisor -->';
  const lines=[marker,'**Автоматическая навигация по реестру.** Это не научная приёмка и не разрешение запуска.',''];
  for(const key of references.slice(0,50)) {
    const n=byKey.get(key);
    lines.push(n?`- [${key}](https://github.com/${owner}/${repo}/blob/${context.payload.repository.default_branch}/${n.path}${n.fragment?'#'+n.fragment:''})`: `- Неизвестный ID: \`${key}\`.`);
  }
  if(!references.length)lines.push('Укажите типизированные ID, например `question:U010`, `result:R129`, `obligation:N02`.');
  const related=graph.edges.filter(e=>references.includes(e.source)||references.includes(e.target));
  lines.push('',`Связей в графе для этих ID: ${related.length}. [Полная карта](https://github.com/${owner}/${repo}/blob/${context.payload.repository.default_branch}/analysis/REGISTRY_LINKS/INDEX.md).`);
  const comments=await github.paginate(github.rest.issues.listComments,{owner,repo,issue_number:issue.number,per_page:100});
  const old=comments.find(c=>c.user?.login==='github-actions[bot]'&&c.body.startsWith(marker));
  const body=lines.join('\n');
  if(old&&old.body!==body)await github.rest.issues.updateComment({owner,repo,comment_id:old.id,body});
  else if(!old)await github.rest.issues.createComment({owner,repo,issue_number:issue.number,body});
};
