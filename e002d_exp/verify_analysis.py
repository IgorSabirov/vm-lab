"""Report-only arithmetic, independent of production analysis/numerics/model imports.

Input primitives are reconstructed from the exported six-point scalar windows.
Eligibility is conditional on reported full-grid/quality/stationarity gates; those
gates cannot be independently recomputed from the deliberately reduced export.
"""
import math
import numpy as np

TARGETS={"S2a":(2,5,6),"S2b":(4,3,6),"S1a":(2,1,2),"S1b":(4,1,4),
         "M2a":(6,5,6),"M2b":(6,3,6),"M1a":(6,1,2),"M1b":(6,1,4)}
OPS={**{k:(k,) for k in ("S2a","S2b","S1a","S1b")},"S2":("S2a","S2b"),"S1":("S1a","S1b")}
MODELS=("QS","RR_QS")

def point(v,u=None,reason=None):
    if v is None:return (None,None,None,None,reason or "nonfinite")
    return (v,u,None if u is None else v-u,None if u is None else v+u,
            reason if reason is not None else ("no_coarse_pair" if u is None else None))

def add(*terms):
    if any(p[0] is None for k,p in terms):return point(None,reason="undefined_operand")
    u=None if any(p[1] is None for k,p in terms) else sum(abs(k)*p[1] for k,p in terms)
    return point(sum(k*p[0] for k,p in terms),u)

def divide(a,b,prob=False):
    floor=1e-6 if prob else 1e-8
    if a[0] is None or b[0] is None or abs(b[0])<=floor or (prob and b[0]<=floor):
        return point(None,reason="small_denominator")
    v=a[0]/b[0]
    if a[1] is None or b[1] is None:return point(v)
    if b[2]<=0<=b[3] or min(abs(b[2]),abs(b[3]))<=floor or b[1]>.1*abs(b[0]):
        return point(None,reason="uncertain_denominator")
    endpoints=[x/y for x in a[2:4] for y in b[2:4]];lo,hi=min(endpoints),max(endpoints)
    return (v,max(v-lo,hi-v),lo,hi,None)

def pack(p):return dict(zip(("value","uncertainty","lower","upper","reason"),p))
def sign(p,eligible=True):
    if not eligible:return "INELIGIBLE"
    if p[0] is None:return "UNDEFINED"
    if p[1] is None:return "SCREENING_ONLY"
    return "RESOLVED_POSITIVE" if p[2]>0 else "RESOLVED_NEGATIVE" if p[3]<0 else "UNRESOLVED_AT_TOLERANCE"
def difference(a,b):return add((1,a),(-1,b))

