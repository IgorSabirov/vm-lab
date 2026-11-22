"""Exact checks of the new observation windows on the original R141 fixtures."""
from ast import literal_eval
import json
from pathlib import Path
import sys

import sympy as sp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'donor_replay'))
from experiments import ring
from previous import by_length, effects


def ring_filters(t):
    source = json.loads((ROOT / 'donor_replay/results.json').read_text())
    data = {}
    polynomials = []
    averages = []
    for word, det_at_one, traces in source['binary']['first']:
        d, shift = ring(len(word))
        shift = sp.Matrix(shift)
        p = sp.diag(*map(int, word))
        b = p * sp.Matrix(d) * p
        k = b*b.T
        averages.append(sum((shift**i*k*(shift.T)**i for i in range(k.rows)), sp.zeros(k.rows))/k.rows)
        polynomial = (sp.eye(k.rows) + t*k).det().expand()
        assert polynomial.subs(t, 1) == det_at_one
        assert [sp.trace(k**i) for i in range(1, 4)] == traces[:3]
        polynomials.append(polynomial)
        data[word] = str(polynomial)
    average = sp.eye(6) - (shift + shift.T)/3
    assert averages[0] == averages[1] == average
    shifted = average - sp.eye(6)/3
    eigenvalues = shifted.eigenvals()
    assert all(e >= 0 for e in eigenvalues) and eigenvalues[0] == 1
    kernel = shifted.nullspace()[0]
    z = sp.Symbol("z")
    kernel_polynomial = sum(c*z**i for i, c in enumerate(kernel))
    assert sp.expand((z-1)*kernel_polynomial) == z**6-1
    f, g = polynomials
    delta = sp.factor(f-g)
    resolvent_difference = sp.factor(t*(sp.diff(g,t)/g-sp.diff(f,t)/f))
    blind = (3+sp.sqrt(21))/2
    assert delta == t**3 and resolvent_difference.subs(t,blind).simplify() == 0
    assert resolvent_difference.subs(t,1) == -sp.Rational(1,26)
    return dict(determinants=data, difference=str(delta), resolvent_difference=str(resolvent_difference),
                positive_blind_scale=str(blind), resolvent_difference_at_one='-1/26',
                toeplitz=dict(common_minimum='1/3', shifted_rank=shifted.rank(),
                kernel_polynomial=str(kernel_polynomial), equal_after_cyclic_average=True))


def length_filters():
    readings = by_length(effects())
    # Fixed windows, chosen without optimizing their conditioning.
    scales = [sp.Rational(1,j) for j in (2,3,4)]
    weights = sp.Matrix([[u**n for n in range(1,6)] for u in scales])
    coherent = sp.Matrix([readings[n] for n in range(1,6)])
    joint = json.loads((ROOT / "donor_replay/followup.json").read_text())["intermediate"]["effects_joint"]
    marked = sp.zeros(5,4)
    for key,row in joint.items():
        _, n = literal_eval(key)
        marked[n-1,:] += sp.Matrix([[sp.Rational(x) for x in row]])
    variable = sp.factor((weights*coherent[:,1:]).det())
    after = weights*marked[:,1:]
    assert variable == -sp.Rational(13,7247757312)
    assert after.rank() == 2 and after[:,0] == sp.zeros(3,1)
    return dict(windows=list(map(str,scales)), variable_columns=['x','y','z'],
                coherent_determinant=str(variable), coherent_rank=3,
                recorded_rank=after.rank(), recorded_null_direction=['1','0','0'])


if __name__ == '__main__':
    print(json.dumps(dict(rings=ring_filters(sp.Symbol('t')), lengths=length_filters()), indent=2))
