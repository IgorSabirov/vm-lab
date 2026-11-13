const {test}=require('node:test');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const {FILES,validate}=require('./copilot_catalog_publish.cjs');
const digest=s=>crypto.createHash('sha256').update(s).digest('hex');
function fixture(){
 const base='a'.repeat(40), files={};
 for(const n of FILES)files[n]='{}';
 files['CONTEXT.json']=JSON.stringify({source_sha:base});
 files['REGISTRY.json']=JSON.stringify({source_sha:base,complete_github_coverage:false,
 entries:[{id:'org/repo',repository:'Org/Repo',url:'https://github.com/Org/Repo',execution_performed:false,scientific_acceptance:false}]});
 files['COPILOT_SELECTION.json']=JSON.stringify({shortlist:[{id:'org/repo'}]});
 const r={source_sha:base,task_id:'now-code-catalog-v1',issue:41,status:'CATALOG_PROPOSAL_GENERATED',
 returncode:0,timed_out:false,scientific_status_changed:false,upstream_execution_performed:false,unique_links:1,selected_links:1,
 files:Object.fromEntries(FILES.filter(n=>n!=='RECEIPT.json').map(n=>[n,digest(files[n])]))};
 files['RECEIPT.json']=JSON.stringify(r); return {base,files};
}
test('valid fixed publication and digest tampering',()=>{
 const {base,files}=fixture();assert.equal(validate(files,base).unique_links,1);
 files['INDEX.md']='changed';assert.throws(()=>validate(files,base),/Digest/);
});
test('wrong base, extra path and scientific promotion rejected',()=>{
 for(const change of ['base','path','science']){
  const {base,files}=fixture();
  if(change==='path')files['../../run.py']='print(1)';
  if(change==='science'){const r=JSON.parse(files['RECEIPT.json']);r.scientific_status_changed=true;files['RECEIPT.json']=JSON.stringify(r);}
  assert.throws(()=>validate(files,change==='base'?'b'.repeat(40):base));
 }
});
