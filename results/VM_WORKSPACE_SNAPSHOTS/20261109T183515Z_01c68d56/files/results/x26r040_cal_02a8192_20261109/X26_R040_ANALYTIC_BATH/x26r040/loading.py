"""Separate loading interface; explicit control Hamiltonian is an imported model input."""
from __future__ import annotations
import numpy as np
from scipy.integrate import solve_ivp
from .model import validate_hermitian


def simulate_controlled_loading(H0: np.ndarray, H_control: np.ndarray,
                                initial_state: np.ndarray, target_projector: np.ndarray,
                                times: np.ndarray, envelope, envelope_derivative,
                                hbar: float = 1.0, rtol: float = 1e-9,
                                atol: float = 1e-11) -> dict:
    """Integrate i hbar dpsi/dt=(H0+u(t)H_control)psi and external work.

    Work is W_ext=int <psi|dH/dt|psi>dt. It is not a complete actuator cost:
    controller reset, reservoir entropy, and return cycle require separate data.
    """
    h0 = np.asarray(H0, dtype=complex)
    hc = np.asarray(H_control, dtype=complex)
    psi0 = np.asarray(initial_state, dtype=complex)
    projector = np.asarray(target_projector, dtype=complex)
    if h0.ndim != 2 or h0.shape[0] != h0.shape[1]:
        raise ValueError("H0 must be square")
    n = h0.shape[0]
    if hc.shape != (n,n) or projector.shape != (n,n) or psi0.shape != (n,):
        raise ValueError("loading dimensions do not match")
    validate_hermitian(h0)
    validate_hermitian(hc)
    validate_hermitian(projector)
    if not np.isclose(np.linalg.norm(psi0), 1.0, atol=1e-9):
        raise ValueError("initial state must be normalized")
    if not np.isfinite(hbar) or hbar <= 0:
        raise ValueError("hbar must be finite and positive")
    if np.linalg.norm(projector @ projector - projector, ord="fro") > 1e-9:
        raise ValueError("target_operator must be an orthogonal projector")
    ts = np.asarray(times, dtype=float)
    if ts.ndim != 1 or len(ts) < 2 or np.any(np.diff(ts) <= 0):
        raise ValueError("times must be a strictly increasing vector")

    def rhs(t, y):
        psi = y[:n] + 1j*y[n:2*n]
        work = y[-1]
        u = float(envelope(t))
        du = float(envelope_derivative(t))
        h = h0 + u*hc
        dpsi = -1j * (h @ psi) / hbar
        power = du * float(np.real(np.vdot(psi, hc @ psi)))
        return np.concatenate([dpsi.real, dpsi.imag, [power]])

    y0 = np.concatenate([psi0.real, psi0.imag, [0.0]])
    result = solve_ivp(rhs, (float(ts[0]), float(ts[-1])), y0, t_eval=ts,
                       rtol=rtol, atol=atol, method="DOP853")
    if not result.success:
        raise RuntimeError(f"loading ODE failed: {result.message}")
    states = result.y[:n] + 1j*result.y[n:2*n]
    populations = [float(np.real(np.vdot(psi, projector @ psi))) for psi in states.T]
    norms = [float(np.linalg.norm(psi)) for psi in states.T]
    return {
        "status": "DRIVEN_LOADING_SIMULATED_CONDITIONAL_MODEL",
        "times": ts.tolist(),
        "target_population": populations,
        "state_norm": norms,
        "external_work_model_units": float(result.y[-1, -1]),
        "actuator_total_cost": None,
        "actuator_cost_status": "NOT_EVALUABLE_NO_ACTUATOR_AND_RESET_MODEL",
        "reservoir_entropy_cost": None,
        "reservoir_cost_status": "NOT_EVALUABLE_NO_RESERVOIR_MODEL",
        "interpretation": "conditional controlled dynamics; not derived from ADD",
    }
