"""Explicit ADD -> R040 mapping adapters.

Nothing in this module derives a quantum Hamiltonian from K1/K2.  The mapping
law is an imported MODEL_ASSUMPTION and is accepted only when the manifest says
so explicitly.  The carrier adapter loads the pinned source and verifies its
Git blob SHA-1 before calling the exact full_step implementation.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
from pathlib import Path
from typing import Callable, Mapping

import numpy as np

from .model import R040Parameters

EXPECTED_CARRIER_BLOB = "6e44c12cd1f27aadc9e2c73c1f82222944cd2e7b"
BIT_LAYOUT = ("a1", "b1", "a2", "b2")


def git_blob_sha1_bytes(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def git_blob_sha1(path: str | Path) -> str:
    return git_blob_sha1_bytes(Path(path).read_bytes())


def load_verified_carrier(carrier_path: str | Path,
                          expected_blob: str = EXPECTED_CARRIER_BLOB):
    """Load only the exact pinned carrier.py source; no path/name trust alone."""
    path = Path(carrier_path)
    if not path.is_file():
        raise FileNotFoundError(f"carrier source not found: {path}")
    observed = git_blob_sha1(path)
    if observed != expected_blob:
        raise ValueError(
            f"carrier Git blob mismatch: expected {expected_blob}, observed {observed}"
        )
    spec = importlib.util.spec_from_file_location("x26_pinned_now_carrier", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load verified carrier module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "full_step", None)):
        raise AttributeError("verified carrier source has no callable full_step")
    return module


def validate_word(word) -> list[int]:
    out = list(word)
    if not out or any(type(s) is not int or not 0 <= s < 16 for s in out):
        raise ValueError("ADD word must be a non-empty sequence of four-bit integers")
    return out


def particle_counts(word) -> dict[str, int]:
    """Counts in the carrier.py bit order a1,b1,a2,b2."""
    w = validate_word(word)
    return {name: int(sum((state >> bit) & 1 for state in w))
            for bit, name in enumerate(BIT_LAYOUT)}


def combinatorial_invariants(word) -> dict:
    w = validate_word(word)
    counts = particle_counts(w)
    half = {name: sum((s & mask) == val for s in w)
            for name, mask, val in [('A1',5,1),('A2',5,4),('A12',5,5),
                                    ('B1',10,2),('B2',10,8),('B12',10,10)]}
    k1, k2 = half['A1']*half['B1'], half['A2']*half['B2']
    return {'counts': counts, 'pure_half_counts': half, 'K1': k1, 'K2': k2, 'K': k1+k2,
            'bit_products': {'1': counts['a1']*counts['b1'], '2': counts['a2']*counts['b2']},
            'E0': not any(s in (3,12) for s in w) and not any(
                len(w)>1 and (w[i],w[(i+1)%len(w)]) in ((1,2),(4,8)) for i in range(len(w))),
            'definition': 'Kc = pure_Ac * pure_Bc; bit products are different invariants',
            'status': 'COMBINATORIAL_ONLY_NOT_QUANTUM_SUPERSELECTION'}


def local_motif_features(word, vertex: int, radius: int = 1) -> dict:
    """Ordered cyclic neighbourhood features; orientation is not quotiented out."""
    w = validate_word(word)
    if type(vertex) is not int or not 0 <= vertex < len(w):
        raise ValueError("anchor vertex outside ADD word")
    if type(radius) is not int or radius < 0 or 2 * radius + 1 > len(w):
        raise ValueError("radius must define a non-wrapping-size local window (cyclic indexing)")
    offsets = list(range(-radius, radius + 1))
    indices = [(vertex + offset) % len(w) for offset in offsets]
    states = [w[i] for i in indices]
    width = len(states)
    counts = [sum((s >> b) & 1 for s in states) for b in range(4)]
    split_count = sum(s in (3, 12) for s in states)
    # Match the exact oriented local merge motifs used by full_step.
    merge_count = 0
    for left, right in zip(indices[:-1], indices[1:]):
        if (w[left], w[right]) in ((1, 2), (4, 8)):
            merge_count += 1
    occupancy = float(sum(counts) / (4.0 * width))
    species_1 = float((counts[0] + counts[1]) / (2.0 * width))
    species_2 = float((counts[2] + counts[3]) / (2.0 * width))
    return {
        "vertex": vertex,
        "radius": radius,
        "offsets": offsets,
        "indices": indices,
        "states": states,
        "bit_counts": {name: int(counts[i]) for i, name in enumerate(BIT_LAYOUT)},
        "occupancy": occupancy,
        "species_1_density": species_1,
        "species_2_density": species_2,
        "split_motif_fraction": float(split_count / width),
        "oriented_merge_motifs": int(merge_count),
        "feature_vector": [occupancy, species_1, species_2,
                           float(split_count / width), float(merge_count / max(1, width - 1))],
        "orientation": "ordered offsets -r..+r on the directed cyclic carrier",
    }


def _finite_positive(law: Mapping, key: str) -> float:
    value = law.get(key)
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError(f"mapping law {key} must be finite and positive")
    return float(value)


def map_local_motifs_to_r040(word, anchors: Mapping[str, int], law: Mapping) -> dict:
    """Evaluate one explicit local-density / local-barrier mapping hypothesis.

    q_a is the local total bit occupancy in a radius-r neighbourhood.
    E_a=E_a^0+lambda_a*q_a.  Each bond is
      t_ab = t0*exp[-alpha*(ell0 + beta*abs(q_a-q_b))].
    Identical V and 1 neighbourhood features therefore imply E_V=E_1 and
    gamma_d=t_2, an explicit local Z2 condition; it is not imposed by tuning.
    """
    if law.get("source") != "MODEL_ASSUMPTION" or law.get("accepted") is not True:
        raise ValueError("Phi mapping requires an explicitly accepted MODEL_ASSUMPTION")
    if not isinstance(law.get("assumption"), str) or not law["assumption"].strip():
        raise ValueError("Phi mapping assumption text is required")
    required = ("radius", "E_pair_0", "E_2_0", "lambda_pair", "lambda_2",
                "t0", "barrier_0", "barrier_contrast", "alpha", "kappa", "g")
    missing = [k for k in required if law.get(k) is None]
    if missing:
        raise ValueError("Phi mapping missing parameters: " + ", ".join(missing))
    radius = law["radius"]
    if type(radius) is not int or radius < 0:
        raise ValueError("mapping radius must be a non-negative integer")
    if set(anchors) != {"V", "1", "2"}:
        raise ValueError("anchors must map exactly the R040 roles V, 1, 2")
    q = {role: local_motif_features(word, int(vertex), radius)
         for role, vertex in anchors.items()}
    densities = {role: float(q[role]["occupancy"]) for role in ("V", "1", "2")}
    e_pair_0 = float(law["E_pair_0"])
    e2_0 = float(law["E_2_0"])
    lam_pair = float(law["lambda_pair"])
    lam2 = float(law["lambda_2"])
    t0 = _finite_positive(law, "t0")
    barrier0 = float(law["barrier_0"])
    barrier_contrast = float(law["barrier_contrast"])
    alpha = _finite_positive(law, "alpha")
    kappa = _finite_positive(law, "kappa")
    g = _finite_positive(law, "g")
    all_values = [e_pair_0, e2_0, lam_pair, lam2, barrier0, barrier_contrast]
    if not all(math.isfinite(float(x)) for x in all_values):
        raise ValueError("all mapping coefficients must be finite")

    def hopping(left: str, right: str) -> float:
        effective_barrier = barrier0 + barrier_contrast * abs(densities[left] - densities[right])
        exponent = -alpha * effective_barrier
        # Guard against overflow while preserving the explicitly selected law.
        if exponent > 700 or exponent < -700:
            raise ValueError("local hopping exponent outside safe finite range")
        return float(t0 * math.exp(exponent))

    params = R040Parameters(
        E_V=e_pair_0 + lam_pair * densities["V"],
        E_1=e_pair_0 + lam_pair * densities["1"],
        E_2=e2_0 + lam2 * densities["2"],
        t_1=hopping("V", "1"),
        gamma_d=hopping("V", "2"),
        t_2=hopping("1", "2"),
        kappa=kappa,
        g=g,
        bath_onsite=float(law.get("bath_onsite", 0.0)),
    )
    if not math.isfinite(params.bath_onsite):
        raise ValueError("bath_onsite must be finite")
    z2_local = (abs(densities["V"] - densities["1"]) <= float(law.get("feature_tolerance", 1e-14)))
    return {
        "effective_barriers": {a+b: barrier0 + barrier_contrast*abs(densities[a]-densities[b])
                               for a,b in [('V','1'),('V','2'),('1','2')]},
        "parameters": {name: float(value) for name, value in params.__dict__.items()},
        "local_features": q,
        "local_density": densities,
        "local_Z2_condition": {
            "V_and_1_equal_local_density": bool(z2_local),
            "E_V_equals_E_1": bool(math.isclose(params.E_V, params.E_1, rel_tol=0.0,
                                                   abs_tol=float(law.get("feature_tolerance", 1e-14)))),
            "gamma_d_equals_t_2": bool(math.isclose(params.gamma_d, params.t_2, rel_tol=0.0,
                                                       abs_tol=float(law.get("feature_tolerance", 1e-14)))),
            "interpretation": "local motif equivalence implies a Z2-symmetric parameter subfamily under this postulate",
        },
        "provenance": {name: {"source": "MODEL_ASSUMPTION",
                                 "assumption": "Derived by the accepted local Phi law: " + law["assumption"]}
                       for name in params.__dict__},
        "mapping_status": "MODEL_ASSUMPTION_EVALUATED_NOT_ADD_DERIVED",
        "global_K_used_as_mapping_input": False,
        "assumption": law["assumption"],
    }


def permute_vertex_motifs(word, permutation: list[int]) -> list[int]:
    w = validate_word(word)
    if sorted(permutation) != list(range(len(w))):
        raise ValueError("permutation must be a bijection on all vertex indices")
    return [w[i] for i in permutation]


def advance_one_add_step(word, anchors: Mapping[str, int], full_step: Callable,
                         interaction: bool = True) -> dict:
    """Execute one real carrier step and transport role anchors by payload map."""
    w = validate_word(word)
    if set(anchors) != {"V", "1", "2"}:
        raise ValueError("anchors must map exactly V, 1, 2")
    if any(type(i) is not int or not 0 <= i < len(w) for i in anchors.values()):
        raise ValueError("anchor index outside current carrier")
    before = combinatorial_invariants(w)
    next_word, payload_map = full_step(w, interaction=interaction)
    next_word = validate_word(next_word)
    if not isinstance(payload_map, dict) or set(payload_map) != set(range(len(w))):
        raise ValueError("carrier full_step did not return a complete old-node -> new-node map")
    if any(type(v) is not int or not 0 <= v < len(next_word) for v in payload_map.values()):
        raise ValueError("carrier payload map points outside the next word")
    next_anchors = {role: int(payload_map[index]) for role, index in anchors.items()}
    after = combinatorial_invariants(next_word)
    if before["pure_half_counts"] != after["pure_half_counts"] or before["counts"] != after["counts"] or (before["K1"], before["K2"]) != (after["K1"], after["K2"]):
        raise ArithmeticError("pinned carrier step did not preserve declared particle counts/K1/K2")
    return {
        "word_before": w,
        "word_after": next_word,
        "anchors_before": dict(anchors),
        "anchors_after": next_anchors,
        "payload_map": {str(k): int(v) for k, v in payload_map.items()},
        "invariants_before": before,
        "invariants_after": after,
        "length_before": len(w),
        "length_after": len(next_word),
        "length_change": len(next_word) - len(w),
        "status": "ONE_PINNED_ADD_STEP_EXECUTED",
    }


def run_add_mapping_smoke(word, anchors: Mapping[str, int], law: Mapping,
                          carrier_path: str | Path, seed: int = 20261109,
                          interaction: bool = True) -> dict:
    """Current snapshot -> Phi -> K-preserving motif shuffle -> real F step."""
    module = load_verified_carrier(carrier_path)
    w = validate_word(word)
    original_inv = combinatorial_invariants(w)
    original = map_local_motifs_to_r040(w, anchors, law)
    rng = np.random.default_rng(seed)
    permutation = rng.permutation(len(w)).tolist()
    shuffled_word = permute_vertex_motifs(w, permutation)
    shuffled_inv = combinatorial_invariants(shuffled_word)
    shuffled = map_local_motifs_to_r040(shuffled_word, anchors, law)
    if (original_inv["K1"], original_inv["K2"], original_inv["counts"]) != (
            shuffled_inv["K1"], shuffled_inv["K2"], shuffled_inv["counts"]):
        raise ArithmeticError("vertex permutation unexpectedly changed global K/counts")
    p0 = np.asarray(list(original["parameters"].values()), dtype=float)
    p1 = np.asarray(list(shuffled["parameters"].values()), dtype=float)
    mapping_change_norm = float(np.linalg.norm(p0 - p1))
    step = advance_one_add_step(w, anchors, module.full_step, interaction=interaction)
    next_mapping = map_local_motifs_to_r040(step["word_after"], step["anchors_after"], law)
    return {
        "schema": 1,
        "carrier_source": {"path_name": Path(carrier_path).name,
                           "expected_git_blob_sha1": EXPECTED_CARRIER_BLOB,
                           "observed_git_blob_sha1": git_blob_sha1(carrier_path),
                           "verified": True},
        "snapshot": {"length": len(w), "anchors": dict(anchors), "invariants": original_inv},
        "phi": original,
        "K_preserving_permutation_control": {
            "seed": int(seed),
            "permutation": permutation,
            "invariants_unchanged": True,
            "mapping_parameter_l2_change": mapping_change_norm,
            "mapping_changed": bool(mapping_change_norm > 1e-12),
            "phi_permuted": shuffled,
            "interpretation": "a K-preserving permutation can alter local motifs; this is a sensitivity control, not a proof of causal physics",
        },
        "one_step": step,
        "phi_after_one_step": next_mapping,
        "status": "ADD_MAPPING_SMOKE_EXECUTED_WITH_EXPLICIT_MODEL_ASSUMPTION",
        "scientific_status": "CONDITIONAL_MAPPING_TEST_NOT_ADD_DERIVATION",
    }
