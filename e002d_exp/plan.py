"""Frozen E002d v003 cases; identities include every varied physical parameter."""
import hashlib
import json
VERSION="E002d-v003"
MODELS=("QS","RR_QS")
EPSILON_GRID=(-.5,-.25,-.125,-.0625,0.,.0625,.125,.25,.5)
CENTRAL_GRID=(-.125,0.,.125)
TARGETS={"S2a":(2,5,6),"S2b":(4,3,6),"S1a":(2,1,2),"S1b":(4,1,4),
         "M2a":(6,5,6),"M2b":(6,3,6),"M1a":(6,1,2),"M1b":(6,1,4)}
OPERATIONS={**{k:(k,) for k in ("S2a","S2b","S1a","S1b")},
            "S2":("S2a","S2b"),"S1":("S1a","S1b"),"M2":("M2a","M2b"),"M1":("M1a","M1b")}
CONTRACT=dict(version=VERSION,source_physics_commit="29fe4496485c17e935b2e2ffa9c88b7d75ba6efe",
 primary_dose=.1,secondary_doses=[.05,.2],primary_delta=.125,secondary_deltas=[.0625,.25],
 probability_floor=1e-6,maximum_relative_denominator_uncertainty=.1,
 primitive_absolute_floor=1e-8,resolution_multiplier=10.,
 stationarity=dict(rhs=1e-7,drift=1e-6,flux_absolute=1e-8,flux_relative=1e-5),
 physicality=dict(trace=1e-10,hermiticity=1e-10,minimum_eigenvalue=-1e-8),
 refinement=dict(absolute=1e-6,relative=1e-4),operator_tolerance=1e-12,
 structure_absolute=1e-6,structure_relative=.01,horizons=[200.,400.],
 extension_rule="ALL_184_TO_400_IF_ANY_T200_STATIONARITY_FAILS",
 primary_A=["E","S"],primary_B=["D_delta_0.125","CENTER_BELOW_BOTH_SAMPLED_NEIGHBORS"],
 primary_C=["D_T_minus_D_C","QS_minus_RR_of_D_T_minus_D_C"],
 composition="sum_of_independent_dissipators",automatic_Fano_label=False,minimum_suppression_required=None,
 uncertainty="u=1e-8+10*(abs(fine_mean-coarse_mean)+max(fine_window_range,coarse_window_range)); interval propagation; engineering envelope, not significance or rigorous total-error bound",
 report=dict(maximum_bytes=30*1024**2,maximum_files=500,maximum_file_bytes=8*1024**2,
 series="0:.2:10 then multiples of 4; exact final and T200 windows at step 2",
 diagnostics="0:2:20 then multiples of 4; full-grid extrema before sampling",
 case_format="one .npz.xz per case: XZ around stored NPZ, NPY Fortran layout; compressed/payload hashes and bounded decoder; all bits retained; full states/full grids stay on VM"))

def physics_key(c,include_dt=True):
    fields=("model","phi_over_pi","detuning","dephasing","target","kind","gamma")
    return tuple(c[k] for k in fields)+((c["dt"],) if include_dt else ())

def case(model,target="base",kind="base",gamma=0.,dt=.005,horizon=200.,phi=0.,epsilon=0.,noise=.05):
    c=dict(model=model,target=target,kind=kind,gamma=float(gamma),dt=float(dt),horizon=float(horizon),
           phi_over_pi=float(phi),detuning=float(epsilon),dephasing=float(noise),family=VERSION)
    c["id"]=("Q" if model=="QS" else "R")+"_"+hashlib.sha256(json.dumps(physics_key(c),separators=(",",":")).encode()).hexdigest()[:12]
    return c

