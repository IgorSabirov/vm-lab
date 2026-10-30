"""Pinned physical generator plus independent diagonal intervention channels."""
import numpy as np
from scipy import sparse as sp
from e002_exp.model import clean,maxabs
from e002c_exp.model import build as base_build,operators
from .plan import TARGETS,OPERATIONS
MONITORS=TARGETS
NUMBERS=np.array([i.bit_count() for i in range(8)])

def jump_diagonals(target,kind,gamma):
    if target=="base":
        if kind!="base" or gamma!=0:raise ValueError("Invalid baseline")
        return []
    if target not in OPERATIONS or kind not in ("T","C") or not np.isfinite(gamma) or gamma<0:
        raise ValueError("Invalid intervention")
    result=[]
    for key in OPERATIONS[target]:
        mask,a,b=TARGETS[key];node=np.zeros(8);node[a]=1;node[b]=-1 if kind=="T" else 1
        result.append((key,np.sqrt(gamma)*np.kron(node,(operators()["mask_id"]==mask).astype(float))))
    return result

def damping(diagonals):
    rates=np.zeros((216,216))
    for _,d in diagonals:rates+=.5*(d[:,None]-d[None,:])**2
    return rates

def consequence_map(with_arrays=False):
    result={};arrays={}
    for target,keys in OPERATIONS.items():
        t=damping(jump_diagonals(target,"T",1.));c=damping(jump_diagonals(target,"C",1.))
        expected=np.zeros_like(t);target_rows=[]
        for key in keys:
            mask,a,b=TARGETS[key];edge=np.flatnonzero(operators()["mask_id"]==mask)
            ia=a*27+edge;ib=b*27+edge
            expected[np.ix_(ia,ib)]+=2.;expected[np.ix_(ib,ia)]+=2.
            target_rows.append(dict(target=key,T=float(t[ia[0],ib[0]]),C=float(c[ia[0],ib[0]])))
        error=float(np.max(abs(t-c-expected)))
        result[target]=dict(gamma=1.,difference_error=error,targets=target_rows,
             changed_matrix_entries=int(np.count_nonzero(expected)),
             population_damping=float(max(abs(t.diagonal()).max(),abs(c.diagonal()).max())),
             independent_jump_count=len(keys))
        arrays[target+"_T"]=t;arrays[target+"_C"]=c;arrays[target+"_difference"]=t-c
        if error>1e-12:raise ValueError("Unmatched collateral")
    return (result,arrays) if with_arrays else result

def extra_observables(model):
    names=[];ops=[];o=operators();h=model["currents"][1]+model["currents"][2]
    for m in range(8):
        for n in range(4):
            p=sp.kron(sp.diags((NUMBERS==n).astype(float)),o["masks"][m],format="csr")
            names.append(f"p_m{m}_N{n}");ops.append(p)
            for tag,op in [("h",h),*zip(("I01","I12","I02"),model["currents"])]:
                names.append(f"{tag}_m{m}_N{n}");ops.append(clean(p@op))
    for key,(m,a,b) in TARGETS.items():
        node=np.zeros((8,8),complex);node[b,a]=1
        op=sp.kron(node,o["masks"][m],format="csr")
        names.extend([f"C_{key}_re",f"C_{key}_im"]);ops.extend([clean((op+op.getH())/2),clean((op-op.getH())/(2j))])
        support=np.zeros(8);support[[a,b]]=1
        names.append("aunit_"+key);ops.append(sp.kron(sp.diags(support),o["masks"][m],format="csr"))
    activity=0*o["eye"]
    for _,jump in model["jumps"]:
        # Only intervention jumps are counted in this dedicated activity.
        if _.startswith("selective_"):activity+=jump.getH()@jump
    names.append("activity_added");ops.append(clean(activity))
    rows=sp.vstack([sp.csr_matrix(op.T.toarray().reshape(1,-1,order="F")) for op in ops],format="csr")
    return names,rows

def build(case,alpha=None):
    if alpha is not None or case["model"] not in ("QS","RR_QS"):raise ValueError("E002d scope is QS/RR")
    model=base_build(case)
    ds=jump_diagonals(case["target"],case["kind"],float(case["gamma"]))
    rates=damping(ds);addition=-sp.diags(rates.reshape(-1,order="F"),format="csr")
    model["L"]=clean(model["L"]+addition)
    model["jumps"] += [(f"selective_{key}_{case['kind']}",sp.diags(d,format="csr")) for key,d in ds]
    names,rows=extra_observables(model)
    model["rows"]=sp.vstack([model["rows"],rows],format="csr");model["names"]+=names
    model["checks"].update(selective_population_damping=float(abs(rates.diagonal()).max()),
        selective_trace=float(maxabs(sp.csr_matrix(np.eye(216).reshape(1,-1,order="F"))@addition)),selective_H_change=0.)
    if max(model["checks"].values())>1e-10:raise ValueError("Operator identity failed")
    return model
