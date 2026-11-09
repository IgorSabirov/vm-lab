#!/usr/bin/env python3
"""X26-A: minimal two-mode Friedrich-Wintgen BIC control model.

This is an executable spectral toy model. It is NOT an ADD-derived quantum lift.
The ADD-derived parts are intentionally separated into add_adapter.py stubs.

Units: hbar = 1. Continuum states are energy-normalized. W has units sqrt(energy).
For a flat finite band and energy-independent form factors, the retarded self-energy
is Sigma(E+i0) = J * [log((E-Emin)/(Emax-E)) - i*pi], J = W^dagger W.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable
import json
import math
import numpy as np

Array = np.ndarray


class ModelInputError(ValueError):
    """Raised when a model violates its declared mathematical contract."""


def _complex_array(value: Any, *, ndim: int | None = None) -> Array:
    arr = np.asarray(value, dtype=np.complex128)
    if ndim is not None and arr.ndim != ndim:
        raise ModelInputError(f"expected {ndim} dimensions, got shape {arr.shape}")
    if not np.all(np.isfinite(arr.real)) or not np.all(np.isfinite(arr.imag)):
        raise ModelInputError("arrays must contain finite values")
    return arr


def numerical_rank(matrix: Array, rtol: float = 1e-10) -> int:
    matrix = _complex_array(matrix, ndim=2)
    if matrix.size == 0:
        return 0
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    if singular_values.size == 0 or singular_values[0] == 0:
        return 0
    return int(np.sum(singular_values > rtol * singular_values[0]))


def null_vector_for_two_modes(W: Array, rtol: float = 1e-10) -> tuple[Array | None, int, Array]:
    """Return a normalized right-null vector iff rank(W) < 2.

    W convention: W[mu,c] = <E,mu|V|d_c>; outgoing amplitude is W @ d.
    """
    W = _complex_array(W, ndim=2)
    if W.shape[1] != 2:
        raise ModelInputError(f"this X26 control expects exactly two internal modes; got {W.shape[1]}")
    rank = numerical_rank(W, rtol=rtol)
    s = np.linalg.svd(W, compute_uv=False)
    if rank >= 2:
        return None, rank, s
    _, _, vh = np.linalg.svd(W, full_matrices=True)
    d = vh[-1, :].conj()
    norm = np.linalg.norm(d)
    if norm == 0:
        raise ModelInputError("failed to construct nonzero null vector")
    d = d / norm
    # Fix an irrelevant global phase for reproducible reports.
    nz = np.flatnonzero(np.abs(d) > 1e-14)
    if nz.size and abs(d[nz[0]]) > 0:
        d *= np.exp(-1j * np.angle(d[nz[0]]))
    return d, rank, s


@dataclass(frozen=True)
class Continuum:
    emin: float = -1.0
    emax: float = 1.0
    channel_names: tuple[str, ...] = ("shared_open_channel",)

    def __post_init__(self) -> None:
        if not (math.isfinite(self.emin) and math.isfinite(self.emax) and self.emin < self.emax):
            raise ModelInputError("continuum requires finite emin < emax")
        if not self.channel_names:
            raise ModelInputError("at least one open continuum channel is required")

    def contains(self, energy: float, atol: float = 1e-12) -> bool:
        return self.emin + atol < energy < self.emax - atol

    def log_pv_factor(self, energy: float) -> float:
        """PV integral factor for a flat band: int dE'/(E-E')."""
        if not self.contains(energy):
            raise ModelInputError("flat-band PV formula here is defined for an interior energy")
        return math.log((energy - self.emin) / (self.emax - energy))


@dataclass(frozen=True)
class TwoModeModel:
    Hd: Array
    W0: Array
    continuum: Continuum
    label: str = "unnamed"
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        Hd = _complex_array(self.Hd, ndim=2)
        W0 = _complex_array(self.W0, ndim=2)
        if Hd.shape != (2, 2):
            raise ModelInputError(f"Hd must be 2x2, got {Hd.shape}")
        if W0.shape[1] != 2:
            raise ModelInputError(f"W0 must have two columns, got {W0.shape}")
        if W0.shape[0] != len(self.continuum.channel_names):
            raise ModelInputError("number of rows of W0 must match continuum channel_names")
        if not np.allclose(Hd, Hd.conj().T, atol=1e-12, rtol=1e-12):
            raise ModelInputError("Hd must be Hermitian")

    @property
    def J(self) -> Array:
        return self.W0.conj().T @ self.W0

    @property
    def Gamma(self) -> Array:
        return 2.0 * math.pi * self.J

    def W(self, energy: float) -> Array:
        # X26-A uses an energy-independent direction in mode space.
        # An energy-dependent physical form factor is a future extension/stub.
        if not self.continuum.contains(energy):
            return np.zeros_like(self.W0)
        return self.W0.copy()

    def delta(self, energy: float) -> Array:
        return self.J * self.continuum.log_pv_factor(energy)

    def self_energy(self, energy: float) -> Array:
        return self.delta(energy) - 0.5j * self.Gamma

    def effective_hamiltonian(self, energy: float) -> Array:
        return self.Hd + self.self_energy(energy)

    def narrowest_effective_width(self, energy: float) -> float:
        eigvals = np.linalg.eigvals(self.effective_hamiltonian(energy))
        widths = -2.0 * np.imag(eigvals)
        # Remove tiny negative roundoff only; a materially negative width is an error.
        if np.min(widths) < -1e-8:
            raise ModelInputError(f"effective model produced a negative width: {widths}")
        widths = np.maximum(widths, 0.0)
        return float(np.min(widths))


def tuned_friedrich_wintgen_model(
    *,
    w: Iterable[complex] = (0.22, 0.31 * np.exp(0.35j)),
    E_dark: float = 0.10,
    E_bright: float = 0.42,
    continuum: Continuum | None = None,
    label: str = "FW_two_modes_one_common_continuum",
) -> TwoModeModel:
    """Construct a deliberately tuned rank-one two-mode BIC control.

    This explicitly chooses Hd so that the null vector of W is an eigenvector.
    That is useful as X26-A algebra verification, but it is NOT evidence that ADD
    generates such a Hamiltonian or coupling matrix.
    """
    continuum = continuum or Continuum()
    if not continuum.contains(E_dark):
        raise ModelInputError("E_dark must lie strictly inside the continuum band")
    w_arr = _complex_array(list(w), ndim=1)
    if w_arr.shape != (2,) or np.linalg.norm(w_arr) == 0:
        raise ModelInputError("w must contain two complex nonzero-or-zero amplitudes, not both zero")
    W0 = w_arr.reshape(1, 2)
    d, rank, _ = null_vector_for_two_modes(W0)
    if d is None or rank != 1:
        raise ModelInputError("the control requires one nonzero common open channel (rank one)")
    bright = W0.conj().T[:, 0]
    bright = bright / np.linalg.norm(bright)
    # d and bright are orthonormal by construction under the declared W convention.
    if not np.allclose(np.vdot(bright, d), 0.0, atol=1e-12):
        raise ModelInputError("internal dark/bright basis construction failed")
    Hd = E_dark * np.outer(d, d.conj()) + E_bright * np.outer(bright, bright.conj())
    return TwoModeModel(
        Hd=Hd,
        W0=W0,
        continuum=continuum,
        label=label,
        metadata={
            "construction": "Hd aligned to ker(W); controlled toy, not derived from ADD",
            "E_dark": float(E_dark),
            "E_bright": float(E_bright),
        },
    )


def independent_continua_control(
    *,
    g1: float = 0.22,
    g2: float = 0.31,
    E1: float = 0.10,
    E2: float = 0.42,
    continuum: Continuum | None = None,
) -> TwoModeModel:
    continuum = continuum or Continuum(channel_names=("continuum_for_mode_1", "continuum_for_mode_2"))
    Hd = np.diag([E1, E2]).astype(np.complex128)
    W0 = np.diag([g1, g2]).astype(np.complex128)
    return TwoModeModel(Hd=Hd, W0=W0, continuum=continuum, label="independent_continua_rank_two")


def evaluate_bic(model: TwoModeModel, energy: float, *, tol: float = 1e-9) -> dict[str, Any]:
    d, rank, singular_values = null_vector_for_two_modes(model.W(energy))
    column_norms = np.linalg.norm(model.W(energy), axis=0)
    both_internal_modes_couple = bool(np.all(column_norms > tol))
    result: dict[str, Any] = {
        "model": model.label,
        "energy": float(energy),
        "inside_continuum": model.continuum.contains(energy),
        "rank_W": rank,
        "internal_column_coupling_norms": [float(x) for x in column_norms],
        "both_internal_modes_couple_to_at_least_one_open_channel": both_internal_modes_couple,
        "singular_values_W": [float(x) for x in singular_values],
        "has_nontrivial_dark_kernel": d is not None,
        "dark_vector": None if d is None else _json_complex_vector(d),
        "dark_amplitude_norm": None if d is None else float(np.linalg.norm(model.W(energy) @ d)),
        "dark_eigen_residual": None,
        "dark_width": None,
        "continuum_norm_finite": False,
        "BIC_candidate": False,
        "failure_reasons": [],
    }
    if not result["inside_continuum"]:
        result["failure_reasons"].append("energy_not_inside_continuum")
    if d is None:
        result["failure_reasons"].append("rank_W_is_two_no_dark_kernel")
        return result

    # The flat-band model has W(E') = W0 throughout the band; therefore W(E')d=0
    # for all E' and the continuum wavefunction vanishes identically (normalizable).
    # This statement would need re-evaluation for a non-factorized energy-dependent W.
    residual = (model.Hd + model.delta(energy)) @ d - energy * d
    dark_width_raw = float(np.real(np.vdot(d, model.Gamma @ d)))
    if dark_width_raw < -tol:
        raise ModelInputError(f"positive-semidefinite width matrix produced negative width {dark_width_raw}")
    dark_width = max(0.0, dark_width_raw)
    result["dark_eigen_residual"] = float(np.linalg.norm(residual))
    result["dark_width"] = dark_width
    result["continuum_norm_finite"] = bool(np.linalg.norm(model.W0 @ d) <= tol)
    result["BIC_candidate"] = bool(
        result["inside_continuum"]
        and rank == 1
        and both_internal_modes_couple
        and result["dark_amplitude_norm"] <= tol
        and result["dark_eigen_residual"] <= tol
        and dark_width <= tol
        and result["continuum_norm_finite"]
    )
    if rank != 1:
        result["failure_reasons"].append("not_a_rank_one_two_path_interference_case")
    if not both_internal_modes_couple:
        result["failure_reasons"].append("one_or_both_internal_modes_uncoupled_from_all_open_channels")
    if result["dark_amplitude_norm"] > tol:
        result["failure_reasons"].append("nonzero_on_shell_decay_amplitude")
    if result["dark_eigen_residual"] > tol:
        result["failure_reasons"].append("dark_kernel_vector_not_internal_eigenstate")
    if dark_width > tol:
        result["failure_reasons"].append("nonzero_width")
    if not result["continuum_norm_finite"]:
        result["failure_reasons"].append("continuum_component_not_shown_normalizable")
    return result


def _json_complex_vector(v: Array) -> list[dict[str, float]]:
    return [{"re": float(z.real), "im": float(z.imag)} for z in np.asarray(v).ravel()]


def _fit_log_slope(eps: Array, widths: Array) -> float | None:
    mask = (eps > 0) & (widths > 1e-18) & np.isfinite(widths)
    if np.sum(mask) < 3:
        return None
    x = np.log(eps[mask])
    y = np.log(widths[mask])
    slope, _ = np.polyfit(x, y, 1)
    return float(slope)


def perturbation_diagnostics(model: TwoModeModel, E_ref: float, eps_values: Iterable[float]) -> dict[str, Any]:
    """Compare rank-preserving and BIC-lifting perturbation families.

    The report deliberately does NOT label epsilon^2 as proof of protection.
    The toy has no declared physical symmetry representation.
    """
    eps = np.asarray(list(eps_values), dtype=float)
    if eps.ndim != 1 or eps.size < 3 or np.any(eps <= 0):
        raise ModelInputError("eps_values must contain at least three positive values")
    rows: dict[str, list[float]] = {"rank_preserving_common_rescale": [], "internal_detuning": [], "which_path_extra_channel": []}
    ranks: dict[str, list[int]] = {k: [] for k in rows}

    # 1) W is scaled but its one-dimensional row space is preserved;
    #    Hd is unchanged, so the same dark eigenvector remains exactly dark.
    for e in eps:
        m = TwoModeModel(Hd=model.Hd, W0=model.W0 * (1.0 + e), continuum=model.continuum, label="rank_preserving")
        rows["rank_preserving_common_rescale"].append(m.narrowest_effective_width(E_ref))
        ranks["rank_preserving_common_rescale"].append(numerical_rank(m.W0))

    # 2) A differential internal energy shift breaks alignment of ker(W) with an eigenvector.
    detune = np.diag([1.0, -1.0]).astype(np.complex128)
    for e in eps:
        m = TwoModeModel(Hd=model.Hd + e * detune, W0=model.W0, continuum=model.continuum, label="internal_detuning")
        rows["internal_detuning"].append(m.narrowest_effective_width(E_ref))
        ranks["internal_detuning"].append(numerical_rank(m.W0))

    # 3) Add a distinguishable second continuum channel. For any nonzero epsilon,
    #    this generically makes W full rank and reveals which-path information.
    extra_row = np.array([[1.0, -0.73]], dtype=np.complex128)
    for e in eps:
        Wnew = np.vstack([model.W0, e * extra_row])
        names = tuple(model.continuum.channel_names) + ("which_path_marker",)
        cont = Continuum(model.continuum.emin, model.continuum.emax, names)
        m = TwoModeModel(Hd=model.Hd, W0=Wnew, continuum=cont, label="which_path_lifting")
        rows["which_path_extra_channel"].append(m.narrowest_effective_width(E_ref))
        ranks["which_path_extra_channel"].append(numerical_rank(m.W0))

    result = {}
    for key, vals in rows.items():
        width_arr = np.asarray(vals)
        result[key] = {
            "epsilon": [float(x) for x in eps],
            "narrowest_effective_width": [float(x) for x in width_arr],
            "rank_W": ranks[key],
            "log_log_slope": _fit_log_slope(eps, width_arr),
        }
    return {
        "interpretation": "Perturbative scaling diagnostic only; no physical symmetry/protection has been specified.",
        "families": result,
        "protection_classification": "NOT_CLASSIFIED_NO_DECLARED_SYMMETRY",
    }


def fano_zero_without_bic_control(*, q: float = 0.7, resonance_energy: float = 0.15, width: float = 0.12) -> dict[str, Any]:
    """Canonical scalar Fano amplitude control: a scattering zero with finite width.

    f(epsilon) = (epsilon + q)/(epsilon + i); its zero is at epsilon=-q,
    while the resonance denominator retains finite imaginary part.
    """
    if width <= 0:
        raise ModelInputError("Fano control width must be positive")
    epsilon_zero = -float(q)
    energy_zero = float(resonance_energy + 0.5 * width * epsilon_zero)
    amplitude = (epsilon_zero + q) / (epsilon_zero + 1j)
    return {
        "control": "Fano_scattering_zero_not_BIC",
        "q": float(q),
        "resonance_energy": float(resonance_energy),
        "finite_resonance_width": float(width),
        "zero_energy": energy_zero,
        "amplitude_at_zero": {"re": float(np.real(amplitude)), "im": float(np.imag(amplitude))},
        "amplitude_is_zero": bool(abs(amplitude) < 1e-12),
        "BIC": False,
        "reason": "scattering numerator vanishes but resonance width remains finite; no embedded normalizable eigenstate is asserted",
    }


def single_active_internal_mode_control(*, coupling: float = 0.25, energy: float = 0.1) -> dict[str, Any]:
    """Mapping-specific control: only one resonance is assigned to one ADD channel.

    This does NOT prove that all one-ADD-channel systems lack BICs: two resonances
    may in principle belong to the same ADD channel. See same_channel_two_mode_control.
    """
    return {
        "control": "one_resonance_one_ADD_channel_mapping",
        "active_ADD_channel": 1,
        "K_sector_example": {"K1": 1, "K2": 0},
        "internal_resonance_count": 1,
        "coupling_amplitude": float(coupling),
        "resonance_energy": float(energy),
        "two_resonance_interference_available": False,
        "scope": "mapping-specific only; not a general theorem about BIC",
    }


def same_channel_two_mode_counterexample(
    *,
    E_dark: float = 0.1,
    E_bright: float = 0.42,
    continuum: Continuum | None = None,
) -> dict[str, Any]:
    """Counterexample to treating K1>0,K2>0 as universally necessary for BIC.

    Two resonances are assigned to the same ADD channel c=1, with K1>0,K2=0.
    The spectral toy still admits a shared-continuum dark state.
    """
    cont = continuum or Continuum()
    m = tuned_friedrich_wintgen_model(
        w=(0.22, 0.31), E_dark=E_dark, E_bright=E_bright,
        continuum=cont, label="two_modes_same_ADD_channel_K2_zero",
    )
    bic = evaluate_bic(m, E_dark)
    return {
        "control": "two_resonances_same_ADD_channel",
        "K_sector_metadata": {"K1": 1, "K2": 0},
        "both_modes_mapped_to_ADD_channel": 1,
        "BIC_control_result": bic,
        "interpretation": "A BIC can occur with K2=0 if two distinct resonances are supplied by the same ADD channel; K1>0,K2>0 is mapping-specific, not universal.",
    }


def compare_sector_labels(K_pair_1: tuple[int, int], K_pair_2: tuple[int, int]) -> dict[str, Any]:
    same = tuple(K_pair_1) == tuple(K_pair_2)
    return {
        "sector_1": [int(K_pair_1[0]), int(K_pair_1[1])],
        "sector_2": [int(K_pair_2[0]), int(K_pair_2[1])],
        "same_joint_K_sector": same,
        "coherent_superposition_under_isolated_K_conserving_dynamics": "COMPATIBLE_WITHIN_ONE_SECTOR" if same else "NOT_GENERATED_BY_ISOLATED_K_CONSERVING_DYNAMICS",
        "quantum_superselection": "NOT_ESTABLISHED; requires allowed-observable algebra / reference-frame specification",
    }


def run_x26_a() -> dict[str, Any]:
    continuum = Continuum(emin=-1.0, emax=1.0, channel_names=("shared_continuum",))
    model = tuned_friedrich_wintgen_model(continuum=continuum)
    E_dark = float(model.metadata["E_dark"])
    bic = evaluate_bic(model, E_dark)
    perturb = perturbation_diagnostics(model, E_dark, [1e-2, 5e-3, 2e-3, 1e-3, 5e-4, 2e-4])
    independent = independent_continua_control(continuum=Continuum(
        emin=-1.0, emax=1.0,
        channel_names=("which_path_c1", "which_path_c2"),
    ))
    independent_result = evaluate_bic(independent, E_dark)
    return {
        "run_id": "X26_A_Friedrich_Wintgen_control",
        "scope": "analytic/numerical two-mode toy control; not ADD-derived",
        "units": "hbar=1; continuum energy-normalized; W in sqrt(energy)",
        "model": {
            "label": model.label,
            "Hd": _json_complex_matrix(model.Hd),
            "W0": _json_complex_matrix(model.W0),
            "continuum_band": [continuum.emin, continuum.emax],
            "continuum_channels": list(continuum.channel_names),
            "Gamma": _json_complex_matrix(model.Gamma),
            "delta_at_E_dark": _json_complex_matrix(model.delta(E_dark)),
        },
        "T1_rank_and_dark_kernel": {
            "status": "PASS_ALGEBRAIC_SANITY_CHECK" if bic["has_nontrivial_dark_kernel"] else "FAIL",
            "note": "For a 1x2 W, rank<2 is guaranteed by dimensionality; this is not evidence that ADD generates a common continuum.",
            "details": bic,
        },
        "T2_internal_eigenstate_alignment": {
            "status": "PASS_TOY_MODEL" if bic["dark_eigen_residual"] is not None and bic["dark_eigen_residual"] < 1e-9 else "FAIL",
            "details": {"dark_eigen_residual": bic["dark_eigen_residual"], "dark_width": bic["dark_width"]},
        },
        "T3_embedded_normalizable_state": {
            "status": "PASS_TOY_MODEL" if bic["BIC_candidate"] else "FAIL",
            "details": bic,
            "scope_note": "For this flat-band factorized toy, W(E')d=0 throughout the band, so the continuum component vanishes and the state is normalizable. General energy-dependent ADD-derived form factors are not covered.",
        },
        "T4_perturbation_diagnostics": perturb,
        "T5_loading": {
            "status": "PARTIAL_STATIC_NO_LOADING",
            "result": "An exact dark state in ker(W) is decoupled from the same stationary continuum; an incoming continuum state cannot populate it under this time-independent Hamiltonian.",
            "preparation": "INITIAL_PREPARATION_ONLY unless a time-dependent loading protocol is separately provided",
            "time_dependent_loading_protocol": "NOT_IMPLEMENTED",
        },
        "N1_independent_continua": {
            "status": "PASS_NEGATIVE_CONTROL" if independent_result["rank_W"] == 2 and not independent_result["BIC_candidate"] else "FAIL_CONTROL",
            "details": independent_result,
        },
        "N2_single_channel_mapping": {
            "status": "MAPPING_SPECIFIC_CONTROL_ONLY",
            "one_resonance_case": single_active_internal_mode_control(),
            "counterexample_two_modes_same_channel": same_channel_two_mode_counterexample(),
        },
        "N3_fano_zero_without_BIC": {
            "status": "PASS_NEGATIVE_CONTROL",
            "details": fano_zero_without_bic_control(),
        },
        "N4_different_K_sectors": compare_sector_labels((1, 0), (0, 1)),
        "N5_old_ADD_transport": {
            "status": "BLOCKED_NOT_RUN",
            "reason": "The exact carrier.py source and its transport implementation are not part of this package; only a blob hash was supplied in the research note.",
        },
        "ADD_derived_claims": "NONE",
        "overall": "X26_A_CONTROL_MODEL_EXECUTED; ADD_FANO_BIC_BRIDGE_NOT_ESTABLISHED",
    }


def _json_complex_matrix(a: Array) -> list[list[dict[str, float]]]:
    return [[{"re": float(z.real), "im": float(z.imag)} for z in row] for row in np.asarray(a)]


def main() -> int:
    result = run_x26_a()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
