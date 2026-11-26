"""Exact controls for the R150 proposals. Run with Python 3 and SymPy."""
from collections import Counter
from pathlib import Path
import json
import runpy
import sympy as sp

HERE = Path(__file__).resolve().parent
engine = runpy.run_path(str(HERE.parent / "R141_R148_MODEL/code/r130_reference.py"))


def port_step(graph):
    return engine["forward"](graph, (1, -1))


def port_response():
    """Finite response on two declared observables of the original C2 update."""
    transfers = {}
    for bit in (1, 2, 4, 8):
        columns = []
        for slot in range(3):
            word = [0, 0, 0]
            word[slot] = bit
            following = engine["word"](port_step(engine["named"](word)))
            assert len(following) == 3 and following.count(bit) == 1
            columns.append([int(value == bit) for value in following])
        matrix = sp.Matrix(columns).T
        assert matrix.T * matrix == sp.eye(3) and matrix**3 == sp.eye(3)
        transfers[str(bit)] = matrix.tolist()

    def lengths(word):
        g = engine["named"](word)
        output = []
        for _ in range(8):
            g = port_step(g)
            output.append(len(g))
        return output

    background = [1, 2, 12]
    base = lengths(background)
    assert base == [3] * 8
    flips, mean_columns = [], []
    for slot in range(3):
        samples = []
        for bit in (1, 2, 4, 8):
            perturbed = background.copy()
            perturbed[slot] ^= bit
            series = lengths(perturbed)
            flips.append({"slot": slot, "bit": bit, "lengths": series})
            samples.append(sp.Matrix(series) - sp.Matrix(base))
        mean_columns.append(sum(samples, sp.zeros(8, 1)) / 4)
    response = sp.Matrix.hstack(*mean_columns)
    tails = Counter(row["lengths"][-1] for row in flips)
    assert tails == {11: 6, 12: 2, 5: 4}
    assert response.rank() == 2 and response[:, 0] == response[:, 1]
    return {"slot_transfer_by_bit": transfers, "base_lengths": base, "flips": flips,
            "mean_delta_length_rows_by_tick": [[str(x) for x in row] for row in response.tolist()],
            "length_response_rank": response.rank(), "eighth_tick_counts": dict(sorted(tails.items()))}


def indices():
    # Site numbering is one-based in Fig. 1 and Eq. (7) of Kaplan & Sun.
    reflection = sp.eye(7)
    reflection.row_swap(1, 6)
    reflection.row_swap(3, 5)
    mass = sp.zeros(7)
    for left, plus, minus in ((1, 2, 7), (2, 3, 1), (3, 4, 2), (3, 7, 6),
                              (4, 5, 3), (6, 3, 5), (7, 1, 3)):
        mass[left - 1, plus - 1] += 1
        mass[left - 1, minus - 1] -= 1
    assert reflection.trace() == 3 and mass.rank() == 4
    assert reflection * mass * reflection == -mass

    def parity_kernel(operator):
        return [7 - operator.col_join(reflection - sign * sp.eye(7)).rank() for sign in (1, -1)]

    assert parity_kernel(mass) == parity_kernel(mass.T) == [3, 0]
    # Deliberately destroy spatial parity while retaining a square mass matrix.
    assert (mass + sp.eye(7)).rank() == 7
    # Deterministic deformations preserving parity. Sector indices include opposite chiralities.
    trials = []
    for k in range(1, 5):
        seed = sp.Matrix(7, 7, lambda i, j: ((i+2)**2*(j+3)**k + (i+1)*j*j) % 17)
        perturbed = mass + seed - reflection * seed * reflection
        right, left = parity_kernel(perturbed), parity_kernel(perturbed.T)
        assert right[0] - left[1] == left[0] - right[1] == 3
        trials.append({"rank": perturbed.rank(), "right": right, "left": left})
    shift = sp.Matrix([[0, 0, 1], [1, 0, 0], [0, 1, 0]])
    mirror = sp.eye(3)
    mirror.row_swap(1, 2)
    derivative = shift - sp.eye(3)
    assert mirror*shift*mirror == shift.T and mirror.trace() == 1
    assert derivative.rank() == derivative.T.rank() == 2
    return {"donor_trace":int(reflection.trace()), "donor_mass_rank":mass.rank(),
            "ker_M_spatial_even_odd":parity_kernel(mass), "ker_MT_spatial_even_odd":parity_kernel(mass.T),
            "symmetry_preserving_deformations":trials, "symmetry_breaking_rank":7,
            "triangle_trace":1, "triangle_incidence_kernel_and_cokernel":[1, 1], "cycle_index":0}


def triangle():
    one = sp.ones(3) / 3
    two = sp.eye(3) - one
    adjacency = sp.ones(3) - sp.eye(3)
    triangle_matrix = 3*sp.eye(3) - adjacency
    generator = triangle_matrix - 3*sp.eye(3)
    assert generator == -2*one + two and generator.trace() == 0
    c = sp.Matrix([1, 1, 0]) / sp.sqrt(2)
    assert (one*c).dot(one*c) == sp.Rational(2, 3)
    # Drop common positive e^t. At equality of norms exp(-3t)=1/sqrt(2).
    eta = one*c/sp.sqrt(2) + two*c
    assert sp.simplify((one*eta).dot(one*eta) - (two*eta).dot(two*eta)) == 0
    assert eta[0] == eta[1] and eta[2] < 0
    def q(vector):
        return sp.simplify(vector.dot(vector)/sum(vector)**2)
    positive = eta.applyfunc(abs)
    assert q(eta) == sp.Rational(2, 3)
    physical = 12/(4+sp.sqrt(2))**2
    assert sp.simplify(q(positive)-physical)==0
    return {"triangle_eigenvalues":[1,4,4], "generator_eigenvalues":[-2,1,1],
            "time_equal":"log(2)/6", "signed_Q":"2/3", "mass_Q":"12/(4+sqrt(2))**2",
            "mass_Q_decimal":float(physical), "equal_mass_pair":[0,1]}


if __name__ == "__main__":
    print(json.dumps({"ports":port_response(), "indices":indices(), "flow":triangle()},
                     ensure_ascii=False, indent=2, default=int))
