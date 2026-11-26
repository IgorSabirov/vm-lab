"""Exact R140/H6–R135 controls. Run with Python 3 and SymPy, from any directory."""
import ast
import json
from pathlib import Path
import sys

import sympy as sp

HERE = Path(__file__).resolve().parent
DONOR = HERE.parents[1] / "R141_RIEMANN_CORPUS/donor_replay"
sys.path.insert(0, str(DONOR))
import check_h6 as histories
import previous as h6

ONE = sp.eye(3)
M = ONE[:, [1, 2, 0]]
J = ONE[:, [0, 2, 1]]
e0 = ONE[:, 0]
A_PATH = (3, 3, 3, 2, 2, 2, 2, 2)
B_PATH = (2, 2, 2, 2, 3, 3, 3, 2)


def path_operator(lengths, inversion=J):
    result = ONE
    for length in lengths:
        gate = {2: M, 3: inversion}.get(length, ONE)
        result = gate * result
    return result


def interference():
    # The published path engine rebuilds the 8-step histories and checks the
    # complete amplitude table. Determine the two arms by their length words.
    checked = histories.witness()
    table = json.loads((HERE.parent / "HISTORIES.json").read_text())
    assert table == histories.table and table["amplitude_denominator"] == "sqrt(256)"
    arms = {}
    for row in table["branches"]:
        for endpoint, real, imag in row["amplitudes"]:
            if endpoint == 19:
                arms[tuple(row["lengths"])] = (real + sp.I * imag) / 16
    assert set(arms) == {A_PATH, B_PATH}
    a, b = arms[A_PATH], arms[B_PATH]
    arm_weight = abs(a)**2
    cross = sp.simplify(sp.conjugate(b) * a)
    assert arm_weight == abs(b)**2 == -cross == sp.Rational(1, 128)
    def port(s):
        return 2 * arm_weight + 2 * sp.re(cross * s)
    eta = sp.Symbol("eta", real=True)
    defect = sp.simplify(port(eta) - 2 * arm_weight)
    assert defect == -eta / 64
    # Normalized Haar on Z3 and f(h)=(1+h)/sqrt(2).
    sector = sp.Rational(1, 3) * (2 / sp.sqrt(2))**2
    joint = sector * defect.subs(eta, 1)
    assert joint == -sp.Rational(1, 96) and joint / sector == -sp.Rational(1, 64)
    return {"histories": checked["histories"], "endpoints": checked["graphs"],
            "amplitudes_19": [str(a), str(b)], "arm_weight": str(arm_weight),
            "I2_eta": str(defect), "P19": {str(s): str(port(s)) for s in [1, 0, -1, sp.I]},
            "P_h1": str(sector), "I2_joint_h1": str(joint),
            "I2_conditional_h1": str(joint / sector)}


def transport():
    ua, ub = map(path_operator, (A_PATH, B_PATH))
    rel = ub.H * ua
    assert M**3 == J**2 == ONE and J*M*J == M.inv()
    assert (ua, ub) == (M**5 * J**3, M * J**3 * M**4)
    assert rel == M and ua * e0 == ONE[:, 2] and ub * e0 == e0
    assert M.det() == (-J).det() == 1 and J.det() == -1
    ua_su, ub_su = (path_operator(path, -J) for path in (A_PATH, B_PATH))
    assert ua_su == -ua and ub_su == -ub and ub_su.H * ua_su == rel
    # Non-square isometries give identity only on the physical endpoint space.
    wi = ONE.col_join(sp.zeros(1, 3))
    wf = (M*J).col_join(sp.zeros(2, 3))
    paths = []
    for middle in (M.col_join(sp.zeros(1, 3)), J.col_join(sp.zeros(3, 3))):
        paths.append((wf * middle.H) * (middle * wi.H))
    assert paths[0] == paths[1] == wf * wi.H
    assert paths[1].H * paths[0] == wi * wi.H
    assert wi.H * paths[1].H * paths[0] * wi == ONE
    assert wi * wi.H != sp.eye(wi.rows)

    # Holding the endpoint fixed, ask whether the two field density operators differ.
    # The mixed-state interference uses Tr(rho U_B^dagger U_A), not the distance.
    pure = e0 * e0.H
    fixed = sp.ones(3, 1) / sp.sqrt(3)  # h=1 in the character basis
    controls = {}
    for name, rho in [("e0", pure), ("I/3", ONE/3), ("h=1", fixed*fixed.H)]:
        delta = ua*rho*ua.H - ub*rho*ub.H
        distance = sum(abs(val)*n for val, n in delta.eigenvals().items())/2
        s = sp.trace(rho*rel)
        assert sp.trace(rho*M**2) == sp.conjugate(s)
        controls[name] = [str(s), str(distance), str((1-sp.re(s))/64)]
    assert controls == {"e0": ["0","1","1/64"], "I/3": ["0","0","1/64"],
                        "h=1": ["1","0","0"]}
    atom_counts = h6.shape_counts()
    assert {tuple(lengths): total for lengths, counts, total in atom_counts} == {A_PATH: 3, B_PATH: 5}
    return {"flat_physical_relative": [[int(x) for x in row] for row in ONE.tolist()], "ordered_relative": [[int(x) for x in row] for row in rel.tolist()],
            "det_M_J_minusJ": [1, -1, 1], "atom_totals_A_B": [3, 5],
            "atom_character_A_B": [3 % 3, 5 % 3], "control_columns": ["s", "trace_distance", "P19"],
            "controls": controls, "direct_graph_field_ports": h6.field_checks()}


def wilson_control():
    omega = (-1 + sp.I*sp.sqrt(3)) / 2
    clock = sp.diag(1, omega, sp.expand(omega**2))
    shift = M
    loop = (clock*shift*clock.H*shift.H).applyfunc(sp.simplify)
    assert clock.det().simplify() == shift.det() == 1 and loop == omega * ONE
    trace = sp.trace(loop) / 3
    assert (sp.im(trace), sp.im(sp.trace(loop.conjugate())/3),
            sp.im(sp.trace(loop.H)/3)) == (sp.sqrt(3)/2, -sp.sqrt(3)/2, -sp.sqrt(3)/2)
    return {"normalized_traces_flat_ordered_commutator": [str(sp.trace(op)/3) for op in (ONE, M, loop)],
            "imaginary_part": str(sp.im(trace)), "inverse_imaginary_part": str(-sp.im(trace))}


def readout():
    # Both ranks describe normalized preparations. Column zero is the affine offset.
    fresh = h6.by_length(h6.effects())
    coherent = sp.Matrix([fresh[n] for n in sorted(fresh)])
    saved = json.loads((DONOR / "followup.json").read_text())["intermediate"]
    totals = {}
    for key, values in saved["effects_joint"].items():
        _, final = ast.literal_eval(key)
        row = sp.Matrix([[sp.Rational(v) for v in values]])
        totals[final] = totals.get(final, sp.zeros(1, 4)) + row
    recorded = sp.Matrix.vstack(*(totals[n] for n in sorted(totals)))
    ranks = [matrix[:, 1:].rank() for matrix in (coherent, recorded)]
    assert ranks == [3, 2] and recorded[:, 1] == sp.zeros(recorded.rows, 1)
    return {"rank_final_length": ranks[0], "rank_after_L7_record": ranks[1],
            "lost_coordinate": "x"}


if __name__ == "__main__":
    report = {"interference": interference(), "transport": transport(),
              "R135": wilson_control(), "R141_readout": readout()}
    print(json.dumps(report, indent=2))
