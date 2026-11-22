"""Explore the R139 one-split carrier. Run from any directory with ordinary Python."""
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from runpy import run_path

import numpy as np


HERE = Path(__file__).resolve().parent
R132 = HERE.parent / "ADD_CONNES_PORT_TRANSPORT_20261120/check.py"
GROUP = range(8)
TOL = 1e-12


def near(actual, expected):
    np.testing.assert_allclose(actual, expected, atol=TOL, rtol=0)


def linked_shift(state, end, links, matrices):
    """Lift the R132 head matrix to fundamental spinors in the tail frame."""
    names = [u for u, _ in state]
    shift = np.zeros((2*len(state), 2*len(state)), complex)
    for i, j in zip(*np.nonzero(end)):
        shift[2*i:2*i+2, 2*j:2*j+2] = matrices[links[names[i], names[j]]]
    return shift


def check_named_transport(port, engine, coarse, fine, vertex, matrices, mul):
    old_names = [u for u, _ in coarse]
    new_names = [u for u, _ in fine]
    left, right = engine.left(vertex), engine.right(vertex)
    old_i = old_names.index(vertex)
    old_j = (old_i + 1) % len(coarse)
    head = old_names[old_j]
    def surviving(u):
        return left if u == vertex else u

    # The incoming edge continues into the left child. The outgoing edge splits.
    kept = {(u, old_names[(i+1) % len(coarse)]): i+1 for i, u in enumerate(old_names)
            if u != vertex}
    old_end = port["ring"](len(coarse))[3]
    new_end = port["ring"](len(fine))[3]
    fine_source, fine_target = new_names.index(left), new_names.index(head)
    si, sj = slice(2*old_i, 2*old_i+2), slice(2*old_j, 2*old_j+2)
    ti, tj = slice(2*fine_source, 2*fine_source+2), slice(2*fine_target, 2*fine_target+2)
    for a, b in product(GROUP, repeat=2):
        old_links = {**kept, (vertex, head): mul[a, b]}
        new_links = {(surviving(u), surviving(v)): g for (u, v), g in kept.items()}
        new_links.update({(left, right): a, (right, head): b})
        old_step = linked_shift(coarse, old_end, old_links, matrices)
        new_step = linked_shift(fine, new_end, new_links, matrices)
        # Compare transport on the same oriented path, at its surviving endpoints.
        near((new_step @ new_step)[ti, tj], old_step[si, sj])
        near(np.linalg.matrix_power(new_step, len(fine))[ti, ti],
             np.linalg.matrix_power(old_step, len(coarse))[si, si])


def named_pairs(matrices, mul):
    port = run_path(str(R132))
    engine = port["engine"]
    pairs = []
    for label, children in [(3, (1, 2)), (12, (8, 4))]:
        for position in range(3):
            for offset in (0, 41):
                word = tuple(label if i == position else 0 for i in range(3))
                coarse = tuple((("atom", i + offset), s) for i, s in enumerate(word))
                vertex = coarse[position][0]
                other = tuple(row for row in coarse if row[0] != vertex)
                expected = (coarse[:position] + ((engine.left(vertex), children[0]),
                            (engine.right(vertex), children[1])) + coarse[position+1:])
                fine = engine.interact(coarse, (1, -1))
                assert engine.equal(fine, expected)
                assert engine.equal(engine.interact(fine, (1, -1)), coarse)
                assert all(row in fine for row in other)
                for state in (coarse, fine):
                    _, _, start, end = port["ring"](len(state))
                    # Use the named edge index: tail i, head i+1.
                    assert (start == np.eye(len(state))).all()
                    expected_head = np.roll(np.eye(len(state)), -1, axis=0)
                    assert (end == expected_head).all()
                    transported = port["port_word"](engine.word(state), start, end)
                    assert transported == engine.word(engine.transport(state, 2))
                check_named_transport(port, engine, coarse, fine, vertex, matrices, mul)
                pairs.append((label, position, offset))
    return {"named_pairs": len(pairs), "named_ring_path_comparisons": 64*len(pairs),
            "lengths": [3, 4, 3], "channels": [3, 12],
            "R130_sha256": port["engine_hash"], "R132_sha256": sha256(R132.read_bytes()).hexdigest()}


