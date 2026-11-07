"""Finite unitary wave memory with projective readout.

This is NOT a continuum BIC claim or the spin/hole/proton material candidate.
Environment modes remain inside rho; no Markov reset or repeated fresh bath.
Classical bit input is an orthogonal label. Its loading actuator is imported.
"""
from functools import lru_cache
import numpy as np


@lru_cache(maxsize=64)
def spectrum(modes, coupling, detuning):
    # Vacuum, then two labelled rails [bright, dark, finite environment modes].
    width = modes + 2
    h = np.zeros((1 + 2*width, 1 + 2*width), complex)
    for rail in (0, 1):
        b = 1 + rail*width
        d = b + 1
        h[b, d] = h[d, b] = detuning
        for k, energy in enumerate(np.linspace(-2, 2, modes)):
            e = b + 2 + k
            h[e, e] = energy
            h[b, e] = h[e, b] = coupling / np.sqrt(modes)
    values, vectors = np.linalg.eigh(h)
    return h, values, vectors


def pack(rho):
    return {"real": rho.real.tolist(), "imag": rho.imag.tolist()}


def unpack(data):
    return np.array(data["real"]) + 1j*np.array(data["imag"])


def write(bit, mode, proper_time, modes, coupling, detuning):
    if mode == "classical":
        return {"mode": mode, "bit": bit, "written": proper_time}
    h, _, _ = spectrum(modes, coupling, detuning)
    b = 1 + bit*(modes + 2)
    state = np.zeros(len(h), complex)
    state[b] = 1
    # Local unitary bright<->dark loading pulse. No static capture is asserted.
    if mode == "finite_dark":
        state[b], state[b+1] = 0, 1
    rho = np.outer(state, state.conj())
    return {"mode": mode, "rho": pack(rho), "written": proper_time,
            "modes": modes, "coupling": coupling, "detuning": detuning,
            "load_pulse": mode == "finite_dark",
            "energy_accounting": "memory_H_only; actuator and fuel not a closed Hamiltonian"}


def evolved(data, proper_time):
    h, values, vectors = spectrum(data["modes"], data["coupling"], data["detuning"])
    dt = proper_time - data["written"]
    if dt < -1e-10:
        raise ValueError("reading before writing")
    u = (vectors * np.exp(-1j * values * max(dt, 0))) @ vectors.conj().T
    rho = u @ unpack(data["rho"]) @ u.conj().T
    return h, rho


def read(data, proper_time, draw, survival=1.0, tolerance=1e-10):
    if data["mode"] == "classical":
        bit = data["bit"] if draw < survival else None
        return bit, dict(readable_probability=survival, backend="classical"), data
    h, rho = evolved(data, proper_time)
    trace_error = float(abs(np.trace(rho)-1))
    min_eigenvalue = float(np.linalg.eigvalsh(rho).min())
    if trace_error > tolerance or min_eigenvalue < -tolerance or not np.all(np.isfinite(rho)):
        raise ArithmeticError("invalid density matrix")
    width = data["modes"] + 2
    groups = [[1, 2], [1+width, 2+width]]
    groups.append([j for j in range(len(rho)) if j not in groups[0]+groups[1]])
    probabilities = [float(np.trace(rho[np.ix_(g, g)]).real) for g in groups]
    if min(probabilities) < -tolerance or abs(sum(probabilities)-1) > tolerance:
        raise ArithmeticError("invalid quantum instrument probabilities")
    probabilities = np.clip(probabilities, 0, 1)
    probabilities /= probabilities.sum()
    outcome = min(int(np.searchsorted(np.cumsum(probabilities), draw, side="right")), 2)
    g = groups[outcome]
    post = np.zeros_like(rho)
    post[np.ix_(g, g)] = rho[np.ix_(g, g)] / probabilities[outcome]
    quality = dict(readable_probability=float(probabilities[0]+probabilities[1]),
                   probabilities=probabilities.tolist(), trace_error=trace_error,
                   min_eigenvalue=min_eigenvalue,
                   energy_before_read=float(np.trace(h@rho).real),
                   energy_after_selected_read=float(np.trace(h@post).real),
                   backend="finite_unitary_projective")
    updated = dict(data, rho=pack(post), written=proper_time)
    return (outcome if outcome < 2 else None), quality, updated


def response(modes, coupling, detuning, tolerance=1e-10):
    """Finite atomic operator-valued spectral measure on the two bright inputs."""
    _, values, vectors = spectrum(modes, coupling, detuning)
    indices = [1, 1+modes+2]
    atoms = []
    for k, value in enumerate(values):
        row = vectors[indices, k]
        weight = np.outer(row, row.conj())
        if atoms and abs(value-atoms[-1]["energy"]) <= tolerance:
            atoms[-1]["matrix"] += weight
        else:
            atoms.append({"energy": float(value), "matrix": weight})
    return [{"energy": x["energy"], "weight": pack(x["matrix"])} for x in atoms]
