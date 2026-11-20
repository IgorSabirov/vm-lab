"""Restart the stiff step at the documented common upper limit of all 12 tables."""
import hashlib
import json
import os
import shutil
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from science import MASSES, OUT, SPECIES, dump, yields

PREVIOUS = (Path(os.environ["GITHUB_WORKSPACE"])/"prior/reproductions/BBN_COSMO_20261120/results/44718056893")


def recover():
    checked = {}
    for line in (PREVIOUS/"MANIFEST.sha256").read_text().splitlines():
        sha, name = line.split("  ",1)
        assert hashlib.sha256((PREVIOUS/name).read_bytes()).hexdigest()==sha, name
        checked[name]=sha
    for name in ("cases","class"):
        shutil.copytree(PREVIOUS/name, OUT/name)
    for name in ("LINX_NATIVE.json","PRIMAT_NATIVE.json","output_background.tsv","output_tables.tsv"):
        shutil.copy2(PREVIOUS/name,OUT/name)
    summary=json.loads((PREVIOUS/"SUMMARY.json").read_text())
    dump(OUT/"CHECKPOINT.json",dict(commit="cbb1050f6d831a6ac1a405c9e984aeffa3f1a2cc",
         run=44718056893, files_verified=len(checked),reused_linx=sorted(k for k in checked if k.endswith("/linx.npz")),
         native_timings_s={k:v for k,v in summary["timings"].items() if "native" in k}))
    return summary["CLASS"]["primat_native"]


