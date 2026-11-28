#!/usr/bin/env python3
"""Exact, named history bridge between PR223 and R140/H6.

This module does no scientific work on import.  ``calibrate`` is a separate
two-step workload; ``run`` performs the declared finite experiment once.
Only the local R140 coin is used for propagation, including true idle = 1.
Gaussian rational arithmetic avoids numerical tolerances throughout.
"""
from collections import defaultdict
from fractions import Fraction as F
from functools import lru_cache
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from itertools import combinations
import json
from pathlib import Path


SOURCE_COMMIT = "fcc006b30e120fb536eba09288deeaf2dc42f167"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ENGINE = "analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py"
R140 = "analysis/R140_HAAR_SORKIN/verify.py"
EXPORT = "analysis/R140_HAAR_SORKIN/HISTORIES.json"
MIRROR_DEFINITION = (
    "analysis/MIRROR_PARTNERS_REVIEW_20261128/"
    "checks/original_audit/dynamics/check.py"
)
A_RECORD = (3, 3, 3, 2, 2, 2, 2, 2)
B_RECORD = (2, 2, 2, 2, 3, 3, 3, 2)


def z(a=0, b=0):
    return F(a), F(b)


ZERO, ONE, IMAG = z(), z(1), z(0, 1)
COIN_IDLE, COIN_FLIP = z(F(1, 2), F(-1, 2)), z(F(1, 2), F(1, 2))


def za(a, b):
    return a[0] + b[0], a[1] + b[1]


def zm(a, b):
    return a[0]*b[0] - a[1]*b[1], a[0]*b[1] + a[1]*b[0]


def zc(a):
    return a[0], -a[1]


def zp(a, n):
    out = ONE
    for _ in range(n):
        out = zm(out, a)
    return out


def zn(a):
    return a[0]*a[0] + a[1]*a[1]


def vs(v, a):
    return tuple(zm(x, a) for x in v)


def va(v, w):
    return tuple(za(x, y) for x, y in zip(v, w))


def inner(v, w):
    out = ZERO
    for x, y in zip(v, w):
        out = za(out, zm(zc(x), y))
    return out


def norm(v):
    return sum((zn(x) for x in v), F(0))


def jsz(a):
    return [str(a[0]), str(a[1])]


def jsv(v):
    return [jsz(a) for a in v]


def freeze(x):
    return tuple(freeze(v) for v in x) if isinstance(x, list) else x


