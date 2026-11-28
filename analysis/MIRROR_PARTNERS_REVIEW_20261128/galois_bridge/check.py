#!/usr/bin/env python3
"""Exact arithmetic interface to the archived #223--R140 register.

Only standard-library integer/Fraction arithmetic is used.  This module neither
executes the R130/R140 engines nor replaces their archived results.  The unified
reviewed runner calls calibrate() and then run() on GitHub Actions.

Ring coordinates (a,b) mean a*phi+b, where phi**2=phi+1.  Permutation columns
are images of basis kets, U|x>=|f(x)>; the pullback f(x)->f(A*x) uses the inverse
matrix.  This convention is essential when comparing the Cantor passport.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path


SOURCE_COMMIT = "7aae9af516972c6e7975095baaaf56e4f70af8c5"
ARCHIVE = ("analysis/MIRROR_PARTNERS_REVIEW_20261128/r140_bridge/"
           "runs/46147740174/register_bridge.json")
PHI, ONE = (1, 0), (0, 1)


def ring_mul(x, y, modulus=None):
    a, b = x
    c, d = y
    result = (a * c + a * d + b * c, a * c + b * d)
    return tuple(v % modulus for v in result) if modulus else result


def ring_power(x, n, modulus=None):
    if n < 0:
        raise ValueError("Only nonnegative powers are requested by this audit")
    answer = ONE
    while n:
        if n & 1:
            answer = ring_mul(answer, x, modulus)
        x = ring_mul(x, x, modulus)
        n //= 2
    return answer


def ring_galois(x, modulus=None):
    a, b = x
    result = (-a, a + b)
    return tuple(v % modulus for v in result) if modulus else result


def ring_norm(x):
    a, b = x
    return b * b + a * b - a * a


def ring_negative(x, modulus):
    return tuple(-v % modulus for v in x)


def ring_inverse(x, modulus):
    norm_inverse = pow(ring_norm(x) % modulus, -1, modulus)
    return tuple(norm_inverse * v % modulus for v in ring_galois(x))


def mm(a, b):
    if len(a[0]) != len(b):
        raise AssertionError("Incompatible matrix shapes")
    return [[sum(a[i][k] * b[k][j] for k in range(len(b)))
             for j in range(len(b[0]))] for i in range(len(a))]


def eye(n):
    return [[int(i == j) for j in range(n)] for i in range(n)]


def transpose(a):
    return [list(row) for row in zip(*a)]


def matrix_power(a, n):
    result = eye(len(a))
    while n:
        if n & 1:
            result = mm(result, a)
        a = mm(a, a)
        n //= 2
    return result


def matrix_combination(*terms):
    shape = (len(terms[0][1]), len(terms[0][1][0]))
    return [[sum(scale * a[i][j] for scale, a in terms)
             for j in range(shape[1])] for i in range(shape[0])]


def determinant2(a):
    return a[0][0] * a[1][1] - a[0][1] * a[1][0]


def determinant3(a):
    return sum((-1) ** j * a[0][j] * determinant2(
        [[a[i][k] for k in range(3) if k != j] for i in (1, 2)])
        for j in range(3))


def compose(p, q):
    """p after q, for column-image permutation arrays."""
    return [p[q[j]] for j in range(len(q))]


def permutation_inverse(p):
    inverse = [0] * len(p)
    for j, target in enumerate(p):
        inverse[target] = j
    return inverse


def permutation_order(p):
    current = list(range(len(p)))
    for n in range(1, 2 * len(p) + 1):
        current = compose(p, current)
        if current == list(range(len(p))):
            return n
    raise AssertionError("Unexpected permutation order")


def permutation_matrix(p):
    result = [[0] * len(p) for _ in p]
    for j, i in enumerate(p):
        result[i][j] = 1
    return result


def permutation_on(basis, action):
    lookup = {x: i for i, x in enumerate(basis)}
    if len(lookup) != len(basis):
        raise AssertionError("Duplicate ring states")
    result = [lookup[action(x)] for x in basis]
    if len(set(result)) != len(result):
        raise AssertionError("Action is not a permutation")
    return result


def require(actual, expected, name):
    if actual != expected:
        raise AssertionError(f"{name}: {actual!r} != {expected!r}")


def sparse_diagonal(record):
    n, m = record["shape"]
    require(n, m, "Diagonal shape")
    result = [0] * n
    for i, j, value in record["entries"]:
        require(i, j, "Off-diagonal entry")
        result[i] = int(value)
    return result


def calibrate(root=None):
    """Small representative arithmetic only; never invokes run()."""
    phi2 = ring_mul(PHI, PHI, 4)
    phi3 = ring_mul(phi2, PHI, 4)
    phi6 = ring_mul(phi3, phi3, 4)
    require(phi2, (1, 1), "Calibration phi squared")
    require(phi3, (2, 1), "Calibration phi cubed")
    require(phi6, ONE, "Calibration phi sixth")
    require(ring_mul(PHI, ring_inverse(PHI, 4), 4), ONE, "Calibration unit inverse")
    return {"status": "PASS", "modulus": 4, "explicit_ring_multiplications": 4,
            "unit_inversions": 1, "main_run_invoked": False}


def run(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    archive_path = root / ARCHIVE
    raw_archive = archive_path.read_bytes()
    archived = json.loads(raw_archive)
    require(archived["status"], "PASS", "Pinned register archive status")
    am = archived["exact_matrices"]

    # Integral Galois identities, before taking any finite quotient.
    Mphi = [[1, 1], [1, 0]]
    P = [[-1, 0], [1, 1]]
    A = mm(Mphi, Mphi)
    Ainv = [[1, -1], [-1, 2]]
    require(mm(P, P), eye(2), "Galois involution over Z")
    require(mm(mm(P, Mphi), P), [[0, -1], [-1, 1]], "Galois on phi")
    require(mm(mm(P, A), P), Ainv, "Galois reverses A")
    require(mm(A, Ainv), eye(2), "Integral inverse of A")

    # F4^times in the arithmetic basis (1,t^2,t), with ket convention.
    nonzero2 = [(0, 1), (1, 1), (1, 0)]
    phi2_mod2 = ring_power(PHI, 2, 2)
    m3 = permutation_on(nonzero2, lambda x: ring_mul(phi2_mod2, x, 2))
    j3 = permutation_on(nonzero2, lambda x: ring_galois(x, 2))
    phi_action2 = permutation_on(nonzero2, lambda x: ring_mul(PHI, x, 2))
    require(m3, [1, 2, 0], "Arithmetic A induces M_H6")
    require(j3, [0, 2, 1], "Arithmetic G induces J_H6")
    require(phi_action2, permutation_inverse(m3), "phi versus phi squared")
    require([x[1] for x in nonzero2], [1, 1, 0], "Published 110 readout")
    require(compose(compose(j3, m3), j3), permutation_inverse(m3), "F4 dihedral relation")
    require(am["M_H6"]["column_targets"], m3, "Archived H6 cycle")
    require(am["J_H6"]["column_targets"], j3, "Archived H6 reflection")

    # The previous parity paper's reflection is a conjugate integral lift.
    Mphi_inv = [[0, 1], [1, -1]]
    Ptilde = mm(mm(Mphi, P), Mphi_inv)
    require(Ptilde, [[1, -1], [0, -1]], "Lift of the earlier parity reflection")
    require(mm(Ptilde, Ptilde), eye(2), "Lift involution")
    require([[v % 2 for v in row] for row in Ptilde], [[1, 1], [0, 1]],
            "Previous R mod 2")

    # Stronger factor: O/(phi^6-1)=O/(4), including its full unit group.
    phi6_exact = ring_power(PHI, 6)
    ideal3 = (phi6_exact[0], phi6_exact[1] - 1)
    require(ideal3, tuple(4 * v for v in ring_power(PHI, 3)), "Ideal equality at n=3")
    phi_powers4 = [ring_power(PHI, k, 4) for k in range(6)]
    require(phi_powers4, [(0, 1), (1, 0), (1, 1), (2, 1), (3, 2), (1, 3)],
            "All six powers modulo four")
    require(ring_power(PHI, 6, 4), ONE, "Order divides six")
    if any(ring_power(PHI, k, 4) == ONE for k in range(1, 6)):
        raise AssertionError("phi must have order six modulo four")
    if (0, 3) in phi_powers4:
        raise AssertionError("minus one must be outside the phi subgroup")

    labels = [(epsilon, sheet, j, 2 * j + sheet)
              for epsilon in (1, -1) for sheet in (0, 1) for j in range(3)]
    units = [phi_powers4[k] if epsilon == 1 else ring_negative(phi_powers4[k], 4)
             for epsilon, sheet, j, k in labels]
    all4 = [(a, b) for a in range(4) for b in range(4)]
    require(set(units), {x for x in all4 if ring_norm(x) % 2 == 1}, "All 12 units")
    require(len(set(units)), 12, "Unique epsilon times phi power")
    f = permutation_on(units, lambda x: ring_mul(PHI, x, 4))
    t = permutation_on(units, lambda x: ring_inverse(x, 4))
    c = permutation_on(units, lambda x: ring_negative(x, 4))
    g = permutation_on(units, lambda x: ring_galois(x, 4))
    finv = permutation_inverse(f)
    for actual, key in [(f, "F_reduced"), (t, "T_reduced"), (c, "C_prime_reduced")]:
        require(actual, am[key]["column_targets"], f"Unit representation equals {key}")
    require(compose(compose(t, f), t), finv, "Inversion reverses full F")
    require(compose(c, f), compose(f, c), "minus sign commutes with full F")
    require(compose(c, t), compose(t, c), "minus sign commutes with inversion")
    require(compose(compose(g, f), g), compose(c, finv), "G F G = C F inverse")
    require(compose(g, g), list(range(12)), "G involution")
    controlled_c = [c[i] if sheet else i for i, (_, sheet, _, _) in enumerate(labels)]
    require(g, compose(controlled_c, t), "G = C to the sheet times T")
    require((permutation_order(f), permutation_order(t), permutation_order(c),
             permutation_order(g)), (6, 2, 2, 2), "Orders on the unit sector")

    # Two distinct signs have intrinsic expressions after fixing phi coordinates.
    d = [epsilon for epsilon, sheet, j, k in labels]
    norm_sign = [1 if ring_norm(x) % 4 == 1 else -1 for x in units]
    require(norm_sign, [(-1) ** sheet for _, sheet, _, _ in labels], "Norm reads the sheet")
    cubes = [ring_power(x, 3, 4) for x in units]
    require([1 if b == 1 else -1 for a, b in cubes], d, "Constant coefficient of x cubed reads d")
    require([a // 2 for a, b in cubes], [sheet for _, sheet, _, _ in labels], "phi coefficient reads sheet")
    require(d, sparse_diagonal(am["d_reduced"]), "Archived d readout")
    require([d[f[i]] for i in range(12)], d, "d conserved by F")
    require([d[t[i]] for i in range(12)], d, "d even under T")
    require([d[c[i]] for i in range(12)], [-v for v in d], "d odd under C")
    require([d[g[i]] for i in range(12)], [d[i] * norm_sign[i] for i in range(12)],
            "Galois changes d on the odd sheet")
    if g == t or g == c or compose(g, f) == compose(f, g):
        raise AssertionError("The Galois/time/mirror negative control collapsed")

    # Matrix W24 reconstructed independently, all entries share 1/sqrt(2).
    small_W = [[1, 0, 0, 1, 0, 0], [0, 0, 1, 0, 1, 0], [0, 1, 0, 0, 0, 1]]
    Q = [[0] * 24 for _ in range(12)]
    for block in range(4):
        for i in range(3):
            for j in range(6):
                Q[3 * block + i][6 * block + j] = small_W[i][j]
    require(am["W_full"]["shape"], [12, 24], "Archived W shape")
    archived_Q = [[0] * 24 for _ in range(12)]
    for i, j, value in am["W_full"]["entries"]:
        require(value, "sqrt(2)/2", "Common exact W coefficient")
        archived_Q[i][j] = 1
    require(Q, archived_Q, "Independent W reconstruction")
    require(mm(Q, transpose(Q)), matrix_combination((2, eye(12))), "W coisometry")
    for action, full_key in [(f, "F_full"), (t, "T_full"), (c, "C_prime_full")]:
        full = permutation_matrix(am[full_key]["column_targets"])
        require(mm(Q, full), mm(permutation_matrix(action), Q), f"W intertwines {full_key}")
    dfull = sparse_diagonal(am["d_full"])
    require([[Q[i][j] * dfull[j] for j in range(24)] for i in range(12)],
            [[d[i] * Q[i][j] for j in range(24)] for i in range(12)], "W intertwines d")
    qfull = [row["q"] for row in archived["charges_on_full_basis"]]
    Kint = [[qfull[i] * Q[j][i] for j in range(12)] for i in range(24)]
    require(mm(Q, Kint), [[0] * 12 for _ in range(12)], "Inherited q kernel witness")
    require(mm(Q, [[qfull[i] * v for v in Kint[i]] for i in range(24)]),
            matrix_combination((2, eye(12))), "q does not descend through normalized W")

    # Reduction of 12 units modulo two is four-to-one, distinct from the 24-to-12 W above.
    lookup2 = {x: i for i, x in enumerate(nonzero2)}
    projection = [lookup2[tuple(v % 2 for v in x)] for x in units]
    R = [[int(projection[j] == i) for j in range(12)] for i in range(3)]
    require([row.count(1) for row in R], [4, 4, 4], "Uniform four-element unit fibres")
    require(mm(R, transpose(R)), matrix_combination((4, eye(3))), "Reduction coisometry scale")
    for action, target, name in [(f, permutation_inverse(m3), "phi"),
                                 (compose(f, f), m3, "phi squared"),
                                 (g, j3, "Galois"), (t, j3, "inversion")]:
        require(mm(R, permutation_matrix(action)), mm(permutation_matrix(target), R),
                f"Modulo-two projection: {name}")
    require(mm(R, permutation_matrix(c)), R, "Modulo-two projection loses C")
    require(mm(R, permutation_matrix(compose(compose(f, f), f))), R, "Projection loses F cubed")
    fibres = [[i for i, target in enumerate(projection) if target == j] for j in range(3)]
    for fibre in fibres:
        require(sorted(d[i] for i in fibre), [-1, -1, 1, 1], "Mirror parity lost in each fibre")
        require(sorted(norm_sign[i] for i in fibre), [-1, -1, 1, 1], "Sheet parity lost in each fibre")
    unit_kernel = [x for x in units if tuple(v % 2 for v in x) == ONE]
    zero_fibre = [x for x in all4 if all(v % 2 == 0 for v in x)]
    require(set(unit_kernel), {(0, 1), (0, 3), (2, 1), (2, 3)}, "Multiplicative kernel")
    require(len(zero_fibre), 4, "Excluded nonunit zero fibre")
    if set(unit_kernel) & set(zero_fibre):
        raise AssertionError("Unit-group kernel and zero residue fibre are different objects")
    try:
        ring_inverse((2, 0), 4)
    except ValueError:
        nonunit_inverse_rejected = True
    else:
        raise AssertionError("Inversion must reject the nonunit 2phi")

    # n=1..12 is a finite control of the all-n proof, not the proof itself.
    quotient_rows = []
    for n in range(1, 13):
        un = ring_power(PHI, 2 * n)
        An = matrix_power(A, n)
        lucas = An[0][0] + An[1][1]
        for sigma, label in [(1, "ordinary_phi2n_minus1"), (-1, "signed_phi2n_plus1")]:
            generator = (un[0], un[1] - sigma)
            mod2 = all(v % 2 == 0 for v in generator)
            mod4 = all(v % 4 == 0 for v in generator)
            require(mod2, n % 3 == 0, "All-n modulo-two criterion")
            require(mod4, sigma == 1 and n % 3 == 0, "All-n modulo-four criterion")
            quotient_order = abs(ring_norm(generator))
            require(quotient_order, lucas - 2 * sigma, "Quotient order")
            det_relation = determinant2(matrix_combination((1, An), (-sigma, eye(2))))
            require(det_relation, ring_norm(generator), "Norm equals lattice determinant")
            quotient_rows.append({
                "n": n, "boundary": label, "ideal_generator_phi_basis": generator,
                "order": quotient_order, "reduces_to_F4": mod2,
                "reduces_to_O_mod4": mod4,
                "fibre_size_mod2": quotient_order // 4 if mod2 else None,
                "fibre_size_mod4": quotient_order // 16 if mod4 else None,
            })

    # A complex-linear 2x2-to-3x3 intertwiner cannot replace the finite-set lift.
    M3 = permutation_matrix(m3)
    pA_at_A = matrix_combination((1, mm(A, A)), (-3, A), (1, eye(2)))
    pA_at_M = matrix_combination((1, mm(M3, M3)), (-3, M3), (1, eye(3)))
    require(pA_at_A, [[0, 0], [0, 0]], "Characteristic polynomial of A")
    require(determinant3(pA_at_M), -16, "No characteristic-zero linear intertwiner")
    require(determinant2(matrix_combination((1, matrix_power(A, 3)), (-1, eye(2)))),
            -16, "det(A cubed minus I)")
    # Inversion is a group automorphism on units, not the Galois ring automorphism.
    inverse_sum = ring_inverse((1, 1), 4)
    sum_inverses = tuple((x + y) % 4 for x, y in zip(ONE, ring_inverse(PHI, 4)))
    if inverse_sum == sum_inverses:
        raise AssertionError("Inversion unexpectedly became additive")

    return {
        "status": "PASS",
        "scope": "exact arithmetic and archived-register intertwiners; no new R140 replay",
        "source": {"commit": SOURCE_COMMIT, "archive_path": ARCHIVE,
                   "archive_sha256": hashlib.sha256(raw_archive).hexdigest()},
        "integral": {"Mphi": Mphi, "Galois_P": P, "A": A, "A_inverse": Ainv,
                     "earlier_reflection_lift": Ptilde, "phi6_minus1": ideal3,
                     "det_A3_minus_I": -16, "det_pA_at_M_H6": -16},
        "mod2": {"nonzero_basis": nonzero2, "A_permutation": m3,
                 "G_permutation": j3, "phi_permutation": phi_action2,
                 "second_coordinate_readout": [1, 1, 0],
                 "zero_element_retained_in_full_field": True,
                 "H6_sector_selected_by_nonzero_residue": True},
        "mod4": {
            "phi_powers_0_to_5": phi_powers4, "minus_one_outside_phi_subgroup": True,
            "unit_group": "C6 x C2", "unit_count": 12, "nonunit_count": 4,
            "states": [{"index": i, "epsilon": epsilon, "sheet": sheet,
                        "j": j, "exponent": k, "phi_basis": units[i],
                        "norm_mod4": ring_norm(units[i]) % 4, "cube": cubes[i], "d": d[i]}
                       for i, (epsilon, sheet, j, k) in enumerate(labels)],
            "permutations": {"F": f, "T_inversion": t, "C_minus": c,
                             "G_Galois": g, "C_controlled_by_sheet": controlled_c},
            "archive_F_T_C_d_matches": True, "G_equals_C_to_sheet_times_T": True,
            "G_F_G_equals_C_F_inverse": True,
            "G_not_equal_T_or_C": True,
            "d_depends_on_chosen_phi_subgroup": True,
            "T_not_additive_example": {"inverse_of_1_plus_phi": inverse_sum,
                                      "inverse_1_plus_inverse_phi": sum_inverses},
            "nonunit_inverse_rejected": nonunit_inverse_rejected,
        },
        "W24_to_units": {
            "shape": [12, 24], "common_factor": "1/sqrt(2)",
            "integer_incidence": Q, "rank": 12, "kernel_dimension": 12,
            "F_T_C_d_intertwining": True, "q_non_descent_reconfirmed": True,
            "classical_basis_compression_norm_squared": str(Fraction(1, 2)),
            "probability_preserving_scope": "im(W dagger), with lifted states and effects",
        },
        "unit_projection_mod2": {
            "targets_in_H6_basis": projection, "fibres": fibres,
            "normalized_coisometry_factor": "1/2", "unit_kernel": unit_kernel,
            "zero_residue_nonunits": zero_fibre,
            "loses_mirror_parity": True, "loses_sheet_parity": True,
            "identifies_G_and_T": True, "phi_descends_to_M_H6_inverse": True,
            "phi_squared_descends_to_M_H6": True,
        },
        "finite_quotient_controls": quotient_rows,
        "theorems_tested_not_inferred_from_scan": {
            "Galois_descends_to_both_boundary_quotients": "all n>=1",
            "reduction_to_F4": "both signs iff 3 divides n",
            "reduction_to_O_mod4": "ordinary iff 3 divides n; signed never",
            "full_unit_group_intertwiner": "O/(phi^6-1) units = O/(4) units",
            "full_T_lift_on_ordinary_preimage_units":
                "T_n(x)=(-1)^s(x) G_n(x), where Norm(x) mod4=(-1)^s(x); analytical proof",
            "no_nonzero_characteristic_zero_linear_map_LA_equals_ML": True,
        },
        "not_claimed": ["arithmetic monodromy is the full physical ADD law",
                        "autonomous H6 length-controlled switching or quantum preparation",
                        "signed and ordinary quotient rings are isomorphic",
                        "Galois is identical to mirror C or time reversal T on all slices",
                        "physical universes, metric or thermodynamic arrow"],
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
