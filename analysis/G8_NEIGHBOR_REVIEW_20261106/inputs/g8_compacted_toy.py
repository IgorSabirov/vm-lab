"""Explicit schematic contact-domain stress test for the G8-derived subcase.
This does NOT use the polymer-derived Pc matrix from Supplementary Fig. S9A.
It uses Pc=1 within the predeclared 9-site core, and Pc=eta/|i-j| otherwise.
This is only a sensitivity probe of the *direction* of the 3D-compaction effect.
"""
from pathlib import Path
import json, math, hashlib, platform
import numpy as np, pandas as pd
from g8_subcase import run_one, N, CENTER, CORE, K0, K, EPS, NE0, KB_OVER_KU, TCYC, NCYCLES, PARTIAL_KEEP_PROB, B0, KSYN, KDEG, THRESHOLD, wilson

ETA_OUT = 0.05
NTRAJ = 100
SEED0 = 20261106 + 500000

def make_compact_kernel():
    lo = CENTER - CORE//2
    hi = lo + CORE
    Kmat = np.zeros((N,N), dtype=np.float64)
    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            if lo <= i < hi and lo <= j < hi:
                Kmat[i,j] = 1.0
            else:
                Kmat[i,j] = ETA_OUT / abs(i-j)
    return Kmat


def main(outdir):
    out=Path(outdir); out.mkdir(parents=True,exist_ok=True)
    ker=make_compact_kernel()
    scenarios=[
        ("C1_compact_core_RW_on",0,False,False),
        ("C5_compact_core_apparatus_A_on",0,True,True),
        ("C5_control_compact_core_A_off",0,True,False),
    ]
    rows=[]; raw={}
    for s_idx,(name,mode,dynamic,app_on) in enumerate(scenarios):
        vals=[]
        for rep in range(NTRAJ):
            vals.append(run_one(SEED0+s_idx*100000+rep,mode,dynamic,app_on,ker,N,CENTER,CORE,K0,K,EPS,NE0,KB_OVER_KU,TCYC,NCYCLES,PARTIAL_KEEP_PROB,B0,KSYN,KDEG,THRESHOLD))
        pre_core=np.stack([x[0] for x in vals]); pre_total=np.stack([x[1] for x in vals]); pre_leak=np.stack([x[2] for x in vals]); pre_enz=np.stack([x[3] for x in vals]); pre_bud=np.stack([x[4] for x in vals])
        post_core=np.stack([x[5] for x in vals]); post_total=np.stack([x[6] for x in vals]); post_leak=np.stack([x[7] for x in vals]); post_enz=np.stack([x[8] for x in vals]); post_bud=np.stack([x[9] for x in vals])
        raw[name]={"pre_core":pre_core,"pre_total":pre_total,"pre_leak":pre_leak,"pre_enzymes":pre_enz,"pre_budget":pre_bud,"post_core":post_core,"post_total":post_total,"post_leak":post_leak,"post_enzymes":post_enz,"post_budget":post_bud}
        for g in range(NCYCLES+1):
            if g<NCYCLES:
                maj=(pre_core[:,g]>=THRESHOLD)&(pre_core[:,g+1]>=THRESHOLD)
                seed=(pre_core[:,g]>=1)&(pre_core[:,g+1]>=1)
                qm=float(maj.mean()); qs=float(seed.mean())
                lm,hm=wilson(int(maj.sum()),NTRAJ); ls,hs=wilson(int(seed.sum()),NTRAJ)
            else: qm=qs=lm=hm=ls=hs=float('nan')
            rows.append({"scenario":name,"generation":g,"mean_core_M_predivision":float(pre_core[:,g].mean()),"mean_core_M_postdilution":float(post_core[:,g].mean()),"mean_total_M_predivision":float(pre_total[:,g].mean()),"mean_outside_core_M_predivision":float(pre_leak[:,g].mean()),"mean_HME_count_predivision":float(pre_enz[:,g].mean()),"mean_precursor_remaining_predivision":float(pre_bud[:,g].mean()),"q_majority_predivision_and_next_transfer":qm,"q_majority_CI95_low":lm,"q_majority_CI95_high":hm,"q_seed_predivision_and_next_transfer":qs,"q_seed_CI95_low":ls,"q_seed_CI95_high":hs,"n_trajectories":NTRAJ})
    df=pd.DataFrame(rows); df.to_csv(out/'G8_COMPACTED_TOY_SUMMARY.csv',index=False)
    np.savez_compressed(out/'G8_COMPACTED_TOY_RAW.npz',**{f'{name}__{fld}':a for name,d in raw.items() for fld,a in d.items()})
    np.save(out/'G8_COMPACTED_TOY_KERNEL.npy',ker)
    script_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    meta={"not_published_Pc_matrix":True,"Pc_definition":"1.0 for distinct pairs both within central 9-site core; 0.05/|i-j| for all other pairs","eta_out":ETA_OUT,"parameters":{"N":N,"core":CORE,"k_over_k0":K/K0,"epsilon":EPS,"Ne":NE0,"kb_over_ku":KB_OVER_KU,"Tcyc":TCYC,"cycles":NCYCLES,"trajectories":NTRAJ,"k_syn":KSYN,"enzyme_half_life":TCYC,"B0":B0,"apparatus_A_fixed":True},"seed_base":SEED0,"script_sha256":script_sha,"python":platform.python_version(),"numpy":np.__version__}
    (out/'G8_COMPACTED_TOY_METADATA.json').write_text(json.dumps(meta,indent=2))
    print(df[df.generation<NCYCLES][["scenario","generation","mean_core_M_predivision","mean_core_M_postdilution","mean_total_M_predivision","mean_outside_core_M_predivision","mean_HME_count_predivision","mean_precursor_remaining_predivision","q_majority_predivision_and_next_transfer","q_seed_predivision_and_next_transfer"]].to_string(index=False))
    print('script_sha256:',script_sha)

if __name__=='__main__':
    import sys
    main(sys.argv[1] if len(sys.argv)>1 else '/mnt/data/G8_COMPACTED_TOY')
