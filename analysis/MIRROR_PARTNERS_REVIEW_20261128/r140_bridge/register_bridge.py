#!/usr/bin/env python3
"""Exact named-register interface between PR #223 and R140/H6.

This module imports the pinned in-repository R130 engine without invoking its
main().  It never writes or replaces historical results.  Scientific execution
is delegated to the reviewed, unified GitHub Actions entry point.

The two signs below label mirror sectors, not the sign of the conserved q.
Every sector still contains both q=+1 and q=-1 states.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import sympy as sp


SOURCE_COMMIT = "fcc006b30e120fb536eba09288deeaf2dc42f167"
ENGINE_PATH = "analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py"
EPS = (1, -1)


def _load_engine(root: Path):
    path = root / ENGINE_PATH
    spec = importlib.util.spec_from_file_location("r130_register_bridge", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load the existing R130 engine: {path}")
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    return engine


def _block2(a, b, c, d):
    return sp.BlockMatrix([[a, b], [c, d]]).as_explicit()


def build_registers(root=None):
    """Return exact matrices and named bases for the companion history replay.

    Columns are input states; permutation column j is the image of basis j.
    H_minus is defined as the actual named C' image, with reversed directed
    edges.  No atomic renaming or unoriented-graph quotient is used.

    Public keys used by history_bridge.py: W_plus, W_minus, S_plus, S_minus,
    T_plus, T_minus, C_even, c3, c6, M, J.  These matrices describe the even
    six-state slice of each sector.  The full named F lives on full_basis.
    """
    root = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    e = _load_engine(root)

    def mirror(x):
        return tuple((e.mirror_name(u), s) for u, s in reversed(x))

    def swap_ports(x):
        return tuple((u, ((s & 1) << 1) | ((s & 2) >> 1)
                      | ((s & 4) << 1) | ((s & 8) >> 1)) for u, s in x)

    def cp(x):
        return mirror(swap_ports(x))

    def forward(x):
        return e.forward(x, EPS)

    def reverse_time(x):
        return e.interact(e.r2(x), EPS)

    def permutation(basis, action):
        lookup = {e.canonical(x): i for i, x in enumerate(basis)}
        if len(lookup) != len(basis):
            raise AssertionError("The named basis contains duplicate states")
        targets = []
        for x in basis:
            key = e.canonical(action(x))
            if key not in lookup:
                raise AssertionError("The chosen named basis is not closed")
            targets.append(lookup[key])
        if len(set(targets)) != len(basis):
            raise AssertionError("The named action is not a permutation")
        return sp.eye(len(basis))[:, targets]

    even_plus = [e.named(tuple(p if j == i else 0 for j in range(3)))
                 for p in (1, 8) for i in range(3)]
    odd_plus = [forward(x) for x in even_plus]
    even_minus = [cp(x) for x in even_plus]
    odd_minus = [forward(x) for x in even_minus]
    full_basis = even_plus + odd_plus + even_minus + odd_minus
    even_basis = even_plus + even_minus

    S_plus = permutation(even_plus, lambda x: forward(forward(x)))
    S_minus = permutation(even_minus, lambda x: forward(forward(x)))
    T_plus = permutation(even_plus, reverse_time)
    T_minus = permutation(even_minus, reverse_time)
    W = sp.Matrix([[1, 0, 0, 1, 0, 0],
                   [0, 0, 1, 0, 1, 0],
                   [0, 1, 0, 0, 0, 1]]) / sp.sqrt(2)
    M = sp.eye(3)[:, [1, 2, 0]]
    J = sp.eye(3)[:, [0, 2, 1]]
    c3 = sp.Matrix([1, 1, 0]) / sp.sqrt(2)

    return {
        "root": root, "engine": e, "cp": cp, "forward": forward,
        "reverse_time": reverse_time, "permutation": permutation,
        "even_plus": even_plus, "odd_plus": odd_plus,
        "even_minus": even_minus, "odd_minus": odd_minus,
        "full_basis": full_basis,
        "S_plus": S_plus, "S_minus": S_minus,
        "T_plus": T_plus, "T_minus": T_minus,
        "W_plus": W, "W_minus": W.copy(), "M": M, "J": J,
        "C_even": permutation(even_basis, cp),
        "F_full": permutation(full_basis, forward),
        "T_full": permutation(full_basis, reverse_time),
        "C_full": permutation(full_basis, cp),
        "c3": c3, "c6": W.H * c3,
    }


def _same(actual, expected, label):
    if actual.shape != expected.shape:
        raise AssertionError(f"{label}: different matrix shapes")
    difference = (actual - expected).applyfunc(sp.simplify)
    if difference != sp.zeros(*actual.shape):
        raise AssertionError(f"{label}: exact matrix identity failed")


def _matrix_data(matrix):
    """Complete exact sparse representation; no floating point entries."""
    return {
        "shape": [matrix.rows, matrix.cols],
        "entries": [[i, j, str(sp.simplify(matrix[i, j]))]
                    for i in range(matrix.rows) for j in range(matrix.cols)
                    if matrix[i, j] != 0],
    }


def _permutation_data(matrix):
    targets = []
    for j in range(matrix.cols):
        rows = [i for i in range(matrix.rows) if matrix[i, j] == 1]
        if len(rows) != 1 or sum(matrix[:, j]) != 1:
            raise AssertionError("Expected an exact permutation matrix")
        targets.append(rows[0])
    return {"dimension": matrix.rows, "column_targets": targets}


def _charges(x):
    q = chi = channel = d = 0
    for _, s in x:
        a1, b1, a2, b2 = ((s >> k) & 1 for k in range(4))
        q += a1 + a2 - b1 - b2
        chi += a1 * a2 - b1 * b2
        channel += a1 + b1 - a2 - b2
        d += a1 - b1 - a2 + b2
    return {"q": q, "chi": chi, "N1_minus_N2": channel, "d_q1_minus_q2": d}


def calibrate(root=None):
    """One representative input; the unified runner measures elapsed time.

    This does not invoke run() or build the full 24-state matrices.  Its role is
    environment and scale calibration, not substitution for the main replay.
    """
    root = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    e = _load_engine(root)
    x = e.named((1, 0, 0))
    fx = e.forward(x, EPS)
    sx = e.forward(fx, EPS)
    tx = e.interact(e.r2(x), EPS)
    if not e.equal(sx, e.named((0, 0, 1))):
        raise AssertionError("Calibration: the a1 position shift is inconsistent")
    if not e.equal(tx, e.named((8, 0, 0))):
        raise AssertionError("Calibration: T does not exchange a1 with b2")
    if e.equal(fx, x):
        raise AssertionError("Calibration: distinct named slices were identified")
    W = sp.Matrix([[1, 0, 0, 1, 0, 0],
                   [0, 0, 1, 0, 1, 0],
                   [0, 1, 0, 0, 0, 1]]) / sp.sqrt(2)
    M = sp.eye(3)[:, [1, 2, 0]]
    J = sp.eye(3)[:, [0, 2, 1]]
    _same(W[:, 2], M * W[:, 0], "calibration W S column")
    _same(W[:, 3], J * W[:, 0], "calibration W T column")
    return {
        "status": "PASS", "representative_named_inputs": 1,
        "named_forward_steps": 2, "named_T_applications": 1,
        "matrix_column_identities": 2,
        "scope": "representative calibration only; full run not invoked",
        "source_sha256": hashlib.sha256((root / ENGINE_PATH).read_bytes()).hexdigest(),
    }


def run(root=None):
    """Run the finite exact checks and return a JSON-serializable record."""
    b = build_registers(root)
    e, cp, forward, reverse_time = (
        b[k] for k in ("engine", "cp", "forward", "reverse_time"))
    S, T, W, M, J = (b[k] for k in ("S_plus", "T_plus", "W_plus", "M", "J"))
    F_full, T_full, C_full = (b[k] for k in ("F_full", "T_full", "C_full"))
    I3, I6, I12, I24 = (sp.eye(n) for n in (3, 6, 12, 24))
    Z3, Z6, Z12 = (sp.zeros(n) for n in (3, 6, 12))

    # Independently specified index actions, compared with the named engine.
    S_expected = sp.eye(6)[:, [2, 0, 1, 4, 5, 3]]
    T_expected = sp.eye(6)[:, [3, 4, 5, 0, 1, 2]]
    _same(S, S_expected, "S positions")
    _same(T, T_expected, "T particle exchange")
    _same(b["S_minus"], S, "mirror S")
    _same(b["T_minus"], T, "mirror T")
    _same(W * S, M * W, "W S = M W")
    _same(W * T, J * W, "W T = J W")
    _same(W * W.H, I3, "W coisometry")
    _same(T * S * T, S.T, "even time reversal")
    _same(b["C_even"], _block2(Z6, I6, I6, Z6), "mirror sector exchange")

    # Full named F: odd bases are F applied to the even bases, not identified.
    F12 = _block2(Z6, S, I6, Z6)
    T12 = sp.diag(T, S.T * T)
    _same(F_full, sp.diag(F12, F12), "two named slices for F")
    _same(T_full, sp.diag(T12, T12), "time reversal on the odd slice")
    _same(C_full, _block2(Z12, I12, I12, Z12), "full mirror sector exchange")
    _same(F_full ** 6, I24, "F period six")
    _same(T_full ** 2, I24, "T involution")
    _same(C_full ** 2, I24, "C prime involution")
    _same(T_full * F_full * T_full, F_full.T, "full named time reversal")
    _same(C_full * F_full, F_full * C_full, "full named same time mirror")
    _same(C_full * T_full, T_full * C_full, "C prime commutes with T")

    # H6 quotient retained on each named slice and on each mirror sector.
    W_full = sp.diag(W, W, W, W)
    F6 = _block2(Z3, M, I3, Z3)
    T6 = sp.diag(J, M.T * J)
    F_reduced = sp.diag(F6, F6)
    T_reduced = sp.diag(T6, T6)
    C_reduced = _block2(Z6, I6, I6, Z6)
    _same(W_full * F_full, F_reduced * W_full, "full F intertwiner")
    _same(W_full * T_full, T_reduced * W_full, "full T intertwiner")
    _same(W_full * C_full, C_reduced * W_full, "full C prime intertwiner")
    _same(W_full * W_full.H, I12, "full coisometry")
    _same(F_full * W_full.H, W_full.H * F_reduced, "invariant lifted states")

    # Exact negative controls against discarded names and confused symmetries.
    even_keys = {e.canonical(x) for x in b["even_plus"]}
    full_keys = {e.canonical(x) for x in b["full_basis"]}
    if len(full_keys) != 24:
        raise AssertionError("The full named register must have 24 distinct states")
    f_outside_even = sum(e.canonical(forward(x)) not in even_keys
                         for x in b["even_plus"])
    cp_outside_even = sum(e.canonical(cp(x)) not in even_keys
                          for x in b["even_plus"])
    t_inside_even = sum(e.canonical(reverse_time(x)) in even_keys
                        for x in b["even_plus"])
    if (f_outside_even, cp_outside_even, t_inside_even) != (6, 6, 6):
        raise AssertionError("Expected F-sheet, C-sector and T-intrasector separation")
    naive_T12 = sp.diag(T, T)
    naive_reversal_defect = naive_T12 * F12 * naive_T12 - F12.T
    if naive_reversal_defect == sp.zeros(12):
        raise AssertionError("The identical-slice T negative control failed")
    if F12 ** 3 == I12 or C_full == T_full:
        raise AssertionError("A distinct named slice or distinct symmetry collapsed")
    if any(not e.equal(cp(x), y) for x, y in zip(b["odd_plus"], b["odd_minus"])):
        raise AssertionError("Odd mirror bases do not commute with the named F")

    # W is a coisometry, not a six-dimensional change of coordinates.
    P = W.H * W
    _same(P * P, P, "projection onto im W dagger")
    if W.rank() != 3 or len(W.nullspace()) != 3 or P == I6:
        raise AssertionError("The rectangular-map negative control failed")
    e0 = sp.eye(6)[:, 0]
    norm_classical = sp.simplify((W * e0).dot((W * e0).conjugate()))
    if norm_classical != sp.Rational(1, 2):
        raise AssertionError("A classical basis state must lose half its norm under W")
    c6 = b["c6"]
    _same(c6, sp.Matrix([1, 0, 1, 1, 1, 0]) / 2, "published coherent preparation")
    _same(P * c6, c6, "coherent state lies in the chosen subspace")
    rho = c6 * c6.H
    dephased = sp.diag(*rho.diagonal())
    weights = {"coherent": sp.trace(P * rho),
               "dephased_same_populations": sp.trace(P * dephased),
               "fully_mixed": sp.trace(P) / 6}
    if weights != {"coherent": 1, "dephased_same_populations": sp.Rational(1, 2),
                   "fully_mixed": sp.Rational(1, 2)}:
        raise AssertionError("Unexpected weight in the probability-preserving subspace")

    # Odd charges are microscopic observables, not automatically H6 observables.
    charge_rows = [_charges(x) for x in b["full_basis"]]
    qfull = sp.diag(*[row["q"] for row in charge_rows])
    nfull = sp.diag(*[row["N1_minus_N2"] for row in charge_rows])
    dfull = sp.diag(*[row["d_q1_minus_q2"] for row in charge_rows])
    _same(F_full.T * qfull * F_full, qfull, "q conserved")
    _same(C_full.T * qfull * C_full, -qfull, "q mirror odd")
    _same(T_full.T * qfull * T_full, -qfull, "q reversal odd")
    _same(C_full.T * nfull * C_full, nfull, "channel difference mirror even")
    _same(T_full.T * nfull * T_full, -nfull, "channel difference reversal odd")
    _same(dfull, sp.diag(I12, -I12), "d distinguishes the mirror sectors")
    _same(F_full.T * dfull * F_full, dfull, "d conserved")
    _same(C_full.T * dfull * C_full, -dfull, "d mirror odd")
    _same(T_full.T * dfull * T_full, dfull, "d reversal even")
    d_reduced = sp.diag(I6, -I6)
    _same(W_full * dfull, d_reduced * W_full, "d descends through the doubled W")
    if any(row["chi"] != 0 for row in charge_rows):
        raise AssertionError("A one-particle register cannot carry nonzero chi")
    q6 = sp.diag(1, 1, 1, -1, -1, -1)
    K = q6 * W.H
    _same(W * K, sp.zeros(3), "explicit kernel basis")
    _same(K.H * K, I3, "orthonormal kernel basis")
    _same(W * q6 * K, I3, "q does not descend through W")
    _same(P * q6 * P, sp.zeros(6), "compressed q vanishes")
    chi_witness = e.named((5, 0, 0))
    witness_rows = {
        "input": _charges(chi_witness),
        "F_input": _charges(forward(chi_witness)),
        "C_prime_input": _charges(cp(chi_witness)),
        "T_input": _charges(reverse_time(chi_witness)),
    }
    if witness_rows["input"] != {"q": 2, "chi": 1, "N1_minus_N2": 0,
                                 "d_q1_minus_q2": 0}:
        raise AssertionError("Incorrect nonzero-chi witness")
    if witness_rows["F_input"] != witness_rows["input"]:
        raise AssertionError("Nonzero-chi witness not conserved")
    for key in ("C_prime_input", "T_input"):
        if witness_rows[key] != {"q": -2, "chi": -1, "N1_minus_N2": 0,
                                 "d_q1_minus_q2": 0}:
            raise AssertionError("Nonzero-chi witness not odd")

    return {
        "status": "PASS",
        "scope": "exact finite named register; same arrow symmetry and H6 representation",
        "source": {"commit": SOURCE_COMMIT, "path": ENGINE_PATH,
                   "sha256": hashlib.sha256((b["root"] / ENGINE_PATH).read_bytes()).hexdigest()},
        "basis_order": ["plus_even", "plus_odd=F(plus_even)",
                        "minus_even=C_prime(plus_even)", "minus_odd=F(minus_even)"],
        "within_slice": [[p, i] for p in ["a1", "b2"] for i in range(3)],
        "within_slice_minus_note": "same source-column labels after C_prime: a1->b1, b2->a2",
        "named_basis": b["full_basis"],
        "dimensions": {"single_even_slice": 6, "single_full_F_sector": 12,
                       "mirror_pair_full_F": 24, "single_W_rank": 3,
                       "single_W_kernel": 3, "full_W_rank": 12},
        "exact_matrices": {
            "S_plus": _permutation_data(S), "S_minus": _permutation_data(b["S_minus"]),
            "T_plus": _permutation_data(T), "T_minus": _permutation_data(b["T_minus"]),
            "M_H6": _permutation_data(M), "J_H6": _permutation_data(J),
            "W_plus": _matrix_data(W), "W_minus": _matrix_data(b["W_minus"]),
            "kernel_basis_K=q_W_dagger": _matrix_data(K),
            "F_full": _permutation_data(F_full), "T_full": _permutation_data(T_full),
            "C_prime_full": _permutation_data(C_full), "W_full": _matrix_data(W_full),
            "F_reduced": _permutation_data(F_reduced),
            "T_reduced": _permutation_data(T_reduced),
            "C_prime_reduced": _permutation_data(C_reduced),
            "d_full": _matrix_data(dfull), "d_reduced": _matrix_data(d_reduced)},
        "identities": {"W_S_equals_M_W": True, "W_T_equals_J_W": True,
                       "mirror_W_C_prime_equals_original_W": True,
                       "full_F_T_C_intertwiners": True, "F_named_period": 6,
                       "T_F_T_equals_F_inverse": True, "C_prime_F_equals_F_C_prime": True,
                       "C_prime_T_equals_T_C_prime": True},
        "negative_controls": {
            "F_images_outside_original_even_slice": f_outside_even,
            "C_prime_images_outside_original_even_sector": cp_outside_even,
            "T_images_inside_original_even_sector": t_inside_even,
            "same_T_on_both_named_slices_fails_reversal": True,
            "naive_reversal_defect_nonzero_entries": sum(v != 0 for v in naive_reversal_defect),
            "F_cubed_is_not_named_identity": True,
            "all_named_states": len(full_keys),
            "unlabelled_cyclic_words_after_forgetting_names":
                len({e.cyclic(e.word(x)) for x in b["full_basis"]}),
            "W_is_not_invertible_on_C6": True,
            "classical_basis_vector_compression_norm_squared": str(norm_classical),
            "projection_weights": {k: str(v) for k, v in weights.items()},
            "q_does_not_descend_to_W_quotient": True,
            "compressed_q_on_imWdagger": "0",
            "one_particle_chi_identically_zero": True},
        "charges_on_full_basis": charge_rows,
        "mirror_readout": {
            "observable": "d=q1-q2=sum(a1-b1-a2+b2)",
            "plus_sector": 1, "minus_sector": -1,
            "F_conserved": True, "C_prime_odd": True, "T_even": True,
            "descends_to_doubled_H6": True,
            "reduced_operator_with_slices": "diag(I6,-I6)",
            "reduced_operator_on_even_slices": "diag(I3,-I3)",
            "readout_projectors": "(I +/- d)/2",
            "interpretation": "one concrete mirror-sector observable; not a time arrow",
        },
        "nonzero_chi_witness": {"input_word": [5, 0, 0], "values": witness_rows},
        "not_claimed": ["autonomous H6 switching from a one-particle register",
                        "two physical universes or a spatial 3+1+3 decomposition",
                        "a thermodynamic arrow from the integer step",
                        "interference between mirror sectors without a specified instrument"],
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
