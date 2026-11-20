"""Name recurrence, fixed path multiplication, and local frame controls only."""
from functools import reduce
from operator import matmul
from pathlib import Path
from runpy import run_path
import json

import sympy as sp

HERE = Path(__file__).resolve().parent
control = run_path(str(HERE.parent / "check_controls.py"))
engine = run_path(str(HERE.parents[1] / "ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py"))
I, T = control["I"], control["T"]
left, right, join = (engine[name] for name in ("left", "right", "join"))


def names_after_steps(steps):
    initial = engine["named"]((1, 2, 12))
    state = initial
    atom = initial[2][0]
    left_branch, right_branch = left(atom), right(atom)
    for n in range(1, steps + 1):
        before = {s: name for name, s in state}
        a, b, c = (before[s] for s in (1, 2, 12))
        state = engine["forward"](state, (1, -1))
        after = {s: name for name, s in state}
        assert after == {1: join(right(right(c)), a),
                         2: join(b, left(left(c))),
                         12: join(right(left(c)), left(right(c)))}
        left_branch, right_branch = right(left_branch), left(right_branch)
        assert after[12] == ("v", left_branch, right_branch)
        assert not engine["equal"](state, initial)
    return steps


def prod(links):
    return reduce(matmul, links, I)


def path_checks():
    a, b = (3*I + 8*T[0])/5, (4*I + 6*T[1])/5
    links = [a, b, (I + 2*sum(T, sp.zeros(2)))/2, a.H, b.H]
    g = prod(links)
    count = 0
    for k, h in enumerate(links):
        pre, post = prod(links[:k]), prod(links[k+1:])
        for gen in T:
            # Exact matrix identities test every matrix element simultaneously.
            d_right = pre*h*gen*post
            d_left = pre*gen*h*post
            for residual in (d_right - g*(post.H*gen*post),
                             d_left - (pre*gen*pre.H)*g):
                assert residual.applyfunc(sp.expand).is_zero_matrix
                count += 1
    return count


def gauge_and_weights():
    turn = 2*T[0]
    assert turn*turn.H == I
    assert turn*T[2]*turn.H == -T[2]
    probe = lambda g: g.trace()/2
    for weight in (sp.S.Zero, sp.S.Half, sp.Integer(2)):
        assert control["derivative"](probe, [I], 0, weight*T[2], 2) == -weight**2/4
    return {"same_endpoint_product": True, "raw_z_signs": [1,-1],
            "weighted_generators": ["0", "1/2", "2"]}


if __name__ == "__main__":
    print(json.dumps({"name_steps_checked": names_after_steps(24),
                      "two_frame_matrix_identities": path_checks(),
                      "gauge_and_weights": gauge_and_weights()}, indent=2))
