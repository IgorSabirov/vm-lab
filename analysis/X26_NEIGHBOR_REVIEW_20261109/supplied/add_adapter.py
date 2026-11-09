#!/usr/bin/env python3
"""X26-B ADD-derived adapter boundary.

No ADD quantum lift, physical mode map, Hamiltonian, or continuum coupling is
silently invented here. Functions marked TODO are deliberate blockers.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Sequence
import numpy as np


class MissingPhysicsInput(NotImplementedError):
    pass


@dataclass
class StubStatus:
    name: str
    status: str
    missing_input: str
    required_output: str


@dataclass
class OrbitLiftCheck:
    status: str
    dimension: int
    unitarity_error: float | None
    commutator_K1_norm: float | None
    commutator_K2_norm: float | None
    note: str


def load_exact_add_carrier(*, source_path: str | None = None, expected_blob: str = "6e44c12cd1f27aadc9e2c73c1f82222944cd2e7b") -> Any:
    """TODO: load exact carrier.py, verify its Git blob and source contract."""
    raise MissingPhysicsInput(
        "ADD source adapter is a stub: provide exact carrier.py bytes, Git blob verification, "
        "and explicit FIG2A_FULL state/transition API. Expected blob: " + expected_blob
    )


def enumerate_add_patch(*, carrier: Any, L: int, state_words: Sequence[int]) -> Any:
    """TODO: enumerate a closed local patch and calculate K1/K2 from exact carrier semantics."""
    raise MissingPhysicsInput("No exact ADD patch enumerator or state-word-to-(A,B) parser is supplied.")


def derive_two_internal_modes(*, patch: Any, mapping_spec: dict[str, Any] | None = None) -> Any:
    """TODO: derive two physically justified resonant modes from ADD, not arbitrary basis vectors."""
    raise MissingPhysicsInput("No validated mapping from ADD configurations/half-pairs to quantum resonant modes.")


def derive_internal_hamiltonian(*, modes: Any, energy_calibration: dict[str, Any] | None = None) -> np.ndarray:
    """TODO: derive Hd from a specified microscopic dynamics or calibrated experiment."""
    raise MissingPhysicsInput("No ADD-derived quantum generator, energy calibration, or operator map is supplied.")


def derive_continuum_coupling(*, modes: Any, environment: Any, interaction: Any) -> np.ndarray:
    """TODO: calculate W[mu,c] = <E,mu|V|d_c> for all open channels."""
    raise MissingPhysicsInput("No physical environment, interaction operator V, continuum normalization, or form factors supplied.")


def derive_environment(*, environment_spec: dict[str, Any] | None = None) -> Any:
    """TODO: define the physical continuum, its channels, density of states and thresholds."""
    raise MissingPhysicsInput("No physical continuum/channel specification or density of states supplied.")


def specify_perturbation_symmetries(*, symmetry_spec: dict[str, Any] | None = None) -> Any:
    """TODO: define the exact symmetry group and separate preserving/breaking perturbations."""
    raise MissingPhysicsInput("No physical symmetry representation or perturbation classes supplied.")


def specify_loading_protocol(*, protocol_spec: dict[str, Any] | None = None) -> Any:
    """TODO: define a realizable preparation/loading protocol, including time-dependent controls if any."""
    raise MissingPhysicsInput("No physical input channel or BIC loading protocol supplied.")


def validate_finite_closed_orbit_lift(
    next_index: Sequence[int],
    K1: Sequence[int],
    K2: Sequence[int],
    *,
    atol: float = 1e-12,
) -> OrbitLiftCheck:
    """Validate a permutation-unitary only on a genuinely closed finite orbit.

    This does NOT build the full infinite direct-sum Hilbert space of a growing ADD
    carrier. A truncated, non-closed growing orbit must not be turned into a fake
    finite unitary.
    """
    nxt = np.asarray(next_index, dtype=int)
    k1 = np.asarray(K1, dtype=int)
    k2 = np.asarray(K2, dtype=int)
    n = len(nxt)
    if n == 0 or k1.shape != (n,) or k2.shape != (n,):
        raise ValueError("next_index, K1 and K2 must be nonempty vectors of the same length")
    if np.any(nxt < 0) or np.any(nxt >= n) or len(set(nxt.tolist())) != n:
        return OrbitLiftCheck("FAIL_NOT_A_FINITE_PERMUTATION", n, None, None, None,
                              "The supplied finite subset is not closed under a bijective transition.")
    # U|j> = |next_index[j]>
    U = np.zeros((n, n), dtype=np.complex128)
    U[nxt, np.arange(n)] = 1.0
    K1op = np.diag(k1.astype(float))
    K2op = np.diag(k2.astype(float))
    unitary_error = float(np.linalg.norm(U.conj().T @ U - np.eye(n)))
    comm1 = float(np.linalg.norm(U @ K1op - K1op @ U))
    comm2 = float(np.linalg.norm(U @ K2op - K2op @ U))
    passed = unitary_error <= atol and comm1 <= atol and comm2 <= atol
    return OrbitLiftCheck(
        "PASS_CONDITIONAL_FINITE_ORBIT_LIFT" if passed else "FAIL_INVARIANT_OR_UNITARITY",
        n, unitary_error, comm1, comm2,
        "Conditional permutation lift on this closed finite orbit only; no physical Hilbert-space or superselection claim.",
    )


def run_x26_b() -> dict[str, Any]:
    """Return explicit blocker statuses; never substitutes guessed physics."""
    items = [
        StubStatus("exact_ADD_source", "BLOCKED_MISSING", "carrier.py exact bytes + blob verification", "validated FIG2A_FULL transition function"),
        StubStatus("ADD_patch_enumeration", "BLOCKED_MISSING", "state-word parser and exact I/Q transition semantics", "patch with exact K1/K2 and compatible-pair witnesses"),
        StubStatus("quantum_lift", "BLOCKED_MISSING", "Hilbert-space construction and map X -> |psi_X>", "linear generator consistent with ADD transition"),
        StubStatus("two_internal_modes", "BLOCKED_MISSING", "physical mode-identification rule", "two independent modes in one common (K1,K2) sector"),
        StubStatus("internal_Hamiltonian", "BLOCKED_MISSING", "microscopic dynamics or independently calibrated energies", "Hermitian Hd and energy reference"),
        StubStatus("continuum", "BLOCKED_MISSING", "environment, open channels, density of states, thresholds", "normalized continuum Hilbert space"),
        StubStatus("coupling_matrix_W", "BLOCKED_MISSING", "interaction V and all open-channel matrix elements", "full W_mu,c(E) including which-path channels"),
        StubStatus("symmetry_protection", "BLOCKED_MISSING", "symmetry representation and perturbation classes", "protected-vs-accidental classification"),
        StubStatus("BIC_loading", "BLOCKED_MISSING", "physical input and preparation protocol", "preparability test separated from BIC existence"),
    ]
    return {
        "run_id": "X26_B_ADD_DERIVED_SPECTRAL_LIFT",
        "status": "BLOCKED_NO_PHYSICAL_ADD_SPECTRAL_INPUTS",
        "items": [asdict(x) for x in items],
        "available_conditional_helper": "validate_finite_closed_orbit_lift",
        "warning": "Do not replace any BLOCKED item with arbitrary fitted matrices and then call the result ADD-derived.",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run_x26_b(), indent=2, ensure_ascii=False))
