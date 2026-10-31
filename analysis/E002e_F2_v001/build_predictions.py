"""Freeze a falsifiable training-only contrast-transfer candidate."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import numpy as np
from scipy import sparse as sp
from e002e_exp.plan import inventory,validate_predictions
from e002e_exp.runtime import kernel_hash
from e002c_exp.model import operators
from e002_exp.model import maxabs

ROOT=Path(__file__).resolve().parents[2];D=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def write(name,x):
    (D/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def main():
    analysis=read(D/'training_analysis.json');inputs=read(D/'training_inputs.json')
    full={x['model']:x for x in analysis['full_lines']}
    g={x['v']:x for x in analysis['small_lines'] if x['block']=='G' and x['dimension']==4 and x['mask']==6 and x['phi']==.5}
    g2={x['v']:x for x in analysis['small_lines'] if x['block']=='G' and x['dimension']==8 and x['mask']==6 and x['phi']==.5}
    f2=[c for c in inventory()['full_static'] if c['block']=='F2'];pred=[];caps={};audit=[]
    review=read(ROOT/'experiments/e002e/implementation_review_exportfix.json')
    for model in ('QS','RR_QS'):
        b=full[model]['contrasts']['0.125'];gc=g[1.]['contrasts']['j_N1']['0.125']
        gain=b['value']/gc['value'];ug=(b['uncertainty']+abs(gain)*gc['uncertainty'])/(abs(gc['value'])-gc['uncertainty'])
        check=gain*g[1.]['contrasts']['j_N1']['0.5']['value'];actual=full[model]['contrasts']['0.5']['value']
        audit.append(dict(model=model,gain=gain,gain_uncertainty=ug,training_D05_prediction=check,training_D05_actual=actual,training_relative_error=abs(check-actual)/abs(actual)))
        for v in (0.,.5):
            cases={c['epsilon']:c for c in f2 if c['model']==model and c['m6_v_over_J']==v}
            for delta in (.125,.5):
                x=g[v]['contrasts']['j_N1'][str(delta)];base=full[model]['contrasts'][str(delta)]
                expected=0. if v==0 else gain*x['value']
                train_u=.1*base['uncertainty'] if v==0 else abs(x['value'])*ug+abs(gain)*x['uncertainty']+ug*x['uncertainty']
                science=.1*abs(base['value']) if v==0 else .2*abs(expected)
                tol=science+train_u;pid=f'{model}_D{delta:g}_v{v:g}';ids=[cases[e]['id'] for e in (0.,-delta,delta)]
                training_ids=[i['id'] for i in inputs if i['block'] in ('G','R_baseline','F1_v_equals_J')]
                pred.append(dict(prediction_id=pid,model=model,physical_case_ids=ids,
                    observable_definition=dict(kind='linear_combination',observable='j6',linear_terms=[dict(case_id=ids[0],coefficient=1.),dict(case_id=ids[1],coefficient=-.5),dict(case_id=ids[2],coefficient=-.5)]),
                    parameter_domain=dict(phi_over_pi=.5,node_noise=.05,m6_v_over_J=v,delta=delta),prediction_type='value',expected_value_or_sign_or_interval=expected,
                    tolerance_and_error_rule=dict(absolute_tolerance=tol,error_rule='interval_with_numerical_uncertainty',scientific_allowance=science,training_numerical_allowance=train_u),training_input_ids=training_ids,
                    candidate_model_derivation='H_G1: one positive gain from full/G1 D125 at v=1; D(delta,v)=gain*G1_D(delta,v); no heldout fitting',
                    denominator_validity_if_ratio='j6 only if p(m6,N2)>1e-6 and p exceeds its propagated uncertainty; otherwise NUMERICALLY_UNRESOLVED',
                    outcome_on_failure='Reject H_G1 contrast transfer for this domain; do not infer absence of every Fano mechanism',confirmatory_or_exploratory='confirmatory',family='H_G1'))
                caps[pid]=tol
        for c in [c for c in f2 if c['model']==model and c['m6_v_over_J']==.5]:
            e=c['epsilon'];bpoint=next(p for p in full[model]['points'] if p['epsilon']==e)
            for ladder,obs in ((g,'j1'),(g2,'j2')):
                lo=next(p for p in ladder[1.]['points'] if p['epsilon']==e)[obs]
                hi=next(p for p in ladder[.5]['points'] if p['epsilon']==e)[obs]
                assert hi>lo
            tol=.001*abs(bpoint['j6']['value']);pid=f'{model}_DELTA_j6_eps{e:g}_v0.5'
            pred.append(dict(prediction_id=pid,model=model,physical_case_ids=[c['id']],
                observable_definition=dict(kind='baseline_difference',observable='j6',linear_terms=[dict(case_id=c['id'],coefficient=1.)]),
                parameter_domain=dict(phi_over_pi=.5,node_noise=.05,m6_v_over_J=.5,epsilon=e),prediction_type='sign',expected_value_or_sign_or_interval=1,
                tolerance_and_error_rule=dict(absolute_tolerance=tol,error_rule='interval_with_numerical_uncertainty',scientific_allowance=tol,training_numerical_allowance=0.),
                training_input_ids=[i['id'] for i in inputs if i['block'] in ('G','R_baseline','F1_v_equals_J')],
                candidate_model_derivation='H_sign: positive j change under v=1 to .5 agrees in G1/m6/N1 and G2/m6/N2; hypothesize transfer to full conditional j6',
                denominator_validity_if_ratio='Both baseline and F2 p6 must exceed1e-6 and their errors',
                outcome_on_failure='Reject transferred positive-sign prediction at this point; distinct from H_G1 and from universal Fano claims',confirmatory_or_exploratory='confirmatory',family='H_sign'))
            caps[pid]=tol
    now=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    record=dict(schema_version=1,status='FROZEN',experiment='E002e',concept_path='experiments/e002e/CONCEPT_v003.md',
        concept_sha256=hashlib.sha256((ROOT/'experiments/e002e/CONCEPT_v003.md').read_bytes()).hexdigest(),code_commit=review['implementation_commit'],kernel_sha256=kernel_hash(),created_at_utc=now,frozen_at_utc=now,
        training_inputs=inputs,allowed_training_blocks=['G','R_baseline','F1_v_equals_J','F3_baseline_if_declared','T_baseline_if_declared'],prohibited_training_blocks=['F2_v0','F2_v0.5'],
        previously_viewed_controls='Small G at v=0/.5/1; full undeformed G3 baseline only. No full F2 states solved/viewed.',heldout_case_ids=[c['id'] for c in f2],predictions=pred,
        family_rules={'H_G1':'All8 value predictions must pass; one resolved failure rejects this transfer; unresolved prevents support','H_sign':'Report10 dependent sign predictions separately; not10 independent proofs'},
        exploratory_outcomes=['absolute h6 and p6 changes','absolute j6 at v=0','continuous minimum position','background and full width','new frequency phase under deformation','mechanistic joint reconstruction of h6,p6,j6'])
    valid=validate_predictions(record,review['implementation_commit'],caps)
    o=operators();Q=sp.diags(np.tile((o['mask_id']==6).astype(float),8));a=o['up'][1]@o['up'][2].getH();hop=o['pl'][1]@(a+a.getH())
    mask2=sp.diags(np.tile((o['mask_id']==2).astype(float),8))
    algebra=dict(commutator_max=maxabs(Q@hop-hop@Q),outside_m6_hopping_max=maxabs((sp.eye(216)-Q)@hop),mask2_hopping_max=maxabs(mask2@hop),mask2_selected_hopping_max=maxabs(mask2@Q@hop))
    assert algebra['commutator_max']==0 and algebra['outside_m6_hopping_max']>0 and algebra['mask2_selected_hopping_max']==0
    z=[np.eye(4)-2*np.diag(np.eye(4)[i]) for i in (1,2,3)];rho=np.zeros((4,4));rho[1,2]=1.
    noise=sum(.05*(Z@rho@Z-rho) for Z in z);algebra['rho01_dephasing_rate']=-float(noise[1,2]);assert abs(algebra['rho01_dephasing_rate']-.2)<1e-15
    algebra.update(curvature_convention='K_delta=-2D_delta/delta^2',parseval='For f=exp(-t), L1=1 but L2_squared=.5; Parseval does not compute L1',F2_outcomes_computed=False)
    write('f2_prereg_predictions.json',record);write('declared_caps.json',caps);write('candidate_training_checks.json',audit);write('review_algebra_checks.json',algebra)
    print(json.dumps(dict(validation=valid,candidate=audit,algebra=algebra,predictions=[dict(id=p['prediction_id'],expected=p['expected_value_or_sign_or_interval'],tolerance=p['tolerance_and_error_rule']['absolute_tolerance']) for p in pred])))

if __name__=='__main__':main()
