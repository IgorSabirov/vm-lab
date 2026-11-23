"""Summaries for the external surveys, preserving galaxies and clusters as units."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
p=Path(__file__).resolve().parent
d=pd.read_csv(p/'little_sample.csv')
q=d.query('status=="tested"')
z=q.delta.to_numpy()
rad=pd.read_csv(p/'little_radial.csv')
def whole_ci(values):
    return np.percentile(np.random.default_rng(143).choice(values,(10000,len(values))).mean(1),[2.5,97.5]).tolist()
errors=(rad.CCC-rad.Vobs)**2/rad.eV.clip(lower=1)**2-(rad.MOND-rad.Vobs)**2/rad.eV.clip(lower=1)**2
assert np.allclose(errors.groupby(rad.Galaxy).mean().sort_index(),q.set_index('Galaxy').delta.sort_index())
assert q.axis_matches.sum()==len(rad)
c=pd.read_csv(p/'cluster_scores.csv')
summary=dict(little=dict(counts=d.status.value_counts().to_dict(),npoints=len(rad),ccc_wins=int((z<0).sum()),
              mean=z.mean(),median=np.median(z),ci=whole_ci(z),
              half_point_changed={k:q.loc[np.sign(q[k])!=np.sign(q.delta),'Galaxy'].tolist() for k in ['delta_shift_minus','delta_shift_plus']},
              max_overlap_arcmin=d.query('status=="overlap"').sep_arcmin.max(),
              min_external_arcmin=d.query('status!="overlap"').sep_arcmin.min()),
          clusters=dict(n=len(c),n_radii=int(c.n.sum()),n_in_band=int(c.n_01_1.sum()),r05_ccc_range=c['CCC_ratio_0.5'].agg(['min','max']).tolist(),
                        r05_mond_range=c['MOND_ratio_0.5'].agg(['min','max']).tolist()))
(p/'external_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
