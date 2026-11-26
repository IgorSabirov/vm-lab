"""Exact zero-phase graph index of D=1-F, independently from the sign-kernel and from orbit modes."""
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'physical_audit'))
from replay import four_words, restrict_map, orbits, reverse_channels, rewrite, canonical, active


def counts(f):
    t = {w: canonical(rewrite(reverse_channels(w))) for w in f}
    assert all(t[t[w]] == w and t[f[t[f[w]]]] == w for w in f)
    # For H_1=-TF, H_1^2=1.  sign(H_1) is exactly -TF.
    trace_t = sum(w == t[w] for w in f)
    trace_tf = sum(w == t[f[w]] for w in f)
    cycles = orbits(f)
    # The zero-phase space consists of vectors constant on each cycle.
    # Reflection permutes those vectors and fixes precisely the setwise invariant cycles.
    trace_on_zero = sum(t[c[0]] in c for c in cycles)
    assert 2 * trace_on_zero == trace_t + trace_tf
    even = (len(cycles) + trace_on_zero) // 2
    odd = len(cycles) - even
    assert even - odd == trace_on_zero
    alt={w:f[t[w]] for w in f}
    assert all(alt[alt[w]]==w for w in f)
    assert sum(alt[c[0]] in c for c in cycles)==trace_on_zero
    pi_cycles=[c for c in cycles if len(c)%2==0]
    def pi_trace(reflection):
        return sum((-1)**c.index(reflection[c[0]]) for c in pi_cycles if reflection[c[0]] in c)
    pi_t,pi_ft=pi_trace(t),pi_trace(alt)
    assert pi_t==-pi_ft
    checks={}
    if len(f)<=130:
        words=sorted(f);lookup={w:i for i,w in enumerate(words)}
        def permutation(mapping):
            mat=np.zeros((len(f),len(f)))
            for i,w in enumerate(words): mat[lookup[mapping[w]],i]=1
            return mat
        F=permutation(f); Gamma=permutation(t); ident=np.eye(len(f))
        for m in (.25,1.,1.75):
            H=Gamma@((1-m)*ident-F)
            assert np.array_equal(H,H.T)
            eig,U=np.linalg.eigh(H)
            sign=(U*np.sign(eig))@U.T
            D=ident+Gamma@sign
            gap=float(min(abs(eig)))
            assert gap+2e-12>=1-abs(1-m)
            assert np.linalg.norm(Gamma@D+D@Gamma-D@Gamma@D)<1e-10
            measured=float(np.trace(Gamma@(ident-D/2)))
            assert abs(measured-trace_on_zero)<1e-10
            checks[str(m)]={'min_abs_H':gap,'index_from_matrix':measured}
    return dict(alternate_grading_zero_index=trace_on_zero,pi_trace_T=pi_t,pi_trace_FT=pi_ft,
                kernel_mass_scan=checks,dimension=len(f), trace_T=trace_t, trace_TF=trace_tf,
                zero_even=even, zero_odd=odd, index=trace_on_zero, pairs=min(even,odd))


def run():
    output = {}
    for size in range(3,16,2):
        f = restrict_map(four_words(size))
        a = {w:v for w,v in f.items() if active(w)}
        b = {w:v for w,v in f.items() if not active(w)}
        output[size] = {k:counts(m) for k,m in [('full_fixed_length_core',f),('active',a),('passive',b)]}
        assert [row['index'] for row in output[size].values()] == [3,2,1]
    return output


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
