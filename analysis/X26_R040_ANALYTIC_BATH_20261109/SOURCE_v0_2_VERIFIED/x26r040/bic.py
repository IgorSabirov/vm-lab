"""Direct embedded-eigenvalue checks, separate from resonance poles."""
from __future__ import annotations
import numpy as np
from .model import R040Parameters


def check_direct_bic(p: R040Parameters, tol: float = 1e-10) -> dict:
    d = p.dark_vector
    energy = p.dark_energy
    bath = p.bath()
    in_band = bath.lower_edge < energy < bath.upper_edge
    port_amplitude = p.g * d[2]
    eigen_residual = float(np.linalg.norm(p.H3 @ d - energy * d))
    normalized = abs(np.linalg.norm(d) - 1.0) <= tol
    decoupled = abs(port_amplitude) <= tol
    normalizable_continuum_component = decoupled  # exactly zero for this port geometry
    passed_eigen = eigen_residual <= tol
    passed = bool(in_band and normalized and decoupled and passed_eigen
                  and normalizable_continuum_component)
    from .symmetry import check_z2_exchange
    symmetry = check_z2_exchange(p, tol=tol)
    if passed:
        verdict = "BIC_IN_CONDITIONAL_R040_TIGHT_BINDING_MODEL"
    elif not in_band:
        verdict = "DARK_BOUND_STATE_OUTSIDE_CONTINUUM_NOT_BIC"
    elif not passed_eigen:
        verdict = "DARK_VECTOR_NOT_EIGENSTATE"
    elif not decoupled:
        verdict = "OPEN_CHANNEL_COUPLING_NONZERO_NOT_BIC"
    else:
        verdict = "NOT_BIC"
    return {
        "verdict": verdict,
        "energy": float(energy),
        "continuum_interval": [float(bath.lower_edge), float(bath.upper_edge)],
        "energy_inside_continuum": bool(in_band),
        "normalized_internal_vector": bool(normalized),
        "port_amplitude_norm": float(abs(port_amplitude)),
        "eigen_equation_residual": eigen_residual,
        "continuum_component_norm": 0.0 if decoupled else float("inf"),
        "normalizable_continuum_component": bool(normalizable_continuum_component),
        "all_open_channels_checked": True,
        "mechanism_class": ("Z2_SYMMETRY_PROTECTED_BIC" if passed and symmetry["status"]=="EXACT_Z2_EXCHANGE_SYMMETRY"
                            else "PARAMETRICALLY_TUNED_BIC" if passed else "NO_BIC_MECHANISM_ASSIGNED"),
        "z2_symmetry": symmetry,
        "model_scope": "conditional R040: bath contacts only trimer node 2",
    }


def static_loading_invariant(p: R040Parameters, initial_state: np.ndarray,
                             times: np.ndarray | list[float], n_bath_sites: int = 32,
                             tol: float = 1e-9) -> dict:
    """Verify constant dark-sector weight in the full finite-ring Hamiltonian.

    The finite bath is a closed Hermitian ring, not an irreversible continuum.
    The exact dark state has zero amplitude on the only contacted trimer node,
    so its projector commutes with this full Hamiltonian for every ring size.
    """
    from scipy.linalg import expm
    if type(n_bath_sites) is not int or n_bath_sites < 3:
        raise ValueError("n_bath_sites must be an integer >= 3")
    bath=p.bath()
    dim=3+n_bath_sites
    hfull=np.zeros((dim,dim),dtype=complex)
    hfull[:3,:3]=p.H3
    hb=np.zeros((n_bath_sites,n_bath_sites),dtype=complex)
    for i in range(n_bath_sites):
        j=(i+1)%n_bath_sites
        hb[i,i]+=p.bath_onsite
        hb[i,j]+=p.kappa
        hb[j,i]+=p.kappa
    hfull[3:,3:]=hb
    hfull[2,3]=p.g
    hfull[3,2]=p.g
    d=np.zeros(dim,dtype=complex)
    d[:3]=p.dark_vector
    projector=np.outer(d,d.conj())
    psi=np.asarray(initial_state,dtype=complex)
    if psi.shape==(3,):
        psi=np.concatenate([psi,np.zeros(n_bath_sites,dtype=complex)])
    if psi.shape!=(dim,) or not np.isclose(np.linalg.norm(psi),1.0,atol=tol):
        raise ValueError("initial_state must be normalized and have length 3 or 3+n_bath_sites")
    comm=float(np.linalg.norm(hfull@projector-projector@hfull,ord="fro"))
    pd0=float(np.real(np.vdot(psi,projector@psi)))
    values=[]
    for t in times:
        evolved=expm(-1j*hfull*float(t))@psi
        values.append(float(np.real(np.vdot(evolved,projector@evolved))))
    drift=max((abs(v-pd0) for v in values),default=0.0)
    return {
        "initial_dark_population":pd0,
        "dark_population_by_time":values,
        "max_absolute_drift":float(drift),
        "projector_commutator_norm":comm,
        "bath_ring_sites":n_bath_sites,
        "finite_bath_is_closed":True,
        "static_no_loading_pass":bool(drift<=tol and comm<=tol),
        "scope":"full finite Hermitian ring; exact static no-loading control, not continuum decay dynamics",
    }