def load_module(path, label):
    spec = spec_from_file_location(label, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(None)
def sources(root):
    # The source module's __main__ campaigns are deliberately not invoked.
    return load_module(root / R140, "r140_named_history_source")


class NamedBridge:
    def __init__(self, root):
        self.source = sources(root)
        self.e = self.source.E

    def cp(self, graph):
        def swap(s):
            return ((s & 1) << 1) | ((s & 2) >> 1) | ((s & 4) << 1) | ((s & 8) >> 1)
        return self.source.rooted(tuple(
            (self.e["mirror_name"](u), swap(s)) for u, s in reversed(graph)
        ))

    @lru_cache(None)
    def local_terms(self, graph):
        """All local-coin branches, with names and chosen active sites retained."""
        active = tuple(u for u, _, fine in self.source.tiling(graph) if fine is not None)
        terms = []
        for count in range(len(active) + 1):
            for selected in combinations(active, count):
                after_i = self.source.flip_named(graph, frozenset(selected))
                out = self.source.rooted(self.e["transport"](after_i, 2))
                coefficient = zm(zp(COIN_IDLE, len(active)-count), zp(COIN_FLIP, count))
                terms.append((out, coefficient, selected))
        return tuple(terms)

    def replay(self, initial, steps):
        paths = {((), self.source.rooted(initial)): ONE}
        visited = set()
        layer_sizes = []
        for _ in range(steps):
            following = defaultdict(lambda: ZERO)
            for (record, graph), amplitude in paths.items():
                visited.add(graph)
                for out, coefficient, _selected in self.local_terms(graph):
                    key = record + (len(out),), out
                    following[key] = za(following[key], zm(amplitude, coefficient))
            paths = {key: value for key, value in following.items() if value != ZERO}
            layer_sizes.append({"records_and_ends": len(paths),
                                "graphs": len({g for _, g in paths})})
        return paths, visited, layer_sizes

    def local_covariance(self, graph):
        mirror = self.cp(graph)
        assert self.cp(mirror) == self.source.rooted(graph)
        active = {u for u, _, fine in self.source.tiling(graph) if fine is not None}
        mirror_active = {u for u, _, fine in self.source.tiling(mirror) if fine is not None}
        assert {self.e["mirror_name"](u) for u in active} == mirror_active
        mirrored_terms = {frozenset(sel): (out, weight)
                          for out, weight, sel in self.local_terms(mirror)}
        for out, weight, selected in self.local_terms(graph):
            mapped = frozenset(self.e["mirror_name"](u) for u in selected)
            other, other_weight = mirrored_terms[mapped]
            assert other == self.cp(out) and other_weight == weight
            flipped = self.source.flip_named(graph, frozenset(selected))
            assert self.cp(flipped) == self.source.flip_named(mirror, mapped)
        assert self.cp(self.e["transport"](graph, 2)) == self.source.rooted(
            self.e["transport"](mirror, 2))
        return len(self.local_terms(graph))


def identity(n):
    return tuple(range(n))


def compose(p, q):
    """Column permutation of P Q: old index i goes to p[q[i]]."""
    return tuple(p[q[i]] for i in range(len(p)))


def inverse(p):
    return tuple(p.index(i) for i in range(len(p)))


def permute(p, v):
    out = [ZERO] * len(v)
    for i, item in enumerate(v):
        out[p[i]] = item
    return tuple(out)


def history_permutation(record, op2, op3):
    out = identity(len(op2))
    for length in record:
        op = op2 if length == 2 else op3 if length == 3 else identity(len(op2))
        out = compose(op, out)
    return out


def gate(record, phase):
    # Physical unitary after the FIRST actual step, on the entire L=3 subspace.
    return phase if record and record[0] == 3 else ONE


def field_outputs(paths, op2, op3, initial, phase=ONE):
    out = defaultdict(lambda: (ZERO,) * len(initial))
    for (record, graph), amplitude in paths.items():
        field = permute(history_permutation(record, op2, op3), initial)
        out[graph] = va(out[graph], vs(field, zm(amplitude, gate(record, phase))))
    return dict(out)


def probabilities(vectors, denominator):
    return {g: norm(v) / denominator for g, v in vectors.items()}


def pair_data(paths, endpoint, op2, op3, initial, denominator, phase):
    af = permute(history_permutation(A_RECORD, op2, op3), initial)
    bf = permute(history_permutation(B_RECORD, op2, op3), initial)
    a = vs(af, zm(paths[A_RECORD, endpoint], gate(A_RECORD, phase)))
    b = vs(bf, zm(paths[B_RECORD, endpoint], gate(B_RECORD, phase)))
    cross = 2 * inner(b, a)[0] / denominator
    return {"s": jsz(tuple(x / denominator for x in inner(bf, af))),
            "mu_A": str(norm(a) / denominator),
            "mu_B": str(norm(b) / denominator),
            "I2": str(cross), "P19": str(norm(va(a, b)) / denominator)}


def matrix_permutation(matrix):
    assert matrix.rows == matrix.cols
    out = []
    for j in range(matrix.cols):
        ones = [i for i in range(matrix.rows) if matrix[i, j] == 1]
        assert len(ones) == 1
        assert all(matrix[i, j] == (1 if i == ones[0] else 0) for i in range(matrix.rows))
        out.append(ones[0])
    assert len(set(out)) == len(out)
    return tuple(out)


def incidence_from_w(matrix):
    # Matrix entries are 0 or 1/sqrt(2); squaring is an exact integer check.
    out = []
    for i in range(matrix.rows):
        row = []
        for j in range(matrix.cols):
            value = matrix[i, j]
            assert value == 0 or (value.is_positive and value*value == F(1, 2))
            row.append(0 if value == 0 else 1)
        out.append(tuple(row))
    return tuple(out)


def incidence_lift(w, v):
    return tuple(tuple_sum(v[i] for i in range(len(w)) if w[i][j])
                 for j in range(len(w[0])))


def tuple_sum(items):
    out = ZERO
    for value in items:
        out = za(out, value)
    return out


def get_registers(root, register_bundle):
    if register_bundle is not None:
        return register_bundle
    module = load_module(HERE / "register_bridge.py", "r140_mirror_register_bridge")
    return module.build_registers(root)


def calibrate(root=None):
    root = Path(root) if root is not None else ROOT
    bridge = NamedBridge(root)
    x = bridge.e["named"]((1, 2, 0))
    p, v, _ = bridge.replay(x, 2)
    pm, vm, _ = bridge.replay(bridge.cp(x), 2)
    assert {(r, bridge.cp(g)): a for (r, g), a in p.items()} == pm
    c = (ONE, ONE, ZERO)
    m, j = (1, 2, 0), (0, 2, 1)
    a, b = field_outputs(p, m, j, c), field_outputs(pm, m, j, c)
    assert all(a[g] == b[bridge.cp(g)] for g in a)
    return {"steps": 2, "named_path_entries": len(p)+len(pm),
            "visited_named_graphs": len(v | vm), "field_dimension": 3,
            "no_full_campaign": True}


def run(root=None, register_bundle=None):
    root = Path(root) if root is not None else ROOT
    bridge = NamedBridge(root)
    exported = json.loads((root / EXPORT).read_text())
    original_ends = tuple(freeze(g) for g in exported["named_endpoints"])
    expected = {}
    for row in exported["branches"]:
        record = tuple(row["lengths"])
        for endpoint, re, im in row["amplitudes"]:
            expected[record, original_ends[endpoint]] = z(F(re, 16), F(im, 16))
    initial = bridge.e["named"]((1, 2, 0))
    paths, visited, layers = bridge.replay(initial, 8)
    mirrored, mirror_visited, mirror_layers = bridge.replay(bridge.cp(initial), 8)
    assert paths == expected, "Local-coin replay differs from frozen R140 amplitudes"
    assert {(r, bridge.cp(g)): a for (r, g), a in paths.items()} == mirrored
    records = sorted({r for r, _ in paths})
    assert len(records) == 92
    assert sorted({g for _, g in paths}) == list(original_ends)
    assert len(original_ends) == 40
    mirror_ends = sorted({g for _, g in mirrored})
    mirror_index = {g: i for i, g in enumerate(mirror_ends)}
    endpoint_map = [mirror_index[bridge.cp(g)] for g in original_ends]
    assert sorted(endpoint_map) == list(range(40))
    local_choices = sum(bridge.local_covariance(g) for g in visited | mirror_visited)
    endpoint19 = original_ends[19]
    assert {r for r, g in paths if g == endpoint19} == {A_RECORD, B_RECORD}
    assert paths[A_RECORD, endpoint19] == z(F(-1, 16), F(1, 16))
    assert paths[B_RECORD, endpoint19] == z(F(1, 16), F(-1, 16))
    # C' preserves every entry of a length record.  These two arms are distinct.
    assert A_RECORD != B_RECORD

    mixed = bridge.e["named"]((1, 2, 12))
    sites = tuple(u for u, _, fine in bridge.source.tiling(mixed) if fine is not None)
    assert len(sites) == 2
    corners = [bridge.source.flip_named(mixed, frozenset(mask))
               for n in range(3) for mask in combinations(sites, n)]
    assert len(set(corners)) == 4
    for graph in corners + [bridge.cp(g) for g in corners]:
        assert len(bridge.local_terms(graph)) == 4
        assert all(zn(a) == F(1, 4) for _, a, _ in bridge.local_terms(graph))
        bridge.local_covariance(graph)

    bundle = get_registers(root, register_bundle)
    splus, tplus = matrix_permutation(bundle["S_plus"]), matrix_permutation(bundle["T_plus"])
    sminus, tminus = matrix_permutation(bundle["S_minus"]), matrix_permutation(bundle["T_minus"])
    wplus, wminus = incidence_from_w(bundle["W_plus"]), incidence_from_w(bundle["W_minus"])
    assert wplus == wminus and splus == sminus and tplus == tminus
    m, j = (1, 2, 0), (0, 2, 1)
    mi = inverse(m)
    assert compose(compose(j, m), j) == mi and mi != m
    assert compose(j, m) != compose(m, j)
    case_rows = []
    for prep_name, initial3 in (
        ("published_c", (ONE, ONE, ZERO)),
        ("phase_sensitive_control", (ONE, IMAG, ZERO)),
    ):
        for phase_name, phase in (("0", ONE), ("pi/2", IMAG)):
            original = field_outputs(paths, m, j, initial3, phase)
            copy = field_outputs(mirrored, m, j, initial3, phase)
            reflected_initial = permute(j, initial3)
            orientation = field_outputs(mirrored, mi, j, reflected_initial, phase)
            wrong = field_outputs(mirrored, m, j, reflected_initial, phase)
            rp = field_outputs(paths, splus, tplus, incidence_lift(wplus, initial3), phase)
            rm = field_outputs(mirrored, sminus, tminus, incidence_lift(wminus, initial3), phase)
            rj = field_outputs(mirrored, inverse(sminus), tminus,
                               incidence_lift(wminus, reflected_initial), phase)
            ps = probabilities(original, 2)
            pc, pj, pw = (probabilities(v, 2) for v in (copy, orientation, wrong))
            assert sum(ps.values()) == sum(pc.values()) == sum(pj.values()) == sum(pw.values()) == 1
            rows = []
            for k, graph in enumerate(original_ends):
                mg = bridge.cp(graph)
                assert copy[mg] == original[graph]
                assert orientation[mg] == permute(j, original[graph])
                assert rp[graph] == incidence_lift(wplus, original[graph])
                assert rm[mg] == incidence_lift(wminus, copy[mg])
                assert rj[mg] == incidence_lift(wminus, orientation[mg])
                assert norm(rp[graph]) / 4 == ps[graph]
                assert norm(rm[mg]) / 4 == pc[mg]
                assert norm(rj[mg]) / 4 == pj[mg]
                assert ps[graph] == pc[mg] == pj[mg]
                # The three resolved character detectors transform E_k -> J E_k J.
                det = [zn(v)/2 for v in original[graph]]
                mirrored_det = [zn(orientation[mg][j[k]])/2 for k in range(3)]
                assert det == mirrored_det
                rows.append({"endpoint": k, "mirror_endpoint": endpoint_map[k],
                             "field_numerator": jsv(original[graph]),
                             "physical_mirror_numerator": jsv(orientation[mg]),
                             "P": str(ps[graph]),
                             "character_detectors": list(map(str, det)),
                             "wrong_same_M_P": str(pw[mg]),
                             "wrong_same_M_field_numerator": jsv(wrong[mg])})
            selected = pair_data(paths, endpoint19, m, j, initial3, 2, phase)
            selected_copy = pair_data(mirrored, bridge.cp(endpoint19), m, j, initial3, 2, phase)
            selected_orientation = pair_data(mirrored, bridge.cp(endpoint19), mi, j,
                                             reflected_initial, 2, phase)
            selected_wrong = pair_data(mirrored, bridge.cp(endpoint19), m, j,
                                       reflected_initial, 2, phase)
            assert selected == selected_copy == selected_orientation
            assert F(selected["P19"]) == ps[endpoint19]
            case_rows.append({"preparation": prep_name, "phase_after_first_step_L3": phase_name,
                              "initial3_numerator": jsv(initial3), "field_norm_denominator": 2,
                              "register_norm_denominator": 4,
                              "all40_vector_covariance": True, "all40_register_lifts": True,
                              "all40_detector_covariance": True, "normalization": "1",
                              "selected_pair": selected, "wrong_same_M_selected_pair": selected_wrong,
                              "wrong_same_M_vector_mismatches": sum(
                                  wrong[bridge.cp(g)] != permute(j, original[g]) for g in original_ends),
                              "wrong_same_M_probability_mismatches": sum(
                                  pw[bridge.cp(g)] != ps[g] for g in original_ends),
                              "outputs": rows})
    published0, publishedpi2, control0, controlpi2 = case_rows
    assert published0["selected_pair"]["I2"] == "-1/128"
    assert published0["selected_pair"]["P19"] == "1/128"
    assert publishedpi2["selected_pair"]["I2"] == "0"
    assert publishedpi2["selected_pair"]["P19"] == "1/64"
    assert control0["selected_pair"]["I2"] == "0"
    assert controlpi2["selected_pair"]["I2"] == "-1/128"
    assert controlpi2["wrong_same_M_selected_pair"]["I2"] == "1/128"
    assert controlpi2["wrong_same_M_selected_pair"]["P19"] == "3/128"

    # Exact two-sector Gram calculation for an equal mixture/superposition when
    # the detector sums corresponding endpoints with orthogonal register-sector blocks.
    # A sector record has the SAME value on both arms within a given sector.
    # Thus its overlap multiplier is delta_(d_A,d_B)=1, unlike a path record.
    before_partner_record = F(0)
    after_partner_record = F(0)
    after_arm_record = F(0)
    partner_gram_rows = []
    paired_arm_a, paired_arm_b, paired_d = [], [], []
    for sector, basis_key, ps0, g0, sop, top, wop in (
        (1, "even_plus", paths, endpoint19, splus, tplus, wplus),
        (-1, "even_minus", mirrored, bridge.cp(endpoint19), sminus, tminus, wminus),
    ):
        d_labels = [sum((s & 1) - ((s >> 1) & 1) - ((s >> 2) & 1)
                        + ((s >> 3) & 1) for _, s in graph)
                    for graph in bundle[basis_key]]
        assert set(d_labels) == {sector}
        initial6 = incidence_lift(wop, (ONE, ONE, ZERO))
        arm_a = permute(history_permutation(A_RECORD, sop, top), initial6)
        arm_b = permute(history_permutation(B_RECORD, sop, top), initial6)
        labels_a = {d_labels[k] for k, value in enumerate(arm_a) if value != ZERO}
        labels_b = {d_labels[k] for k, value in enumerate(arm_b) if value != ZERO}
        assert labels_a == labels_b == {sector}
        record_overlap = F(int(labels_a == labels_b))
        i2 = F(pair_data(ps0, g0, sop, top, initial6, 4, ONE)["I2"])
        assert i2 == F(published0["selected_pair"]["I2"])
        paired_arm_a.extend(vs(arm_a, ps0[A_RECORD, g0]))
        paired_arm_b.extend(vs(arm_b, ps0[B_RECORD, g0]))
        paired_d.extend(d_labels)
        before_partner_record += i2 / 2
        after_partner_record += record_overlap * i2 / 2
        after_arm_record += F(int(A_RECORD == B_RECORD)) * i2 / 2
        partner_gram_rows.append({"d_A": sector, "d_B": sector,
                                  "weight": "1/2", "sector_record_overlap": "1",
                                  "weighted_I2": str(i2/2)})
    assert before_partner_record == after_partner_record == F(-1, 128)
    assert after_arm_record == 0

    def record_isometry(vector, labels):
        """|i> -> |i> tensor |labels[i]> with an orthogonal two-state record."""
        out = [ZERO] * (2*len(vector))
        assert len(labels) == len(vector) and set(labels) <= {0, 1}
        for k, amplitude in enumerate(vector):
            out[2*k + labels[k]] = amplitude
        return tuple(out)

    # The six-bit preparation has denominator 2; equal amplitudes of the two
    # partner sectors introduce another sqrt(2), hence squared denominator 8.
    d_record_labels = [0 if value == 1 else 1 for value in paired_d]
    recorded_a = record_isometry(paired_arm_a, d_record_labels)
    recorded_b = record_isometry(paired_arm_b, d_record_labels)
    path_recorded_a = record_isometry(paired_arm_a, [0]*12)
    path_recorded_b = record_isometry(paired_arm_b, [1]*12)
    # This is the final representation of a record written along each history.
    # It is not a single map of an already recombined, unlabelled output state.
    assert 2*inner(paired_arm_b, paired_arm_a)[0]/8 == before_partner_record
    assert 2*inner(recorded_b, recorded_a)[0]/8 == after_partner_record
    assert 2*inner(path_recorded_b, path_recorded_a)[0]/8 == after_arm_record
    assert norm(recorded_a) == norm(paired_arm_a)
    assert norm(recorded_b) == norm(paired_arm_b)

    # A complete path record suppresses cross terms without changing each arm.
    # Dephasing the initial BIT register is a distinct, independently calculated control.
    bit_occupied = [k for k, value in enumerate(incidence_lift(wplus, (ONE, ONE, ZERO))) if value != ZERO]
    assert len(bit_occupied) == 4
    dephased_rows = []
    for phase_name, phase in (("0", ONE), ("pi/2", IMAG)):
        dep = {g: F(0) for g in original_ends}
        dep_m = {bridge.cp(g): F(0) for g in original_ends}
        dep_i2 = F(0)
        for bit in bit_occupied:
            basis = tuple(ONE if k == bit else ZERO for k in range(6))
            out = field_outputs(paths, splus, tplus, basis, phase)
            out_m = field_outputs(mirrored, sminus, tminus, basis, phase)
            for graph in original_ends:
                dep[graph] += norm(out[graph]) / 4
                dep_m[bridge.cp(graph)] += norm(out_m[bridge.cp(graph)]) / 4
            dep_i2 += F(pair_data(paths, endpoint19, splus, tplus, basis, 1, phase)["I2"]) / 4
        assert sum(dep.values()) == sum(dep_m.values()) == 1
        assert all(dep[g] == dep_m[bridge.cp(g)] for g in original_ends)
        assert dep_i2 == 0 and dep[endpoint19] == F(1, 64)
        # Independent complete length-record readout, with the coherent initial field.
        recorded = {g: F(0) for g in original_ends}
        for (record, graph), amplitude in paths.items():
            recorded[graph] += zn(amplitude)
        assert sum(recorded.values()) == 1 and recorded[endpoint19] == F(1, 64)
        dephased_rows.append({"phase": phase_name, "dephased_bit_I2": str(dep_i2),
                              "dephased_bit_P19": str(dep[endpoint19]),
                              "path_record_I2": "0", "path_record_P19": str(recorded[endpoint19]),
                              "all40_mirror_probabilities_equal": True,
                              "dephased_bit_uses_full_six_state_register": True,
                              "dephased_bit_distribution": [str(dep[g]) for g in original_ends],
                              "full_path_record_distribution": [str(recorded[g]) for g in original_ends]})

    branches = []
    original_index = {g: k for k, g in enumerate(original_ends)}
    for record in records:
        values = sorted((original_index[g], value) for (r, g), value in paths.items() if r == record)
        branches.append({"lengths": record,
                         "amplitudes": [[k, *jsz(value)] for k, value in values],
                         "mirror_amplitudes": [[endpoint_map[k], *jsz(value)] for k, value in values]})
    return {
        "status": "PASS_EXACT_FINITE_BRIDGE",
        "source_commit": SOURCE_COMMIT,
        "sources_sha256": {p: sha256((root/p).read_bytes()).hexdigest()
                           for p in (ENGINE, R140, EXPORT, MIRROR_DEFINITION)},
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "arithmetic": "Gaussian rationals; all comparisons exact",
        "local_coin": {"idle_active": jsz(COIN_IDLE), "flip_active": jsz(COIN_FLIP),
                       "true_idle": jsz(ONE), "product_over_independent_sites": True},
        "geometry": {"initial_named_graph": initial, "mirror_initial_named_graph": bridge.cp(initial),
                     "steps": 8, "history_count": 92, "endpoint_count": 40,
                     "exact_export_match": True, "exact_named_mirror_match": True,
                     "visited_graphs": len(visited | mirror_visited),
                     "local_choice_covariance_checks": local_choices,
                     "forward_layer_sizes": layers, "mirror_layer_sizes": mirror_layers,
                     "endpoint_map": endpoint_map, "named_endpoints": original_ends,
                     "mirror_named_endpoints": mirror_ends, "branches": branches,
                     "A": A_RECORD, "B": B_RECORD, "A_and_B_are_not_mirror_partners": True,
                     "mirror_of_A_keeps_record_A": True, "mirror_of_B_keeps_record_B": True},
        "two_site_control": {"word": [1, 2, 12], "sites": 2, "corners": 4,
                             "original_and_mirror_corners_checked": 8,
                             "each_one_step_branch_probability": "1/4"},
        "field_operator_control": {"M": m, "J": j, "J_M_J": mi,
                                   "J_M_J_equals_M_inverse": True,
                                   "J_does_not_commute_with_fixed_M": True,
                                   "other_lengths_use_identity": True},
        "field_cases": case_rows,
        "observer_controls": {
            "partner_label": "d=q1-q2, +1 on H_plus and -1 on H_minus",
            "H6_only_same_law_partner_reading": "identical; trace_distance=0",
            "partner_d_reading": "disjoint outcomes +1,-1; trace_distance=1",
            "d_record_is_identical_on_A_and_B_within_each_partner": True,
            "d_record_path_overlap": "1",
            "d_record_retains_within_partner_I2": str(after_partner_record),
            "equal_partner_weight_gram": partner_gram_rows,
            "actual_12bit_d_labels": paired_d,
            "paired_arm_A_numerator": jsv(paired_arm_a),
            "paired_arm_B_numerator": jsv(paired_arm_b),
            "paired_arm_squared_denominator": 8,
            "record_isometry_output_dimension": len(recorded_a),
            "exact_record_isometry_and_gram_checks": True,
            "complete_arm_record_path_overlap": "0",
            "complete_arm_record_I2": str(after_arm_record),
            "dephasing_controls": dephased_rows,
            "scope": "d distinguishes paired preparations; no superselection postulate"},
        "limitations": [
            "The independent register, preparation, and length-controlled field coupling are explicit inputs.",
            "Copy exchange with identity field and physical holonomy inversion with J are distinct lifts.",
            "J on the field pairs M,J with M^-1,J; it is not a symmetry of the unchanged M,J rule.",
            "Common forward-step covariance does not determine a thermodynamic arrow.",
            "The finite history experiment covers the specified eight-step cone, not all named graphs."
        ]
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
