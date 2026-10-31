"""Independent report-only reconstruction. Imports no evolution/model/analysis code."""
import gzip,hashlib,json
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
TARGETS={"S2a":(2,5,6),"S2b":(4,3,6),"S1a":(2,1,2),"S1b":(4,1,4),
         "M2a":(6,5,6),"M2b":(6,3,6),"M1a":(6,1,2),"M1b":(6,1,4)}
OPS={**{k:(k,) for k in ("S2a","S2b","S1a","S1b")},
     "S2":("S2a","S2b"),"S1":("S1a","S1b"),"M2":("M2a","M2b"),"M1":("M1a","M1b")}

def verify(report):
    root=Path(report);manifest=json.loads((root/"data_manifest.json").read_text())
    for item in manifest["exported"]:
        path=Path(item["path"])
        if path.is_absolute() or ".." in path.parts:raise ValueError("Unsafe export path")
        data=(root/path).read_bytes()
        if len(data)!=item["bytes"] or hashlib.sha256(data).hexdigest()!=item["sha256"]:
            raise ValueError("Export hash mismatch: "+item["path"])
    metrics=json.loads((root/"metrics.json").read_text());schema=json.loads((root/"schema.json").read_text())
    pointer=metrics["analysis"]
    if "file" in pointer:
        if pointer["file"]!="analysis.json.gz":raise ValueError("Unexpected analysis path")
        data=(root/pointer["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest()!=pointer["sha256"]:raise ValueError("Analysis hash mismatch")
        metrics["analysis"]=json.loads(gzip.decompress(data))
    registry=json.loads((root/"case_registry.json").read_text())["cases"]
    ids=[c["id"] for c in registry];actual=[s["case"]["id"] for s in metrics["cases"]]
    if len(set(ids))!=len(ids) or set(actual)!=set(ids) or len(actual)!=len(ids):raise ValueError("Case coverage mismatch")
    registered={c["id"]:c for c in registry}
    names=schema["series"];maximum=0.;mineig=1.;means={};window_stats={};windows=0;certificates=0
    def check(a,b,label,tolerance=1e-10):
        nonlocal maximum
        a,b=np.asarray(a),np.asarray(b)
        if a.shape!=b.shape:raise ValueError("Reconstruction shape: "+label)
        if not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError("Nonfinite reconstruction: "+label)
        error=float(np.max(abs(a-b),initial=0));maximum=max(maximum,error)
        if error>tolerance:raise ValueError("Reconstruction failed: "+label+" "+str(error))
    for s in metrics["cases"]:
        c=s["case"];cid=c["id"]
        if c!=registered[cid]:raise ValueError("Case identity mismatch")
        with np.load(root/"cases"/(cid+".npz"),allow_pickle=False) as z:
            time=z["window_time"];blocks=z["window_blocks"];values=z["window_scalar"]
            if blocks.shape!=(len(time),9,8,8) or not np.array_equal(time,values[:,0]):raise ValueError("Window shape/grid mismatch")
            check(blocks,blocks.swapaxes(-1,-2).conj(),"Hermiticity")
            ev=np.linalg.eigvalsh(blocks);mineig=min(mineig,float(ev.min()))
            if ev.min() < -1e-8:raise ValueError("Nonpositive reduced block")
            check(blocks[:,0],blocks[:,1:].sum(axis=1),"mask sum")
            check(np.trace(blocks[:,0],axis1=1,axis2=2),np.ones(len(time)),"trace")
            numbers=np.array([i.bit_count() for i in range(8)])
            allcurr=np.zeros((len(time),3));activity=np.zeros(len(time))
            for mask in range(8):
                b=blocks[:,mask+1]
                check(values[:,names.index(f"p_m{mask}")],np.trace(b,axis1=1,axis2=2).real,"mask weight")
                for n in range(4):
                    weight=np.trace(b[:,numbers==n][:,:,numbers==n],axis1=1,axis2=2).real
                    curr=np.zeros((len(time),3))
                    if n in (1,2):
                        pairs=((2,4),(1,2),(1,4)) if n==1 else ((3,5),(5,6),(3,6))
                        for e,(a,bb) in enumerate(pairs):
                            if mask&(1<<e):
                                phase=np.exp(-1j*np.pi*c["phi_over_pi"]) if e==2 else 1.
                                curr[:,e]=-2*(phase*b[:,a,bb]).imag
                    current=curr[:,1]+curr[:,2]
                    check(values[:,names.index(f"p_m{mask}_N{n}")],weight,"sector weight")
                    for tag,expected in [("h",current),*[(tag,curr[:,e]) for e,tag in enumerate(("I01","I12","I02"))]]:
                        check(values[:,names.index(f"{tag}_m{mask}_N{n}")],expected,tag+" sector current")
                    norm=np.sqrt(bool(mask&2)+bool(mask&4)) if n in (1,2) else 0.
                    if np.any(abs(current)>norm*weight+1e-7):raise ValueError("Conditional current exceeds operator bound")
                    allcurr+=curr
                for key,(m,a,bb) in TARGETS.items():
                    if m!=mask:continue
                    check(values[:,names.index("C_"+key+"_re")],b[:,a,bb].real,"coherence real")
                    check(values[:,names.index("C_"+key+"_im")],b[:,a,bb].imag,"coherence imaginary")
                    support=(b[:,a,a]+b[:,bb,bb]).real
                    check(values[:,names.index("aunit_"+key)],support,"jump support")
                    if key in OPS.get(c["target"],()):activity+=c["gamma"]*support
            for e,tag in enumerate(("I01","I12","I02")):check(values[:,names.index(tag)],allcurr[:,e],tag+" sum")
            check(values[:,names.index("h")],allcurr[:,1]+allcurr[:,2],"hop sum")
            check(values[:,names.index("activity_added")],activity,"activity")
            for horizon in s.get("reference_horizons",[]):
                reference=s["reference"] if horizon==s["horizon"] else s["transition_reference"]
                wanted=horizon-10+2*np.arange(6)
                take=np.isin(time,wanted)
                if not np.array_equal(time[take],wanted):raise ValueError("Incomplete reference window")
                mean=simpson(values[take,1:],x=time[take],axis=0)/10
                check(mean,np.array([reference[name] for name in names[1:]]),"mean")
                record=dict(zip(names[1:],mean.tolist()))
                pk=(c["model"],c["target"],c["kind"],c["gamma"],c["phi_over_pi"],c["detuning"],c["dephasing"],c["dt"],horizon)
                means[pk]=record
                window_stats[pk]=dict(id=cid,mean=record,range=dict(zip(names[1:],np.ptp(values[take,1:],axis=0).tolist())))
                if horizon==s["horizon"]:
                    check(mean,np.array([s["reference"][name] for name in names[1:]]),"final mean")
            # Recompute the exported pure-state witness constants without the production helper.
            for ti in range(len(z["e_time"])):
                for state in range(9):
                    if not z["e_valid"][ti,state]:continue
                    block=z["e_blocks"][ti,state];rho=block/np.trace(block).real
                    for j,psi in enumerate(z["e_vectors"][ti,state]):
                        check(np.array(np.vdot(psi,psi).real),np.array(1.),"witness vector norm")
                        alphas=[]
                        for cut in range(3):
                            mat=np.moveaxis(psi.reshape(2,2,2),cut,0).reshape(2,4)
                            alphas.append(float(np.linalg.svd(mat,compute_uv=False)[0]**2))
                        check(np.array(max(alphas)),np.array(z["e_alpha"][ti,state,j]),"witness alpha")
                        check(np.array(np.vdot(psi,rho@psi).real),np.array(z["e_overlap"][ti,state,j]),"witness overlap")
                        certificates+=1
        windows+=1
    # Check full rate maps by independently building diagonal eigenvalue patterns.
    mask_ids=np.array([(int(a==2)+2*int(b==2)+4*int(c==2)) for a in range(3) for b in range(3) for c in range(3)])
    with np.load(root/"intervention_rates.npz",allow_pickle=False) as z:
        for op,keys in OPS.items():
            for branch in ("T","C"):
                expected=np.zeros((216,216))
                for key in keys:
                    m,a,b=TARGETS[key];v=np.zeros(216);edge=np.flatnonzero(mask_ids==m)
                    v[a*27+edge]=1.;v[b*27+edge]=-1. if branch=="T" else 1.
                    expected+=(v[:,None]-v[None,:])**2/2
                check(z[op+"_"+branch],expected,"rate map",1e-12)
            check(z[op+"_difference"],z[op+"_T"]-z[op+"_C"],"rate difference",1e-12)
    # Reconstruct central values of the published scientific comparisons; no import of analysis.
    def get(model,target,kind,gamma,phi,epsilon,noise,horizon):
        return means[(model,target,kind,gamma,phi,epsilon,noise,.005,horizon)]
    def dval(model,target,kind,gamma,phi,noise,horizon,delta=.125,variable="j"):
        records=[get(model,target,kind,gamma,phi,e,noise,horizon) for e in (-delta,0.,delta)]
        ys=[r["h_m6_N2"]/r["p_m6_N2"] if variable=="j" else r[variable] for r in records]
        return ys[1]-(ys[0]+ys[2])/2
    def metric_check(reported,expected,label):
        if reported.get("value") is not None:check(np.array(reported["value"]),np.array(expected),label)
    comparison_count=0
    for row in metrics["analysis"]["A"]:
        if "E" not in row:continue
        h=row["horizon"];g=row["gamma"];target=row["target"]
        b=[get(m,"base","base",0.,0.,0.,.05,h) for m in ("QS","RR_QS")]
        t=[get(m,target,"T",g,0.,0.,.05,h) for m in ("QS","RR_QS")]
        c=[get(m,target,"C",g,0.,0.,.05,h) for m in ("QS","RR_QS")]
        E=(t[0]["h"]-c[0]["h"])-(t[1]["h"]-c[1]["h"]);G=b[0]["h"]-b[1]["h"]
        metric_check(row["E"],E,"E")
        if row["S"]["value"] is not None:metric_check(row["S"],E/G,"S")
        for part in row["components"]:
            name=f"h_m{part['mask']}_N{part['N']}"
            val=(t[0][name]-c[0][name])-(t[1][name]-c[1][name])
            metric_check(part["E"],val,"sector E")
        comparison_count+=1
    for row in metrics["analysis"]["B"]:
        if "D" not in row:continue
        args=(row["model"],"base","base",0.,row["phi_over_pi"],row["dephasing"],row["horizon"],row["delta"])
        if row["D"]["value"] is not None:metric_check(row["D"],dval(*args),"D")
        metric_check(row["raw_D"],dval(*args,variable="h_m6_N2"),"raw D")
        metric_check(row["weight_D"],dval(*args,variable="p_m6_N2"),"weight D");comparison_count+=1
    def response(model,target,horizon):
        return dval(model,target,"T",.1,.5,.05,horizon)-dval(model,target,"C",.1,.5,.05,horizon)
    for row in metrics["analysis"]["C"]:
        if "delta_D" not in row or row["delta_D"]["value"] is None:continue
        h=row["horizon"]
        if "model" in row:expected=response(row["model"],row["target"],h)
        elif row["comparison"]=="QS_minus_RR":expected=response("QS",row["fixed"],h)-response("RR_QS",row["fixed"],h)
        else:expected=response(row["fixed"],"M2",h)-response(row["fixed"],"M1",h)
        metric_check(row["delta_D"],expected,"C delta D");comparison_count+=1
    if windows!=metrics["work"]["actual"]["trajectories"]:raise ValueError("Window count mismatch")
    from .verify_analysis import verify_derived
    derived_fields=verify_derived(metrics,window_stats)
    return dict(status="PASS",case_windows=windows,reconstruction_max_error=maximum,min_reduced_eigenvalue=mineig,
        witness_certificates=certificates,scientific_comparisons=comparison_count,
        independently_reconstructed_derived_fields=derived_fields,
        limitations=["Full-state positivity, full-target norms and node-edge negativity require full VM states.",
          "Full-grid dt, quality and stationarity gates cannot be independently repeated from the reduced export; reconstructed resolution statuses are conditional on those reported gates."])