def cases(mode="production"):
    unique={}
    def add(block,model,target="base",kind="base",gamma=0.,dt=.005,phi=0.,epsilon=0.,noise=.05):
        c=case(model,target,kind,gamma,dt,phi=phi,epsilon=epsilon,noise=noise);k=physics_key(c)
        if k not in unique:unique[k]=dict(c,blocks=[])
        if block not in unique[k]["blocks"]:unique[k]["blocks"].append(block)
    for model in MODELS:
        for dt in (.005,.01):
            add("A",model,dt=dt)
            for target in ("S2a","S2b","S1a","S1b"):
                for kind in ("T","C"):add("A",model,target,kind,.1,dt)
            for target in ("S2","S1"):
                for gamma in ((.05,.1,.2) if dt==.005 else (.1,)):
                    for kind in ("T","C"):add("A",model,target,kind,gamma,dt)
        for noise in (.05,.25):
            for dt in (.005,.01):
                for epsilon in (EPSILON_GRID if dt==.005 else CENTRAL_GRID):
                    add("B",model,dt=dt,phi=.5,epsilon=epsilon,noise=noise)
                for epsilon in CENTRAL_GRID:add("B",model,dt=dt,phi=0.,epsilon=epsilon,noise=noise)
        for dt in (.005,.01):
            for epsilon in CENTRAL_GRID:
                add("C",model,dt=dt,phi=.5,epsilon=epsilon)
                for target in ("M2","M1"):
                    for kind in ("T","C"):add("C",model,target,kind,.1,dt,phi=.5,epsilon=epsilon)
    out=list(unique.values())
    for i,c in enumerate(out):c["label"]=f"C{i:03d}"
    if mode=="production":return out
    if mode=="calibration":
        selected=[]
        for c in out:
            a=(c["phi_over_pi"]==0 and c["detuning"]==0 and c["dephasing"]==.05 and
               (c["target"]=="base" or (c["target"] in ("S2a","S2","S1") and c["gamma"]==.1)))
            b=(c["phi_over_pi"]==.5 and c["detuning"]==.125 and c["dephasing"]==.25 and c["target"]=="base")
            d=(c["phi_over_pi"]==.5 and c["detuning"]==.125 and c["dephasing"]==.05 and c["target"] in ("M1","M2"))
            if a or b or d:selected.append(dict(c,horizon=10.))
        return selected
    if mode=="smoke":
        requests=[("QS","S2","T",0.,0.,.05),("QS","M1","C",.5,.125,.05),
                  ("RR_QS","S1a","C",0.,0.,.05),("RR_QS","M2","T",.5,-.125,.05),
                  ("RR_QS","base","base",.5,.125,.25)]
        return [dict(c,horizon=2.) for c in out if
                (c["model"],c["target"],c["kind"],c["phi_over_pi"],c["detuning"],c["dephasing"]) in requests
                and (c["target"]=="base" or c["gamma"]==.1)]
    raise ValueError("Unknown mode: "+mode)

def counts(mode,horizon=None):
    cs=cases(mode);steps=sum(round((c["horizon"] if horizon is None else horizon)/c["dt"]) for c in cs)
    return dict(trajectories=len(cs),steps=steps,rhs_calls=4*steps)

def comparison_graph():
    cs=cases();by={physics_key(c):c for c in cs};edges=[]
    for c in cs:
        if c["dt"]==.005 and physics_key(dict(c,dt=.01)) in by:
            edges.append(dict(kind="dt",members=[c["id"],by[physics_key(dict(c,dt=.01))]["id"]]))
        if c["kind"]=="T":
            ks=[c,dict(c,kind="C"),dict(c,target="base",kind="base",gamma=0.)]
            edges.append(dict(kind="T_C_baseline",members=[by[physics_key(x)]["id"] for x in ks]))
        if c["model"]=="QS":
            edges.append(dict(kind="QS_RR",members=[c["id"],by[physics_key(dict(c,model="RR_QS"))]["id"]]))
        if c["detuning"]==0 and ("B" in c["blocks"] or "C" in c["blocks"]):
            trio=[dict(c,detuning=e) for e in CENTRAL_GRID]
            if all(physics_key(x) in by for x in trio):
                edges.append(dict(kind="epsilon_triple",members=[by[physics_key(x)]["id"] for x in trio]))
    return dict(extension_cohorts=[[c["id"] for c in cs]],edges=edges)

CALIBRATION_FORECAST=dict(expected_seconds=180.,lower_seconds=60.,upper_seconds=480.,
 source="Verified E002d_CAL_v003_r001 process156.935s for48cases/72000steps; same evolution plus whole-caseXZ packaging and bounded decoding;180s forecast with60–480s range before r002")
