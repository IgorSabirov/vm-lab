"""Recompute review items 1, 3, 4, the measured part of 5 and the full E5 vector."""
import json
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[1] / 'results'


def read(name):
    return json.loads((DATA / (name+'.json')).read_text())


def run():
    coarse, fine, c1, c2 = map(read, ('e6_base','e6_fine','conv_1','conv_2'))
    labels = fine['outputs']
    def outputs(key):
        return np.log([fine['cases'][key][k] for k in labels])
    raw = outputs('zero_contact_pulse') - outputs('zero_contact_off')
    m = np.asarray(fine['intervention_on_mixed_ln'])
    g = np.asarray(fine['intervention_on_graph_interaction_ln'])
    strict = np.asarray(c2['intervention_on_graph_interaction_ln'])
    last = strict - np.asarray(c1['intervention_on_graph_interaction_ln'])
    trajectory = [d['signal']['f1r1']['p_periodic'] for d in (coarse, fine)]
    per_output = {name:dict(raw_ln=raw[j],M_over_raw=m[j]/raw[j],G_over_raw=g[j]/raw[j],
                            strict_G=strict[j],strict_minus_previous=last[j],
                            size_over_step=abs(strict[j]/last[j]))
                  for j,name in enumerate(labels)}
    weak = read('weak_refined')
    return {'per_output':per_output,'p_peak':[row['peak']['value'] for row in trajectory],
            'p_final':[row['final'] for row in trajectory],
            'max_abs_prescribed_minus_live_ln':max(abs(z) for a in fine['prescribed_minus_live_ln'].values() for z in a),
            'E5_delayed_minus_matched':{k:val['delayed_minus_matched'] for k,val in weak.items() if k.endswith('_comparison')}}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,allow_nan=False))
