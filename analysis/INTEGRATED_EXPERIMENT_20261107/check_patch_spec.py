"""Validate documentation/registry patch only; never import or run the model.

Use --repo-root for proposed/current docs, --baseline-docs for 8481ea2 docs,
and --source-root for an export/checkout of the declared ea49ebc code.
"""
import argparse
import ast
import hashlib
import json
import math
import re
from pathlib import Path


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--baseline-docs',type=Path,required=True)
    p.add_argument('--source-root',type=Path,required=True)
    args=p.parse_args(); root=args.repo_root; old=args.baseline_docs; src=args.source_root
    P='analysis/INTEGRATED_EXPERIMENT_20261107'
    A='analysis/FOUR_CANDIDATE_INTEGRATION_20261108'
    E='experiments/now_integrated_v1'
    R='analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json'
    load=lambda q:json.loads(q.read_text())
    spec=load(root/E/'preregistration/FOUR_CANDIDATE_AMENDMENT.json')
    fmap=load(root/P/'PATCH_FILE_MAP.json'); sources=load(root/P/'PATCH_SOURCE_INDEX.json')
    reg=load(root/R); before=load(old/R)
    cases=load(src/E/'preregistration/CASES.json'); prot=load(src/E/'preregistration/PROTOCOL.json')
    model=load(root/A/'DESIGN.json')
    ck={}
    ck['same_experiment_id']=spec['experiment_id']==prot['experiment']=='NOW_INTEGRATED_CONTINUATION_V1'
    ck['proposal_not_activated']=not spec['active'] and not spec['launch_authorized'] and spec['status']=='PROPOSED_PATCH_SPECIFICATION_NOT_IMPLEMENTED'
    ck['correct_source_base']=spec['target']['source_commit']==sources['engine_base']=='ea49ebce07495aa3a8dff6ed2c8cfa4ebfa0b2e8'
    verified=[]
    for f in sources['source_code_files']:
        b=(src/f['path']).read_bytes()
        verified.append(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==f['git_blob'] and hashlib.sha256(b).hexdigest()==f['sha256'])
    ck['all_35_pinned_source_blobs_verified']=len(verified)==35 and all(verified)
    ck['base_inventory']=len(cases['cases'])==123 and len(cases['contrasts'])==84 and len(prot['design_controls'])==11
    ck['base_task_count']=123+3*64+11==spec['preserved']['main_tasks']==326
    nids={f'N{i:02d}' for i in range(1,9)};xids={f'X{i:02d}' for i in range(1,17)}
    ck['eight_N_contracts_mapped']=set(x['id'] for x in spec['map_to_existing'])==nids
    ck['existing_X_only']=all(set(x['existing_comparisons'])<=xids for x in spec['map_to_existing'])
    cids={x['id'] for x in cases['cases']};kinds={x['id'] for x in cases['contrasts']};controls={x['id'] for x in prot['design_controls']}
    ck['all_case_contrast_control_refs_exist']=all(set(x['base_cases'])<=cids and set(x['base_contrasts'])<=kinds and set(x.get('base_controls',[]))<=controls for x in spec['map_to_existing'])
    ck['static_panel_8_valid_templates']=len(spec['static_panel']['case_ids'])==8 and set(spec['static_panel']['case_ids'])<=cids
    dyn=spec['dynamic_panel']['cells']
    ck['dynamic_panel_15_unique_cases']=len(dyn)==15==len({x['id'] for x in dyn}) and sum(x['intervention']=='factorial' for x in dyn)==8
    ck['FT13_unique']=set(x['id'] for x in spec['add_conformance']['gates'])=={f'FT-{i}' for i in range(1,14)}
    ck['FT9_count_exact']=sum(4**n-2*2**n+1 for n in (3,4,5))==1235==spec['add_conformance']['finite_search_total']
    symbols_ok=True
    for row in fmap['files']:
        f=src/row['path']
        if row['operation'].startswith('ADD'):continue
        if not f.exists():symbols_ok=False;continue
        if not row['symbols']:continue
        tree=ast.parse(f.read_text()); found=set()
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):found.add(node.name)
            if isinstance(node,ast.ClassDef):
                found.add(node.name)
                found.update(node.name+'.'+n.name for n in node.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)))
        symbols_ok &= set(row['symbols'])<=found
    ck['all_target_files_symbols_exist']=symbols_ok
    ck['no_executable_implementation_claim']=all(not x['implemented_now'] for x in fmap['files']) and not fmap['executable_source_modified_this_revision']
    ck['all_127_record_IDs_preserved']=[x['id'] for x in reg['results']]==[x['id'] for x in before['results']] and len(reg['results'])==127
    ck['first_125_records_unchanged']=reg['results'][:125]==before['results'][:125]
    ck['all_scientific_statuses_unchanged']=all(a['status']==b['status'] for a,b in zip(reg['results'],before['results']))
    ck['all_42_constructs_unchanged']=reg['constructs']==before['constructs'] and len(reg['constructs'])==42
    ck['all_10_open_links_unchanged']=reg['open_links']==before['open_links'] and len(reg['open_links'])==10
    ck['existing_edges_unchanged']=all(reg[k]==before[k] for k in ('lineage_edges','planned_experiment_edges','result_children','result_to_constructs'))
    ck['architecture_is_amendment']=model['amendment_of']==spec['experiment_id'] and next(x for x in reg['experiment_designs'] if x['id']==model['id'])['amendment_of']==spec['experiment_id']
    ck['R126_R127_revision_present']=all('revision_1_1' in x for x in reg['results'][-2:])
    md=(root/R).with_suffix('.md').read_text()
    ck['registry_headings_and_changed_anchors_unique']=all(len(re.findall(r'^### '+x['id']+r'\.',md,re.M))==1 for x in reg['results']) and all(md.count('<a id="'+x['id'].lower()+'"></a>')==1 for x in reg['results'][-2:])
    ck['source_attachment_hash']=hashlib.sha256((root/sources['neighbour']['path']).read_bytes()).hexdigest()==sources['neighbour']['sha256']
    ck['ADD_original_bytes_preserved']=hashlib.sha256((root/A/'evidence/add_reconstruction/add_backend_smoke_v1.py').read_bytes()).hexdigest()=='ee607902b61b28328affc9ca3474ee8881b610aac9b8ec1773081abe3d585e27'
    ck['denominator_formulas']=16**12==281474976710656 and math.comb(48,24)==32247603683100 and math.prod(math.comb(12,n) for n in (4,6,7,7))==286898008320
    ck['new_forecast_not_inherited']=spec['budget']['new_runtime_seconds'] is None and not spec['budget']['old_forecast_applies']
    current_py={str(f.relative_to(root/E)):f.read_bytes() for f in (root/E).rglob('*.py')}
    baseline_py={str(f.relative_to(old/E)):f.read_bytes() for f in (old/E).rglob('*.py')}
    ck['executable_python_unchanged_from_document_base']=current_py==baseline_py
    ck['XOR_control_discriminates']=all((a^b)!=((1-a)^b) for a in (0,1) for b in (0,1)) and spec['static_panel']['scramble_template_override']['task_content_intervention']=='flip_A'
    ck['mean_and_sum_distinct']=spec['accounting']['entropy_names']=={'S_r_article':'S_local_mean','bar_S_r_article':'S_local_sum'}
    out=dict(status='PASS' if all(ck.values()) else 'FAIL',checks=ck,count=len(ck),scope='document/specification/static source integrity only; no model execution',new_scientific_runs=0,vm_runs=0)
    (root/P/'PATCH_CHECKS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))
    return 0 if all(ck.values()) else 1


if __name__=='__main__':raise SystemExit(main())
