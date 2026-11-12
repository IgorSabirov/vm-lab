// Publish metadata only. No upstream file, PR body or artifact is executed.
import fs from 'node:fs';
const api='https://api.github.com';
const repo=process.env.GITHUB_REPOSITORY;
if(repo!=='IgorSabirov/vm-lab')throw Error('Unexpected target repository');
const token=process.env.GH_TOKEN;
const headers={'Authorization':`Bearer ${token}`,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'};
async function request(path,method='GET',body,allow404=false){
  const r=await fetch(`${api}/repos/${repo}${path}`,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});
  if(r.status===404&&allow404)return null;
  if(!r.ok)throw Error(`GitHub ${method} ${path}: ${r.status}`);
  return r.status===204?null:await r.json();
}
const report=JSON.parse(fs.readFileSync('external-evidence/UPSTREAM.json','utf8'));
if(report.errors.length)throw Error('Incomplete upstream scan');
if(!report.changes.length){console.log('No upstream changes');process.exit(0);}
const branch='automation/upstream-observations';
const path='infra/external/UPSTREAM_OBSERVATIONS.json';
const existing=await request(`/contents/${path}?ref=${branch}`,'GET',undefined,true);
if(existing){const old=JSON.parse(Buffer.from(existing.content,'base64').toString('utf8'));if(old.fingerprint===report.fingerprint){console.log('Identical observation already proposed');process.exit(0);}}
if(!await request(`/git/ref/heads/${branch}`,'GET',undefined,true)){
  const main=await request('/git/ref/heads/main');
  await request('/git/refs','POST',{ref:`refs/heads/${branch}`,sha:main.object.sha});
}
await request(`/contents/${path}`,'PUT',{message:'Record upstream changes for review; preserve accepted sources',branch,content:Buffer.from(JSON.stringify(report,null,2)+'\n').toString('base64'),...(existing?{sha:existing.sha}:{})});
const body=fs.readFileSync('external-evidence/UPSTREAM.md','utf8')+'\nСвязь: #7. Требуются ревизия семантики, лицензии и авторского контроля. Автоматическое слияние выключено.\n';
const prs=await request(`/pulls?state=open&head=IgorSabirov:${branch}&base=main`);
if(prs.length)await request(`/pulls/${prs[0].number}`,'PATCH',{body});
else await request('/pulls','POST',{head:branch,base:'main',title:'Внешние источники: обнаружены новые версии',body,draft:true});
console.log('Draft upstream review PR recorded');