def solve(pair,name):
    from validate_contract import validate_input
    p=OUT/"cases"/name
    doc=json.loads((p/"canonical.json").read_text())
    validate_input(doc)
    hist=doc["history"]
    lt,la,lg=[np.log(hist[k]) for k in ("time_s","scale_factor","T_gamma_MeV")]
    with np.load(p/"plasma.npz") as z:
        tw,fw,bw=(z[k].copy() for k in ("weak_T_MeV","n_to_p_s_inv","p_to_n_s_inv"))
        neff=float(z["Neff"][-1])
    rx=doc["rates"]["reactions"]
    assert [r["id"] for r in rx]==pair.names
    grids=[np.asarray(r["T9"]) for r in rx]
    vals=[np.asarray(r["values"]) for r in rx]
    assert all(g[-1]==10. for g in grids)
    with np.load(p/"rate_parameters.npz") as z:
        abc=z["reverse_alpha_beta_gamma"]
    original=p/"linx.npz"
    tight="tight" in name
    rt,at=(3e-9,3e-13) if tight else (2e-8,2e-12)
    seed=p.parent/"baseline"/"linx.npz"
    with np.load(original if original.exists() else seed) as z:
        times=z["time_s"].copy()
        y0=z["Y"][0].copy()
    factor=float(pair.c.kB)*1e9
    threshold=10.*factor
    edge=float(np.exp(np.interp(np.log(threshold), lg[::-1], lt[::-1])))
    limits=(times[0],edge,times[-1])
    def segment_points(i):
        lo,hi=limits[i:i+2]
        take=(times>=lo if i==0 else times>lo)&(times<=hi)
        nodes=np.unique(np.append(times[take]-lo,hi-lo))
        return lo,hi,take,nodes
    # Preserve 14 native full trajectories exactly. Only the three refined
    # trajectories need another LINX solve, using the original frozen tolerances.
    if original.exists():
        with np.load(original) as z:
            lin=z["Y"].copy()
        linx_steps=None
    else:
        import jax.numpy as jp
        from diffrax import ODETerm, Kvaerno3, SaveAt, PIDController, diffeqsolve
        lin=np.empty((len(times),8))
        y=tuple(map(jp.asarray,y0))
        jt,ja,jg=map(jp.asarray,(lt,la,lg))
        tab=list(map(jp.asarray,vals))
        weak_t=jp.asarray(tw)
        weak_f,weak_b=[jp.asarray(v*float(pair.c.tau_n)) for v in (fw,bw)]
        linx_steps=0
        for i in range(2):
            lo,hi,take,nodes=segment_points(i)
            def rhs(s,y,args):
                lnow=jp.log(lo+s)
                temp=jp.exp(jp.interp(lnow,jt,jg))
                # One-sided value of the discontinuity at the restart time.
                temp=(jp.maximum(temp,threshold*(1+1e-14)) if i==0
                      else jp.minimum(temp,threshold*(1-1e-14)))
                rho=pair.rho0*jp.exp(-3*jp.interp(lnow,jt,ja))
                return pair.net(y,temp,rho,weak_t,weak_f,weak_b,rate_tables=tab)
            sol=diffeqsolve(ODETerm(rhs),Kvaerno3(),t0=0.,t1=float(hi-lo),
                    dt0=1e-10 if i==0 else 1e-20, y0=y,
                    saveat=SaveAt(ts=jp.asarray(nodes)),stepsize_controller=PIDController(rtol=rt,atol=at),
                    max_steps=131072)
            block=np.asarray(sol.ys).T
            lin[take]=block[:np.sum(take)]
            y=tuple(jp.asarray(block[-1]))
            linx_steps+=int(sol.stats["num_steps"])
        np.savez_compressed(original,time_s=times,Y=lin,species=SPECIES)
    kernel=pair.pr._K_LT
    traj=np.empty((len(times),8)); y=y0; diagnostics=[]
    for i in range(2):
        lo,hi,take,nodes=segment_points(i)
        def inputs(s):
            u=np.log(lo+s)
            temp=np.exp(np.interp(u,lt,lg))
            T9=temp/factor
            if i==0:
                f=np.zeros(len(rx))
            else:
                T9=min(T9,10.)
                f=np.array([np.interp(T9,g,v,left=0.,right=0.) for g,v in zip(grids,vals)])
            r=np.empty(2+2*len(rx))
            r[:2]=[np.interp(temp,tw,fw),np.interp(temp,tw,bw)]
            r[2::2]=f
            r[3::2]=abc[0]*T9**abc[1]*np.exp(abc[2]/T9)*f
            return pair.rho0*np.exp(-3*np.interp(u,lt,la)),r
        kwargs=dict(fun=lambda s,y:kernel.rhs(y,*inputs(s)),t_span=(0.,hi-lo),y0=y,
                    jac=lambda s,y:kernel.jacobian(y,*inputs(s)),rtol=rt,atol=at*.01,
                    first_step=1e-10 if i==0 else 1e-20,dense_output=True)
        for method in ("BDF","Radau"):
            sol=solve_ivp(method=method,**kwargs)
            diagnostics.append(dict(segment=i,method=method,nfev=sol.nfev,last_elapsed_s=float(sol.t[-1]),
                                    message=sol.message))
            dump(p/"segment_diagnostics.json",diagnostics)
            if sol.success:break
        if not sol.success:
            raise RuntimeError(f"Segment {i}, elapsed {sol.t[-1]}, {sol.message}")
        traj[take]=sol.sol(times[take]-lo).T
        y=sol.y[:,-1]
    np.savez_compressed(p/"primat.npz",time_s=times,Y=traj,species=SPECIES)
    assert all(np.isfinite(x).all() and np.min(x[-1])>=0 for x in (lin,traj))
    result=dict(linx=yields(lin[-1],pair.cfg),primat=yields(traj[-1],pair.cfg), Neff=neff,
                omega_b=float(pair.c.Omegabh2),linx_steps=linx_steps,
                linx_source="44718056893" if linx_steps is None else "segmented_refinement",
                primat_nfev=sum(x["nfev"] for x in diagnostics),rtol=rt,atol_linx=at,
                atol_primat=at*.01,max_baryon_error=max(float(np.max(np.abs(x@MASSES-1))) for x in (lin,traj)))
    result["agreement"]={k:result["primat"][k]/v-1 for k,v in result["linx"].items()}
    result["control_pass"]=(result["max_baryon_error"]<1e-6 and abs(result["agreement"]["Yp"])<1e-4
                           and abs(result["agreement"]["D_H"])<1e-3)
    dump(p/"observables.json",result)
    return result
