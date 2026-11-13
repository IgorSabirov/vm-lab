"""Conditional thermal/Davies loading channel for a pre-existing R040 BIC.

This is an additional, explicitly imported loading reservoir, separate from
(the scattering) tight-binding bath.  The local ADD event only modulates the
rate through a stated Psi postulate; it is not itself a microscopic reservoir.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.integrate import solve_ivp

from .bic import check_direct_bic
from .model import R040Parameters
from .transfer import projector_from_dark_vector


def _von_neumann_entropy(rho: np.ndarray, tol: float = 1e-14) -> float:
    vals = np.linalg.eigvalsh((rho + rho.conj().T) / 2.0).real
    vals = np.clip(vals, 0.0, 1.0)
    vals = vals[vals > tol]
    return float(-np.sum(vals * np.log(vals)))


def bright_bohr_transition(p: R040Parameters, tol: float = 1e-9) -> dict:
    """Select the highest-energy eigenstate orthogonal to the exact dark BIC."""
    bic = check_direct_bic(p, tol=tol)
    if bic["verdict"] != "BIC_IN_CONDITIONAL_R040_TIGHT_BINDING_MODEL":
        raise ValueError("thermal loading target requires a direct BIC in the declared R040 model")
    values, vectors = np.linalg.eigh(p.H3)
    d = p.dark_vector
    overlaps = np.abs(vectors.conj().T @ d)
    candidates = [i for i in range(3) if overlaps[i] <= tol]
    if not candidates:
        raise ValueError("no orthogonal bright eigenstate found; degeneracy or tolerance issue")
    ed = float(p.dark_energy)
    above = [i for i in candidates if float(values[i]) > ed + tol]
    if not above:
        raise ValueError("no bright eigenstate above the dark energy; this downward thermal protocol is undefined")
    idx = max(above, key=lambda i: float(values[i]))
    b = vectors[:, idx]
    if abs(np.vdot(d, b)) > tol:
        raise ArithmeticError("selected bright state is not orthogonal to the dark state")
    return {
        "dark_energy": ed,
        "bright_energy": float(values[idx]),
        "bohr_gap": float(values[idx] - ed),
        "dark_vector": d,
        "bright_vector": b,
        "bright_eigenvalue_index": int(idx),
        "bright_eigen_equation_residual": float(np.linalg.norm(p.H3 @ b - values[idx] * b)),
        "all_other_eigenvalues": [float(x) for x in values],
    }


def simulate_davies_loading(p: R040Parameters, initial_state: np.ndarray,
                            times: np.ndarray | list[float], beta: float,
                            gamma_down_base: float, local_event_activity: float,
                            gate_envelope, bath_id: str,
                            rtol: float = 1e-9, atol: float = 1e-11,
                            initial_dark_tolerance: float = 1e-10) -> dict:
    """Integrate B -> D thermal loading with detailed-balance reverse jumps.

    L_down(t)=sqrt(gamma_down(t))*|D><B|,
    L_up(t)=sqrt(gamma_down(t)*exp(-beta*DeltaE))*|B><D|.
    The time gate must close at the final time.  beta is in inverse model-energy
    units (k_B=1), and the reported bath entropy flow is beta*Q_bath in k_B units.
    """
    if not isinstance(bath_id, str) or not bath_id.strip():
        raise ValueError("a named loading reservoir is required")
    if not math.isfinite(beta) or beta <= 0:
        raise ValueError("beta must be finite and positive")
    if not math.isfinite(gamma_down_base) or gamma_down_base <= 0:
        raise ValueError("gamma_down_base must be finite and positive")
    if not math.isfinite(local_event_activity) or not (0.0 < local_event_activity <= 1.0):
        raise ValueError("local_event_activity must lie in (0,1]")
    ts = np.asarray(times, dtype=float)
    if ts.ndim != 1 or len(ts) < 3 or np.any(~np.isfinite(ts)) or np.any(np.diff(ts) <= 0):
        raise ValueError("times must be a finite strictly increasing vector with >=3 points")

    trans = bright_bohr_transition(p)
    d = np.asarray(trans["dark_vector"], dtype=complex)
    b = np.asarray(trans["bright_vector"], dtype=complex)
    pd = projector_from_dark_vector(d)
    pb = projector_from_dark_vector(b)
    psi_or_rho = np.asarray(initial_state, dtype=complex)
    if psi_or_rho.shape == (3,):
        if not np.isclose(np.linalg.norm(psi_or_rho), 1.0, atol=1e-9):
            raise ValueError("initial pure state must be normalized")
        rho0 = np.outer(psi_or_rho, psi_or_rho.conj())
    elif psi_or_rho.shape == (3, 3):
        rho0 = (psi_or_rho + psi_or_rho.conj().T) / 2.0
        if abs(np.trace(rho0).real - 1.0) > 1e-9:
            raise ValueError("initial density matrix must have unit trace")
        if np.linalg.eigvalsh(rho0).min() < -1e-9:
            raise ValueError("initial density matrix must be positive semidefinite")
    else:
        raise ValueError("initial_state must be a length-3 ket or 3x3 density matrix")
    p_d0 = float(np.trace(pd @ rho0).real)
    if p_d0 > initial_dark_tolerance:
        raise ValueError("loading test requires an initially orthogonal (zero-dark-weight) packet")

    gap = float(trans["bohr_gap"])
    gamma0 = float(gamma_down_base * local_event_activity)
    gamma_up0 = float(gamma0 * math.exp(-beta * gap))
    ldown0 = math.sqrt(gamma0) * np.outer(d, b.conj())
    lup0 = math.sqrt(gamma_up0) * np.outer(b, d.conj())

    def dissipator(lop: np.ndarray, rho: np.ndarray) -> np.ndarray:
        ld_l = lop.conj().T @ lop
        return lop @ rho @ lop.conj().T - 0.5 * (ld_l @ rho + rho @ ld_l)

    def rhs(t, y):
        rho = y[:9].reshape(3, 3)
        gate = float(gate_envelope(float(t)))
        if not math.isfinite(gate) or gate < -1e-12 or gate > 1.0 + 1e-12:
            raise ValueError("loading gate envelope must remain within [0,1]")
        gate = min(1.0, max(0.0, gate))
        ld = math.sqrt(gate) * ldown0
        lu = math.sqrt(gate) * lup0
        drho = -1j * (p.H3 @ rho - rho @ p.H3)
        drho += dissipator(ld, rho) + dissipator(lu, rho)
        p_b = float(np.trace(pb @ rho).real)
        p_dark = float(np.trace(pd @ rho).real)
        qdot = gap * gate * (gamma0 * p_b - gamma_up0 * p_dark)
        return np.concatenate([drho.reshape(-1), np.array([qdot], dtype=complex)])

    y0 = np.concatenate([rho0.reshape(-1), np.array([0.0 + 0.0j])])
    sol = solve_ivp(rhs, (float(ts[0]), float(ts[-1])), y0, t_eval=ts,
                    rtol=rtol, atol=atol, method="DOP853")
    if not sol.success:
        raise RuntimeError(f"Davies loading integration failed: {sol.message}")
    states = [sol.y[:9, i].reshape(3, 3) for i in range(sol.y.shape[1])]
    p_dark = [float(np.trace(pd @ rho).real) for rho in states]
    p_bright = [float(np.trace(pb @ rho).real) for rho in states]
    traces = [complex(np.trace(rho)) for rho in states]
    min_eigs = [float(np.linalg.eigvalsh((rho + rho.conj().T) / 2).min()) for rho in states]
    entropies = [_von_neumann_entropy(rho) for rho in states]
    system_energies = [float(np.trace(p.H3 @ rho).real) for rho in states]
    q_bath = float(sol.y[-1, -1].real)
    gate_final = float(gate_envelope(float(ts[-1])))
    final_projector_comm = float(np.linalg.norm(p.H3 @ pd - pd @ p.H3, ord="fro"))
    return {
        "status": "DAVIES_THERMAL_LOADING_SIMULATED_CONDITIONAL_MODEL",
        "loading_reservoir_id": bath_id,
        "reservoir_is_separate_from_scattering_bath": True,
        "times": ts.tolist(),
        "target_population": p_dark,
        "bright_population": p_bright,
        "density_matrix_trace": [{"real": float(x.real), "imag": float(x.imag)} for x in traces],
        "minimum_density_eigenvalue": min_eigs,
        "system_von_neumann_entropy_nats": entropies,
        "system_energy_model_units": system_energies,
        "initial_target_population": p_d0,
        "final_target_population": p_dark[-1],
        "bohr_transition": {k: (v.tolist() if isinstance(v, np.ndarray) else v)
                            for k, v in trans.items()},
        "beta_inverse_model_energy": float(beta),
        "gamma_down_effective": gamma0,
        "gamma_up_effective": gamma_up0,
        "detailed_balance_ratio": gamma_up0 / gamma0,
        "reservoir_heat_gained_model_units": q_bath,
        "reservoir_entropy_flow_kB_units": float(beta * q_bath),
        "gate_final_value": gate_final,
        "gate_closed_at_final_time": bool(abs(gate_final) <= 1e-9),
        "post_gate_dark_projector_commutator_norm": final_projector_comm,
        "actuator_gate_switching_work": None,
        "actuator_gate_switching_status": "NOT_EVALUABLE_NO_GATE_ACTUATOR_MODEL",
        "initial_bright_packet_preparation_cost": None,
        "initial_preparation_cost_status": "NOT_EVALUABLE_INPUT_PACKET_ORIGIN_NOT_MODELLED",
        "interpretation": "Conditional weak-coupling thermal/Davies reservoir assumption; not derived from ADD and not a free loader.",
    }