def quaternions():
    # Quaternion units in the defining SU(2) representation, i*j=k.
    one = np.eye(2, dtype=complex)
    i = np.diag([1j, -1j])
    j = np.array([[0, 1], [-1, 0]], dtype=complex)
    units = [one, i, j, i @ j]
    matrices = np.array(units + [-u for u in units])
    lookup = {tuple(m.flat): n for n, m in enumerate(matrices)}
    mul = np.array([[lookup[tuple((a @ b).flat)] for b in matrices] for a in matrices])
    inv = [lookup[tuple(m.conj().T.flat)] for m in matrices]
    return matrices, mul, inv


def check():
    matrices, mul, inv = quaternions()
    named = named_pairs(matrices, mul)
    pairs = list(product(GROUP, repeat=2))
    products = np.array([mul[a, b] for a, b in pairs])
    split = np.eye(8)[products] / np.sqrt(8)
    projector = split @ split.T
    fine_id, coarse_id = np.eye(64), np.eye(8)
    near(split.T @ split, coarse_id)
    # Average of actual midpoint permutations, an independent Gauss projector.
    def destinations(left, mid, right):
        return [8 * mul[mul[left, a], inv[mid]] + mul[mul[mid, b], inv[right]] for a, b in pairs]

    gauss = sum(fine_id[:, destinations(0, m, 0)] for m in GROUP) / 8
    near(projector, gauss)
    for left, mid, right in product(GROUP, repeat=3):
        fine_indices = destinations(left, mid, right)
        coarse_indices = mul[mul[left, :], inv[right]]
        near(split[np.ix_(fine_indices, coarse_indices)], split)
    # Spinor transports are controlled by the same quantum links as the split.
    fine_color = np.array([matrices[a] @ matrices[b] for a, b in pairs])
    near(fine_color[:, None, :, :] * split[:, :, None, None],
         split[:, :, None, None] * matrices[None, :, :, :])
    chi = matrices.trace(axis1=1, axis2=2).real / 2
    for rest in GROUP:
        coarse_wilson = chi[mul[:, rest]]
        fine_wilson = chi[mul[products, rest]]
        near(fine_wilson[:, None] * split, split * coarse_wilson[None, :])
    # The naive (1,g) section keeps every coarse path product, but depends on the new frame.
    section = fine_id[:, :8]
    assert np.array_equal(products[:8], list(GROUP))
    near(section.T @ gauss @ section, coarse_id / 8)
    right_order = chi[mul[mul[1, 2], 3]]
    wrong_order = chi[mul[mul[2, 1], 3]]
    assert (right_order, wrong_order) == (-1, 1)
    # The unitary swaps the coarse space with im(split), fixes its complement.
    move = np.block([[np.zeros((8, 8)), split.T], [split, fine_id - projector]])
    ident = np.eye(72)
    near(move.T @ move, ident)
    near(move @ move, ident)
    balanced = (ident + 1j * move) / np.sqrt(2)
    near(balanced.conj().T @ balanced, ident)
    probe = ident[:, :8]
    first = balanced @ probe
    near(first[:8].conj().T @ first[:8], coarse_id / 2)
    near(first[8:].conj().T @ first[8:], coarse_id / 2)
    detector = balanced.conj().T[:, 8:] @ balanced[8:, :]
    coarse_branch, fine_branch = first.copy(), first.copy()
    coarse_branch[8:] = 0
    fine_branch[:8] = 0
    near(first.conj().T @ detector @ first, coarse_id)
    incoherent = sum(branch.conj().T @ detector @ branch for branch in (coarse_branch, fine_branch))
    near(incoherent, coarse_id / 2)
    return {**named, "group": "Q8", "local_dimensions_coarse_fine": [8, 64],
            "rank_midpoint_invariants": int(np.linalg.matrix_rank(gauss)),
            "frame_triples": 8**3, "basis_pairs_per_frame_triple": len(pairs),
            "ordered_path_spinor_products": len(pairs), "loop_products_with_return": len(pairs)*8,
            "wrong_order_W_example": [int(right_order), int(wrong_order)],
            "midpoint_invariant_probability_single_section": 1/8,
            "named_graph_swap_dimensions": 72, "balanced_steps": 2,
            "probability_fine_coherent": 1, "probability_fine_dephased": 0.5,
            "absolute_tolerance": TOL}


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
