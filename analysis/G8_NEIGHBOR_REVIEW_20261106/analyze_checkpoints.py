"""Post-hoc diagnostics of already replicated arrays; no new stochastic runs."""
from pathlib import Path
import json, math
import numpy as np
import pandas as pd

p=Path(__file__).resolve().parent/'replication'
raw=pd.read_csv(p/'RAW_TRAJECTORIES.csv')
out=[];transfers=[];density=[]
for s,d in raw.groupby('scenario',sort=False):
    a=d.pivot(index='trajectory',columns='checkpoint',values='pre_core').to_numpy()
    b=d.pivot(index='trajectory',columns='checkpoint',values='post_core').to_numpy()
    passing=(a>=1).all(1)
    recovery=(b[:,1:6]==0)&(a[:,2:]>0)
    out.append({'scenario':s,'intervals_1to5_empty_core_then_recovered':int(recovery.sum()),
        'lines_with_empty_core_recovery':int(recovery.any(1).sum()),
        'seed_checkpoint_pass_lines_with_empty_core_post_1to5':int((passing&(b[:,1:6]==0).any(1)).sum()),
        'lines_with_any_empty_core_post_1to5':int((b[:,1:6]==0).any(1).sum())})
    for g in range(6):
        current=a[:,g]>=5;both=current&(a[:,g+1]>=5)
        transfers.append({'scenario':s,'from_checkpoint':g,'to_checkpoint':g+1,
           'contains_division_then_recovery':g>0,'current_majority_count':int(current.sum()),
           'joint_majority_probability':float(both.mean()),
           'conditional_next_majority_probability':float(both.sum()/current.sum()) if current.any() else None})
    for gen in (1,6):
        z=d[d.checkpoint==gen];core=float(z.pre_core.mean()/9);outside=float(z.pre_leak.mean()/192)
        density.append({'scenario':s,'checkpoint':gen,'core_density':core,
            'outside_density':outside,'difference_core_minus_outside':core-outside})
(p/'LOCAL_ERASURE_DIAGNOSTICS.json').write_text(json.dumps(out,indent=2)+'\n')
pd.DataFrame(transfers).to_csv(p/'CONDITIONAL_CHECKPOINTS.csv',index=False)
pd.DataFrame(density).to_csv(p/'LOCALIZATION_DENSITY.csv',index=False)
arith={'string_350_KiB_decimal_orders':350*1024*8*math.log10(2),
       'framework_87_KiB_decimal_orders':87*1024*8*math.log10(2),
       'assumed_246_decimal_orders_in_bits':246*math.log2(10),
       'scope':'unit conversions only; no provenance likelihood or physical attempt budget established'}
(p/'ARITHMETIC_CHECK.json').write_text(json.dumps(arith,indent=2)+'\n')
print('Post-hoc diagnostics saved; simulation arrays unchanged.')
