"""Window comparisons for the frozen A/B/C design, with propagated envelopes."""
import numpy as np
from e002c_exp.engine import compare_pair
from e002c_exp.windows import integral_mean
from .plan import MODELS,TARGETS,OPERATIONS,CONTRACT,physics_key
from .numerics import estimate,linear,ratio,signed,contrast,sampled_minimum

STRUCTURE_NAMES=[f"p_m{m}" for m in range(8)]+[f"p_m{m}_N{n}" for m in range(8) for n in range(4)]+["pL01","pL12","pL02","ell01","ell12","ell02"]

def analyze(results,mode):
    by={physics_key(r["summary"]["case"]):r for r in results};pairs={}
    for k,r in by.items():
        if r["summary"]["case"]["dt"]!=.005:continue
        other=(*k[:-1],.01)
        if other not in by:continue
        check=compare_pair(r,by[other]);pairs[r["summary"]["case"]["id"]]=check
        for obj in (r,by[other]):obj["summary"]["refinement_status"]="passed" if check["pass_gate"] else "failed"
    if mode!="production":
        return dict(pairs=pairs,A=[],B=[],C=[],scope="short technical run; no scientific interpretation")
    horizons=sorted({200.}|{float(r["summary"]["horizon"]) for r in results})
    cache={}
    def get(model,target="base",kind="base",gamma=0.,phi=0.,epsilon=0.,noise=.05,horizon=200.):
        key=(model,phi,epsilon,noise,target,kind,gamma,.005)
        ck=(key,horizon)
        if ck in cache:return cache[ck]
        if key not in by:return None
        fine=by[key];coarse=by.get((*key[:-1],.01))
        fm=integral_mean(fine["series"],fine["names"],horizon)
        cm=integral_mean(coarse["series"],coarse["names"],horizon) if coarse is not None else None
        if fm is None:return None
        times=horizon-10+2*np.arange(6)
        def ranges(r):
            idx=[int(np.argmin(abs(r["series"][:,0]-t))) for t in times]
            if not np.array_equal(r["series"][idx,0],times):raise ValueError("Exact window missing")
            return dict(zip(r["names"],np.ptp(r["series"][idx,1:],axis=0)))
        fr=ranges(fine);cr=ranges(coarse) if cm is not None else None
        vals={name:estimate(value,None if cm is None else
                CONTRACT["primitive_absolute_floor"]+CONTRACT["resolution_multiplier"]*
                (abs(value-cm[name])+max(fr[name],cr[name]))) for name,value in fm.items()}
        matched=(coarse is not None and cm is not None)
        allr=[fine]+([coarse] if matched else [])
        stationary=all(r["summary"]["horizon"]==horizon and r["summary"]["stationarity"]["pass_gate"] and
                       not r["summary"].get("failed") for r in allr)
        refined=matched and all(r["summary"].get("refinement_status")=="passed" for r in allr)
        reason="READY" if stationary and refined else "FINITE_TIME_ONLY" if not stationary else "SCREENING_ONLY" if not matched else "REFINEMENT_FAILED"
        out=dict(values=vals,eligible=stationary and refined,reason=reason,
                 cases=[r["summary"]["case"]["id"] for r in allr],horizon=horizon)
        cache[ck]=out
        return out
    def structural(base,t,c):
        out={}
        for tag,left,right in [("T_minus_C",t,c),("T_minus_0",t,base),("C_minus_0",c,base)]:
            rows=[]
            for name in STRUCTURE_NAMES:
                x,y=left["values"][name],right["values"][name]
                d=linear([(1,x),(-1,y)])
                practical=CONTRACT["structure_absolute"]+CONTRACT["structure_relative"]*max(abs(x["value"]),abs(y["value"]))
                changed=(d["uncertainty"] is not None and abs(d["value"])>max(d["uncertainty"],practical))
                rows.append(dict(name=name,delta=d,practical_threshold=practical,changed=changed))
            out[tag]=rows
        out["status"]="STRUCTURE_COUPLED" if any(x["changed"] for x in out["T_minus_C"]) else "NO_RESOLVED_STRUCTURAL_SHIFT"
        return out
    def response_metrics(base,t,c):
        b,tv,cv=base["values"],t["values"],c["values"]
        delta=linear([(1,tv["h"]),(-1,cv["h"])])
        return dict(h0=b["h"],hT=tv["h"],hC=cv["h"],delta=delta,r=ratio(delta,b["h"]),
                    T_minus_0=linear([(1,tv["h"]),(-1,b["h"])]),
                    C_minus_0=linear([(1,cv["h"]),(-1,b["h"])]))
    A=[]
    for horizon in horizons:
        for target,gamma in [(x,.1) for x in ("S2a","S2b","S1a","S1b")]+[(x,g) for x in ("S2","S1") for g in (.05,.1,.2)]:
            inputs={m:[get(m,horizon=horizon),get(m,target,"T",gamma,horizon=horizon),get(m,target,"C",gamma,horizon=horizon)] for m in MODELS}
            row=dict(target=target,gamma=gamma,horizon=horizon)
            if any(x is None for rs in inputs.values() for x in rs):
                row["status"]="NOT_EVALUABLE";A.append(row);continue
            ready=all(x["eligible"] for rs in inputs.values() for x in rs)
            row["models"]={m:response_metrics(*rs) for m,rs in inputs.items()}
            q,r=[row["models"][m] for m in MODELS]
            G0=linear([(1,q["h0"]),(-1,r["h0"])])
            GT=linear([(1,q["hT"]),(-1,r["hT"])]);GC=linear([(1,q["hC"]),(-1,r["hC"])])
            E=linear([(1,q["delta"]),(-1,r["delta"])])
            row.update(G0=G0,GT=GT,GC=GC,E=E,S=ratio(E,G0),Q=linear([(1,q["r"]),(-1,r["r"])]),
                eligible=ready,reasons=sorted(set(x["reason"] for rs in inputs.values() for x in rs)),
                status=signed(E,ready),S_status=signed(ratio(E,G0),ready))
            row["structure"]={m:structural(*rs) for m,rs in inputs.items()}
            components=[];coherences={}
            for mask in range(8):
                for n in range(4):
                    hn=f"h_m{mask}_N{n}";pn=f"p_m{mask}_N{n}";ds=[];decomposed={}
                    for m in MODELS:
                        b,t,c=inputs[m];tv,cv=t["values"],c["values"]
                        d=linear([(1,tv[hn]),(-1,cv[hn])]);ds.append(d)
                        jt=ratio(tv[hn],tv[pn],True);jc=ratio(cv[hn],cv[pn],True)
                        pt,pc=tv[pn]["value"],cv[pn]["value"]
                        jw=None if jt["value"] is None or jc["value"] is None else (pt-pc)*(jt["value"]+jc["value"])/2
                        cj=None if jt["value"] is None or jc["value"] is None else (jt["value"]-jc["value"])*(pt+pc)/2
                        decomposed[m]=dict(delta=d,jT=jt,jC=jc,weight_term=jw,conditional_term=cj,
                            decomposition_residual=None if jw is None else d["value"]-jw-cj)
                    component=linear([(1,ds[0]),(-1,ds[1])])
                    components.append(dict(mask=mask,N=n,E=component,S=ratio(component,G0),models=decomposed))
            row["components"]=components
            row["component_sum_error"]=abs(sum(x["E"]["value"] for x in components)-E["value"])
            if row["component_sum_error"]>1e-10:raise ValueError("Incomplete gap decomposition")
            for m in MODELS:
                b,t,c=inputs[m];coherences[m]={}
                for target_key in OPERATIONS[target]:
                    mask,a,bb=TARGETS[target_key];nn=a.bit_count();records={}
                    for branch,ctx in [("base",b),("T",t),("C",c)]:
                        v=ctx["values"];re=v["C_"+target_key+"_re"];im=v["C_"+target_key+"_im"]
                        z=complex(re["value"],im["value"]);u=None if re["uncertainty"] is None else float(np.hypot(re["uncertainty"],im["uncertainty"]))
                        records[branch]=dict(re=re,im=im,absolute=float(abs(z)),absolute_uncertainty=u,
                            conditional_re=ratio(re,v[f"p_m{mask}_N{nn}"],True),
                            conditional_im=ratio(im,v[f"p_m{mask}_N{nn}"],True),
                            activity_at_dose=linear([(gamma,v["aunit_"+target_key])]))
                    zt=complex(records["T"]["re"]["value"],records["T"]["im"]["value"])
                    zc=complex(records["C"]["re"]["value"],records["C"]["im"]["value"])
                    phase_valid=all(records[k]["absolute_uncertainty"] is not None and records[k]["absolute"]>
                                    records[k]["absolute_uncertainty"] for k in ("T","C"))
                    records["T_minus_C"]=dict(re=float((zt-zc).real),im=float((zt-zc).imag),
                        phase_shift=float(np.angle(zt*zc.conjugate())) if phase_valid else None)
                    coherences[m][target_key]=records
            row["coherences"]=coherences;A.append(row)
    def dip(model,phi,noise,horizon,target="base",kind="base",gamma=0.,delta=.125):
        ctx=[get(model,target,kind,gamma,phi,e,noise,horizon) for e in (-delta,0.,delta)]
        if any(x is None for x in ctx):return dict(status="NOT_EVALUABLE",eligible=False)
        hs=[x["values"]["h_m6_N2"] for x in ctx];ps=[x["values"]["p_m6_N2"] for x in ctx]
        js=[ratio(h,p,True) for h,p in zip(hs,ps)];d=contrast(*js)
        eligible=all(x["eligible"] for x in ctx)
        return dict(D=d,raw_D=contrast(*hs),weight_D=contrast(*ps),j=js,h=hs,p=ps,
            eligible=eligible,status=signed(d,eligible),minimum=sampled_minimum(*js,eligible),
            reasons=sorted(set(x["reason"] for x in ctx)),cases=[x["cases"] for x in ctx])
    B=[]
    for horizon in horizons:
        for model in MODELS:
            for phi in (0.,.5):
                for noise in (.05,.25):
                    for delta in ((.125,.0625,.25) if phi==.5 else (.125,)):
                        B.append(dict(model=model,phi_over_pi=phi,dephasing=noise,delta=delta,horizon=horizon,
                                      **dip(model,phi,noise,horizon,delta=delta)))
    C=[];link={}
    for horizon in horizons:
        for model in MODELS:
            for target in ("M2","M1"):
                t=dip(model,.5,.05,horizon,target,"T",.1)
                c=dip(model,.5,.05,horizon,target,"C",.1)
                b=dip(model,.5,.05,horizon)
                row=dict(model=model,target=target,horizon=horizon,T=t,C=c,baseline=b)
                if "D" in t and "D" in c:
                    d=linear([(1,t["D"]),(-1,c["D"])])
                    row.update(delta_D=d,raw_delta_D=linear([(1,t["raw_D"]),(-1,c["raw_D"])]),
                        weight_delta_D=linear([(1,t["weight_D"]),(-1,c["weight_D"])]),
                        eligible=t["eligible"] and c["eligible"],status=signed(d,t["eligible"] and c["eligible"]))
                    link[horizon,model,target]=row
                else:row.update(eligible=False,status="NOT_EVALUABLE")
                C.append(row)
        for axis in ("model","sector"):
            values=("M2","M1") if axis=="model" else MODELS
            for value in values:
                lk=(horizon,"QS",value) if axis=="model" else (horizon,value,"M2")
                rk=(horizon,"RR_QS",value) if axis=="model" else (horizon,value,"M1")
                if lk not in link or rk not in link:continue
                left,right=link[lk],link[rk];d=linear([(1,left["delta_D"]),(-1,right["delta_D"])])
                C.append(dict(comparison="QS_minus_RR" if axis=="model" else "M2_minus_M1",
                    fixed=value,horizon=horizon,delta_D=d,eligible=left["eligible"] and right["eligible"],
                    status=signed(d,left["eligible"] and right["eligible"])))
    return dict(pairs=pairs,A=A,B=B,C=C,scope="finite-dose causal channel contrasts; no automatic Fano/entanglement necessity claim")
