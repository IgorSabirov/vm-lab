"""Read exact published histories and check the review against the named transition."""
import argparse
from collections import Counter
from fractions import Fraction
from itertools import combinations
import json
from math import atan, cos, degrees, pi, sin, sqrt
from pathlib import Path
from runpy import run_path

import numpy as np

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
A = (3,3,3,2,2,2,2,2)
B = (2,2,2,2,3,3,3,2)


def readout():
    data = json.loads((PARENT/'HISTORIES.json').read_text())
    assert data['angle_pi_units'] == '1/4' and data['index_base'] == 0
    rows = data['branches']
    paths = [tuple(r['lengths']) for r in rows]
    n = len(data['named_endpoints'])
    assert (len(rows), n) == (92, 40)
    re, im = (np.zeros((len(rows), n), dtype=np.int64) for _ in range(2))
    for i, row in enumerate(rows):
        for end, x, y in row['amplitudes']:
            re[i,end] += x
            im[i,end] += y
    gram = re @ re.T + im @ im.T
    denom = 256
    assert gram.trace() == gram.sum() == denom
    i, j = paths.index(A), paths.index(B)
    assert np.flatnonzero(re[:,19]**2+im[:,19]**2).tolist() == [j,i]
    assert (re[i,19],im[i,19],re[j,19],im[j,19]) == (-1,1,1,-1)
    coherent = re.sum(axis=0)**2 + im.sum(axis=0)**2
    recorded = (re**2+im**2).sum(axis=0)
    dark = np.flatnonzero((coherent==0)&(recorded>0))
    assert list(dark) == [10,15,17,19] and all(recorded[dark] == 4)
    dark_rows = {int(k):np.flatnonzero(re[:,k]**2+im[:,k]**2).tolist() for k in dark}
    # Measurement at step 1. Coarse readout in units of two sites, same additive offset.
    def contrast(length,shift):
        return (length+shift)-(2*((length+1)//2)+shift)
    bins = np.array([contrast(path[0], 0) for path in paths])
    assert all(contrast(p[0],7)==v for p,v in zip(paths,bins))
    assert set(bins) == {-1,0}
    first, second = np.flatnonzero(bins==-1), np.flatnonzero(bins==0)
    cross = lambda matrix: 2 * int(matrix[np.ix_(first,second)].sum())
    end = np.outer(re[:,19],re[:,19])+np.outer(im[:,19],im[:,19])
    assert cross(gram)==0 and cross(end)==-4 and cross(np.diag(np.diag(end)))==0
    total_variation = Fraction(int(abs(coherent-recorded).sum()), 2*denom)
    paircounts = Counter(int(np.sign(gram[a,b])) for a,b in combinations(range(len(rows)),2))
    assert total_variation == Fraction(11, 64)
    assert paircounts == {-1: 56, 0: 4075, 1: 55}
    return dict(histories=len(rows), endpoints=n, witness_rows=[i,j], endpoint_19_numerators=[[-1,1],[1,-1]],
                dark_rows=dark_rows, recorded_mass_four=str(Fraction(int(recorded[dark].sum()),denom)),
                coherent_mass_four="0", endpoint_total_variation=str(total_variation),
                pair_sign_counts={str(k):v for k,v in sorted(paircounts.items())},
                toy_I2_unselected="0", toy_I2_joint_endpoint_19="-1/64", toy_I2_recorded="0")


def follow(ops, path):
    g = ops['rooted'](ops['E']['named']((1,2,0)))
    decisions = []
    for observed in path:
        stay, flip = ops['alternatives'](g)
        if stay == flip:
            assert len(stay) == observed
            decisions.append('idle')
            g=stay
        else:
            assert (len(stay)==observed) != (len(flip)==observed)
            if len(flip)==observed:
                decisions.append('flip'); g=flip
            else:
                decisions.append('stay'); g=stay
    return decisions,g


def angular(ops):
    paths = [follow(ops,path) for path in [A,B]]
    assert paths[0][1] == paths[1][1]
    counts = [dict(Counter(decisions)) for decisions,_ in paths]
    assert counts == [dict(idle=1,flip=1,stay=6),dict(idle=1,flip=3,stay=4)]
    optimum=atan(sqrt(2/5))
    rows=[]
    initial=ops['E']['named']((1,2,0))
    for theta in (0, pi/8, optimum, pi/4, 0.93, pi/2):
        a,b = [ops['projected_vectors'](initial,path,theta) for path in (A,B)]
        c,s=cos(theta),sin(theta)
        weights=[s*s*c**12,s**6*c**8,-2*s**4*c**10,s*s*c**8*cos(2*theta)**2]
        actual=[np.vdot(a,a).real,np.vdot(b,b).real,2*np.vdot(a,b).real,np.vdot(a+b,a+b).real]
        np.testing.assert_allclose(actual,weights,atol=1e-12,rtol=0)
        rows.append([round(degrees(theta),8),*[round(x,12) for x in weights]])
    return dict(path_actions=[p[0] for p in paths], opt_angle_degrees=round(degrees(optimum),10),
                optimum_abs_I2=str(2*Fraction(2,7)**2*Fraction(5,7)**5), angles_and_weights=rows)


def refinement(ops):
    model=ops['E']
    coarse=model['named']((1,2,0))
    fine=(coarse[0],(('atom',3),0),*coarse[1:])
    assert len(model['interact'](coarse,(1,-1)))==2
    assert model['equal'](model['interact'](fine,(1,-1)),fine)
    assert tuple(map(len,ops['alternatives'](coarse)))==(3,2)
    assert tuple(map(len,ops['alternatives'](fine)))==(4,4)
    return dict(input=[1,2,0], inserted_label=0, fine_labels=[1,0,2,0],
                coarse_event_length=2, corresponding_fine_length=3,
                coarse_weight="sin(theta_coarse)^2", fine_weight="0")


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoints-only", action="store_true",
                        help="Audit the integer history table without importing the graph engine.")
    args = parser.parse_args()
    results = {"endpoints": readout()}
    if not args.endpoints_only:
        operators = run_path(str(PARENT / "verify.py"))
        results.update(angles=angular(operators), refinement=refinement(operators))
    print(json.dumps(results, indent=2))
