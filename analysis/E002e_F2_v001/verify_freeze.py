"""Independently reconstruct frozen tolerances from raw verified report records."""
from pathlib import Path
import hashlib,json,math
from e002e_exp.plan import validate_predictions,selected_work
from e002e_exp.runtime import kernel_hash
from infra.github_result_reader import read_github_result

ROOT=Path(__file__).resolve().parents[2]; D=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def close(a,b):assert math.isclose(a,b,rel_tol=1e-14,abs_tol=1e-17),(a,b)
def contrast(rows,d,obs):
    r={x['case']['epsilon']:x['conditional'][obs] for x in rows}
    assert all(r[e]['value'] is not None for e in (0.,-d,d))
    return (r[0.]['value']-.5*(r[-d]['value']+r[d]['value']),r[0.]['uncertainty']+.5*(r[-d]['uncertainty']+r[d]['uncertainty']))

def main():
    p=read(D/'f2_prereg_predictions.json'); proof=read(D/'remote_provenance.json')
    assert all(proof['readback_exact'].values()) and proof['queue_complete']
    assert not any('E002e_F2' in n for n in proof['queue_names'])
    assert {x['base'] for x in proof['comparisons']}=={'517217b5cb1e56dcb0e9cfd35a74e51fb202a49c','91d8bc40b266effd71e7211dda6fe88f5fb7c9b3'}
    assert all(x['head']==proof['prediction_commit'] and x['status']=='ahead' and x['behind_by']==0 for x in proof['comparisons'])
    sources={'G':('E002e_G_v001_r002','91d8bc40b266effd71e7211dda6fe88f5fb7c9b3','9112ff1a5205a40ce1604a42212d3a6d4baa13ae'),'baseline':('E002e_BASELINE_v001_r001','517217b5cb1e56dcb0e9cfd35a74e51fb202a49c','464e7d2ec560426ae106c6d607f47a7a6b667cc9')}
    reports={}
    for k,(rid,ref,source) in sources.items():
        reports[k]=read_github_result(lambda repo,path,ref:(ROOT/path).read_bytes(),repository='IgorSabirov/vm-lab',result_commit=ref,run_id=rid,source_commit=source)
        assert reports[k]['execution_succeeded']
    rows={'G':[],'baseline':[]}
    for item in p['training_inputs']:
        stage='G' if item['block']=='G' else 'baseline';rid,ref,_=sources[stage]
        assert item['report_commit']==ref and item['path'].startswith('results/'+rid+'/files/')
        path=ROOT/item['path'];meta=reports[stage]['report']['files']['files/'+path.name]
        assert item['bytes']==path.stat().st_size==meta['bytes'] and item['sha256']==sha(path)==meta['sha256']
        if path.suffix=='.json':
            r=read(path)
            if isinstance(r,dict) and 'case' in r:rows[stage].append(r)
    assert len(rows['G'])==92 and len(rows['baseline'])==24
    bundle=read(D/'baseline_bundle.json')
    assert bundle['records']==rows['baseline'] and bundle['status']=='VERIFIED_GITHUB'
    fs={c['id']:c for c in selected_work('F2')['full']};caps={}
    for pred in p['predictions']:
        dom=pred['parameter_domain'];model=pred['model'];v=dom['m6_v_over_J']
        full=[r for r in rows['baseline'] if r['case']['model']==model and r['case']['phi_over_pi']==.5]
        def gr(dim,v):return [r for r in rows['G'] if r['case']['block']=='G' and r['case']['dimension']==dim and r['case']['mask']==6 and r['case']['phi_over_pi']==.5 and r['case']['v_over_J']==v]
        terms=pred['observable_definition']['linear_terms']
        assert all(fs[t['case_id']]['model']==model and fs[t['case_id']]['m6_v_over_J']==v for t in terms)
        if pred['family']=='H_G1':
            d=dom['delta'];B,uB=contrast(full,.125,'j6');G,uG=contrast(gr(4,1.),.125,'j_N1')
            a=B/G;ua=(uB+abs(a)*uG)/(abs(G)-uG);X,uX=contrast(gr(4,v),d,'j_N1');base,ubase=contrast(full,d,'j6')
            expected=0. if v==0 else a*X
            tol=.1*abs(base)+.1*ubase if v==0 else .2*abs(expected)+abs(X)*ua+abs(a)*uX+ua*uX
            assert sorted((fs[t['case_id']]['epsilon'],t['coefficient']) for t in terms)==[(-d,-.5),(0.,1.),(d,-.5)]
        else:
            assert pred['family']=='H_sign' and len(terms)==1 and terms[0]['coefficient']==1
            e=dom['epsilon'];assert fs[terms[0]['case_id']]['epsilon']==e
            base=next(r['conditional']['j6']['value'] for r in full if r['case']['epsilon']==e)
            expected=1;tol=.001*abs(base)
            for dim,obs in ((4,'j_N1'),(8,'j_N2')):
                vals=[next(r['conditional'][obs]['value'] for r in gr(dim,w) if r['case']['epsilon']==e) for w in (1.,.5)]
                assert vals[1]>vals[0]
        close(expected,pred['expected_value_or_sign_or_interval']);close(tol,pred['tolerance_and_error_rule']['absolute_tolerance'])
        # Roundoff only; use the reconstructed cap without loosening it scientifically.
        caps[pred['prediction_id']]=max(tol,pred['tolerance_and_error_rule']['absolute_tolerance'])
    review=read(ROOT/'experiments/e002e/implementation_review_exportfix.json')
    validation=validate_predictions(p,review['implementation_commit'],caps)
    out=dict(status='VERIFIED_GITHUB',prediction_sha256=sha(D/'f2_prereg_predictions.json'),prediction_commit=proof['prediction_commit'],training_inputs=p['training_inputs'],kernel_sha256=kernel_hash(),training_contents_hash_checked=True,commit_ancestry_checked=True,baseline_sha256=sha(D/'baseline_bundle.json'),scientific_tolerance_caps=caps,validation=validation,remote_provenance=proof,checks=dict(raw_training_files=len(p['training_inputs']),raw_small_records=92,raw_full_records=24,predictions_recomputed=len(caps),heldout_cases=20),scientific_acceptance=False,review_boundary='Assistant offline verification; no additional Copilot review or user scientific acceptance')
    (D/'prediction_verification.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(dict(status=out['status'],checks=out['checks'],validation=validation)))

if __name__=='__main__':main()
