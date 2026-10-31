"""Retrospective arithmetic audit using previously published reports only."""
import hashlib,json,math,platform,sys
from pathlib import Path
from infra.github_result_reader import read_github_result
from e002e_exp.plan import selected_work
ROOT=Path(__file__).resolve().parents[2];D=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def main():
    allrows=[];verified=[]
    for tag,rid,ref,source,stage in [('baseline','E002e_BASELINE_v001_r001','517217b5cb1e56dcb0e9cfd35a74e51fb202a49c','464e7d2ec560426ae106c6d607f47a7a6b667cc9','baseline'),('F2','E002e_F2_v001_r001','6e9e915986293db9d6702e7f54021115a5c28b02','9d2985bb3ab9cde5ad6a6c03b346d68027d81875','F2')]:
        assert read(D/(tag+'_remote_run.json'))==read(ROOT/'results'/rid/'run.json')
        v=read_github_result(lambda repo,path,ref:(ROOT/path).read_bytes(),repository='IgorSabirov/vm-lab',result_commit=ref,run_id=rid,source_commit=source)
        assert v['execution_succeeded'];verified.append(dict(run_id=rid,commit=ref,files=len(v['artifacts'])))
        allrows += [read(ROOT/'results'/rid/'files'/(c['id']+'.json')) for c in selected_work(stage)['full']]
    groups={}
    for r in allrows:
        c=r['case']
        if c['model'] in ('QS','RR_QS') and c['phi_over_pi']==.5:groups.setdefault((c['model'],c['m6_v_over_J']),{})[c['epsilon']]=r
    fits=[];splits=[];checks=[]
    for (model,v),line in sorted(groups.items()):
        def contrast(d):
            x=[line[e]['conditional']['j6'] for e in (0.,-d,d)]
            return .5*(x[1]['value']+x[2]['value'])-x[0]['value'],x[0]['uncertainty']+.5*(x[1]['uncertainty']+x[2]['uncertainty'])
        A,uA=contrast(.125);B,uB=contrast(.5);R=B/A
        Rlo=(B-uB)/(A+uA);Rhi=(B+uB)/(A-uA)
        out=dict(model=model,v=v,R=R,R_interval=[Rlo,Rhi],K_ratio=R/16,j0=line[0.]['conditional']['j6']['value'])
        if 1<Rlo<Rhi<16:
            s=.25*(R-1)/(16-R);w=math.sqrt(s);amp=A*(s+.015625)/.015625
            ws=[math.sqrt(.25*(r-1)/(16-r)) for r in (Rlo,Rhi)]
            out.update(status='CONDITIONAL_TWO_POINT_FIT',w=w,w_interval=ws,full_half_depth_width=2*w,Delta=amp,plateau=out['j0']+amp,relative_depth=amp/out['j0'],predictions={str(e):out['j0']+amp*e*e/(e*e+s) for e in (.0625,.25,2.,4.,8.,16.,32.)})
            for d in (.0625,.25):
                if d in line:
                    observed,u=contrast(d);predicted=amp*d*d/(d*d+s)
                    checks.append(dict(model=model,v=v,delta=d,observed=observed,predicted=predicted,relative_error=(predicted-observed)/observed,status='RETROSPECTIVE_ALREADY_VIEWED',observed_uncertainty=u,independent_solvers_pass=all(line[e]['refinement']['gate']['pass_gate'] for e in (-d,0.,d))))
        else:out['status']='NO_POSITIVE_SINGLE_LORENTZIAN_FIT'
        fits.append(out)
        for e,r in sorted(line.items()):
            if e<=0:continue
            h0=line[0.]['raw']['h6'];p0=line[0.]['raw']['P_m6_N2'];h=r['raw']['h6'];p=r['raw']['P_m6_N2']
            assert min(p,p0)>1e-6
            dh,dp=h-h0,p-p0;change=h/p-h0/p0
            H=.5*dh*(1/p+1/p0);P=.5*(h+h0)*(1/p-1/p0)
            rem=change-H-P;assert abs(rem)<1e-14
            linear_h=dh/p0;linear_p=-(h0/p0)*dp/p0
            splits.append(dict(model=model,v=v,epsilon=e,h0=h0,p0=p0,h=h,p=p,delta_j=change,numerator_contribution=H,denominator_contribution=P,exact_closure_error=rem,denominator_fraction=P/change if change else None,linear_h=linear_h,linear_p=linear_p,linear_remainder=change-linear_h-linear_p))
    transfers=[]
    for model in ('QS','RR_QS'):
        f=next(f for f in fits if f['model']==model and f['v']==.5);line=groups[model,1.];j0=line[0.]['conditional']['j6']['value'];A=.5*(line[-.125]['conditional']['j6']['value']+line[.125]['conditional']['j6']['value'])-j0;s=f['w']**2;delta=A*(s+.015625)/.015625
        transfers.append(dict(model=model,w=f['w'],Delta=delta,predictions={str(e):j0+delta*e*e/(e*e+s) for e in (.0625,.25,.5,2.,4.,8.,16.)},known_D05=.5*(line[-.5]['conditional']['j6']['value']+line[.5]['conditional']['j6']['value'])-j0,predicted_D05=delta*.25/(.25+s),status='RETROSPECTIVE_WIDTH_TRANSFER_NOT_BLIND'))
    result=dict(verified_reports=verified,fits=fits,retrospective_F1=checks,width_transfer=transfers,exact_ratio_decomposition=splits,unique_sign_model_abs_epsilon_cases=6,environment=dict(python=sys.version,platform=platform.platform()),new_NESS=0,new_QRT=0)
    (D/'numbers.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(fits=fits,retrospective_F1=checks,width_transfer=transfers,splits_delta125=[r for r in splits if r['epsilon']==.125])))
if __name__=='__main__':main()