def verify_derived(metrics,stats):
    if metrics.get("mode")!="production" or metrics.get("fatal") or metrics.get("case_failures"):return 0
    summaries={s["case"]["id"]:s for s in metrics["cases"]};checked=0
    def equal(actual,expected,path):
        nonlocal checked
        if isinstance(expected,dict):
            if not isinstance(actual,dict):raise ValueError("Derived object: "+path)
            for k,v in expected.items():
                if k not in actual:raise ValueError("Derived missing: "+path+"."+k)
                equal(actual[k],v,path+"."+k)
        elif isinstance(expected,list):
            if not isinstance(actual,list) or len(actual)!=len(expected):raise ValueError("Derived list: "+path)
            for i,v in enumerate(expected):equal(actual[i],v,path+"["+str(i)+"]")
        else:
            checked+=1
            if isinstance(expected,(float,int)) and not isinstance(expected,bool):
                ok=actual is not None and np.isfinite(actual) and abs(actual-expected)<=1e-10
            else:ok=actual==expected
            if not ok:raise ValueError("Derived reconstruction failed: "+path)
    def context(model,target,kind,gamma,phi,eps,noise,horizon):
        key=(model,target,kind,gamma,phi,eps,noise,.005,horizon)
        if key not in stats:return None
        fine=stats[key];coarse=stats.get((*key[:-2],.01,horizon))
        members=[summaries[fine["id"]]]+([summaries[coarse["id"]]] if coarse else [])
        vals={n:point(v,None if coarse is None else 1e-8+10*(abs(v-coarse["mean"][n])+max(fine["range"][n],coarse["range"][n])))
              for n,v in fine["mean"].items()}
        stationary=all(s["horizon"]==horizon and s["stationarity"]["pass_gate"] and not s.get("failed") for s in members)
        refined=coarse is not None and all(s["refinement_status"]=="passed" for s in members)
        reason="READY" if stationary and refined else "FINITE_TIME_ONLY" if not stationary else "SCREENING_ONLY" if coarse is None else "REFINEMENT_FAILED"
        return dict(v=vals,eligible=stationary and refined,reason=reason,cases=[s["case"]["id"] for s in members])
    def dip(model,phi,noise,horizon,target="base",kind="base",gamma=0.,delta=.125):
        ctx=[context(model,target,kind,gamma,phi,e,noise,horizon) for e in (-delta,0.,delta)]
        if any(c is None for c in ctx):return dict(status="NOT_EVALUABLE",eligible=False)
        h=[c["v"]["h_m6_N2"] for c in ctx];p=[c["v"]["p_m6_N2"] for c in ctx];j=[divide(a,b,True) for a,b in zip(h,p)]
        contrast=lambda x:add((1,x[1]),(-.5,x[0]),(-.5,x[2]))
        d=contrast(j);eligible=all(c["eligible"] for c in ctx)
        dl,dr=difference(j[0],j[1]),difference(j[2],j[1])
        return dict(D=pack(d),raw_D=pack(contrast(h)),weight_D=pack(contrast(p)),j=[pack(x) for x in j],
            h=[pack(x) for x in h],p=[pack(x) for x in p],eligible=eligible,status=sign(d,eligible),
            minimum=dict(left_minus_center=pack(dl),right_minus_center=pack(dr),status="CENTER_BELOW_BOTH_SAMPLED_NEIGHBORS"
                if eligible and sign(dl)==sign(dr)=="RESOLVED_POSITIVE" else "SAMPLED_MINIMUM_NOT_RESOLVED"),
            reasons=sorted({c["reason"] for c in ctx}),cases=[c["cases"] for c in ctx])
    def unpack(d):return tuple(d[k] for k in ("value","uncertainty","lower","upper","reason"))
    analysis=metrics["analysis"]
    horizons=sorted({200.}|{float(s["horizon"]) for s in summaries.values()})
    akeys={(t,g,h) for h in horizons for t,g in [(t,.1) for t in ("S2a","S2b","S1a","S1b")]+[(t,g) for t in ("S2","S1") for g in (.05,.1,.2)]}
    if len(analysis["A"])!=len(akeys) or {(r["target"],r["gamma"],r["horizon"]) for r in analysis["A"]}!=akeys:raise ValueError("Derived A coverage")
    for row in analysis["A"]:
        target,gamma,horizon=row["target"],row["gamma"],row["horizon"]
        contexts={m:[context(m,t,k,g,0.,0.,.05,horizon) for t,k,g in (("base","base",0.),(target,"T",gamma),(target,"C",gamma))] for m in MODELS}
        if any(c is None for group in contexts.values() for c in group):equal(row,{"status":"NOT_EVALUABLE"},"A");continue
        ready=all(c["eligible"] for group in contexts.values() for c in group)
        values={m:[c["v"] for c in group] for m,group in contexts.items()}
        qs,rr=values["QS"],values["RR_QS"]
        gaps=[difference(qs[i]["h"],rr[i]["h"]) for i in range(3)]
        effects={m:difference(v[1]["h"],v[2]["h"]) for m,v in values.items()}
        effect=difference(effects["QS"],effects["RR_QS"]);scaled=divide(effect,gaps[0])
        expected=dict(G0=pack(gaps[0]),GT=pack(gaps[1]),GC=pack(gaps[2]),E=pack(effect),S=pack(scaled),
            Q=pack(difference(divide(effects["QS"],qs[0]["h"]),divide(effects["RR_QS"],rr[0]["h"]))),
            eligible=ready,status=sign(effect,ready),S_status=sign(scaled,ready),
            reasons=sorted({c["reason"] for group in contexts.values() for c in group}))
        models={};structure={};coherences={}
        for m,(base,t,c) in values.items():
            models[m]=dict(h0=pack(base["h"]),hT=pack(t["h"]),hC=pack(c["h"]),delta=pack(effects[m]),r=pack(divide(effects[m],base["h"])),
                T_minus_0=pack(difference(t["h"],base["h"])),C_minus_0=pack(difference(c["h"],base["h"])))
            structure[m]={}
            for label,left,right in (("T_minus_C",t,c),("T_minus_0",t,base),("C_minus_0",c,base)):
                rows=[]
                names=[f"p_m{k}" for k in range(8)]+[f"p_m{k}_N{n}" for k in range(8) for n in range(4)]+["pL01","pL12","pL02","ell01","ell12","ell02"]
                for name in names:
                    d=difference(left[name],right[name]);threshold=1e-6+.01*max(abs(left[name][0]),abs(right[name][0]))
                    rows.append(dict(name=name,delta=pack(d),practical_threshold=threshold,changed=d[1] is not None and abs(d[0])>max(d[1],threshold)))
                structure[m][label]=rows
            structure[m]["status"]="STRUCTURE_COUPLED" if any(x["changed"] for x in structure[m]["T_minus_C"]) else "NO_RESOLVED_STRUCTURAL_SHIFT"
            coherences[m]={}
            for key in OPS[target]:
                mask,a,b=TARGETS[key];records={};zs={};errors={}
                for branch,v in (("base",base),("T",t),("C",c)):
                    re,im=v["C_"+key+"_re"],v["C_"+key+"_im"];z=complex(re[0],im[0]);zs[branch]=z
                    u=None if re[1] is None else math.hypot(re[1],im[1]);errors[branch]=u
                    records[branch]=dict(re=pack(re),im=pack(im),absolute=abs(z),absolute_uncertainty=u,
                        conditional_re=pack(divide(re,v[f"p_m{mask}_N{a.bit_count()}"],True)),
                        conditional_im=pack(divide(im,v[f"p_m{mask}_N{a.bit_count()}"],True)),activity_at_dose=pack(add((gamma,v["aunit_"+key]))))
                phase_ok=all(errors[k] is not None and abs(zs[k])>errors[k] for k in ("T","C"))
                dz=zs["T"]-zs["C"];product=zs["T"]*zs["C"].conjugate()
                records["T_minus_C"]=dict(re=dz.real,im=dz.imag,phase_shift=math.atan2(product.imag,product.real) if phase_ok else None)
                coherences[m][key]=records
        expected.update(models=models,structure=structure,coherences=coherences)
        components=[]
        for mask in range(8):
            for n in range(4):
                hn,pn=f"h_m{mask}_N{n}",f"p_m{mask}_N{n}";ds=[];parts={}
                for m,(base,t,c) in values.items():
                    d=difference(t[hn],c[hn]);ds.append(d);jt,jc=divide(t[hn],t[pn],True),divide(c[hn],c[pn],True)
                    valid=jt[0] is not None and jc[0] is not None
                    weight=(t[pn][0]-c[pn][0])*(jt[0]+jc[0])/2 if valid else None
                    current=(jt[0]-jc[0])*(t[pn][0]+c[pn][0])/2 if valid else None
                    parts[m]=dict(delta=pack(d),jT=pack(jt),jC=pack(jc),weight_term=weight,conditional_term=current,
                        decomposition_residual=d[0]-weight-current if valid else None)
                d=difference(*ds);components.append(dict(mask=mask,N=n,E=pack(d),S=pack(divide(d,gaps[0])),models=parts))
        expected.update(components=components,component_sum_error=abs(sum(x["E"]["value"] for x in components)-effect[0]))
        equal(row,expected,"A."+target+"."+str(horizon))
    bkeys={(m,p,n,d,h) for h in horizons for m in MODELS for p in (0.,.5) for n in (.05,.25) for d in ((.125,.0625,.25) if p==.5 else (.125,))}
    if len(analysis["B"])!=len(bkeys) or {(r["model"],r["phi_over_pi"],r["dephasing"],r["delta"],r["horizon"]) for r in analysis["B"]}!=bkeys:raise ValueError("Derived B coverage")
    for row in analysis["B"]:equal(row,dip(row["model"],row["phi_over_pi"],row["dephasing"],row["horizon"],delta=row["delta"]),"B")
    cexpected=[];links={}
    for horizon in horizons:
        for model in MODELS:
            for target in ("M2","M1"):
                t=dip(model,.5,.05,horizon,target,"T",.1);c=dip(model,.5,.05,horizon,target,"C",.1)
                expected=dict(model=model,target=target,horizon=horizon,T=t,C=c,baseline=dip(model,.5,.05,horizon))
                if "D" in t and "D" in c:
                    d=difference(unpack(t["D"]),unpack(c["D"]));ok=t["eligible"] and c["eligible"]
                    expected.update(delta_D=pack(d),raw_delta_D=pack(difference(unpack(t["raw_D"]),unpack(c["raw_D"]))),
                        weight_delta_D=pack(difference(unpack(t["weight_D"]),unpack(c["weight_D"]))),eligible=ok,status=sign(d,ok))
                    links[horizon,model,target]=expected
                else:expected.update(eligible=False,status="NOT_EVALUABLE")
                cexpected.append(expected)
        for axis,items in (("QS_minus_RR",("M2","M1")),("M2_minus_M1",MODELS)):
            for value in items:
                lk,rk=((horizon,"QS",value),(horizon,"RR_QS",value)) if axis=="QS_minus_RR" else ((horizon,value,"M2"),(horizon,value,"M1"))
                if lk not in links or rk not in links:continue
                l,r=links[lk],links[rk];d=difference(unpack(l["delta_D"]),unpack(r["delta_D"]));ok=l["eligible"] and r["eligible"]
                cexpected.append(dict(comparison=axis,fixed=value,horizon=horizon,delta_D=pack(d),eligible=ok,status=sign(d,ok)))
    equal(analysis["C"],cexpected,"C")
    return checked
