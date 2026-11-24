"""Comoving entropies and X/visible equality on the actually retained P7 trajectory."""
import math
import numpy as np
from scipy.special import kve, xlogy


def kinetic_entropy(species):
    """Integral over piecewise-constant comoving cells, including spin degeneracy."""
    f = np.asarray(species["occupation"], float)
    stat = species["statistics"]
    if np.any(f < 0) or (stat in ("fermion","FD") and np.any(f > 1)):
        return None
    integrand = -xlogy(f, f)
    if stat in ("fermion","FD"):
        integrand -= xlogy(1-f, 1-f)
    elif stat in ("boson","BE"):
        integrand += (1+f)*np.log1p(f)
    else:
        integrand += f
    return float(species["degeneracy"]/(6*math.pi**2)
                 * np.diff(np.asarray(species["q_edges_MeV"])**3) @ integrand)


def entropies(row, model):
    a3 = row["scale_factor"]**3
    hidden = a3*row["bulk_entropy_MeV3"]
    visible = 0.
    for i, name in [(1,"gamma"),(2,"nu")]:
        if name in model.kinetic.sectors:
            continue
        if row["rho"][i] > 0:
            visible += a3*(row["rho"][i]+row["pressure"][i])/row["T_"+name+"_MeV"]
    for species in row["kinetic_species"]:
        if species["sector"] not in ("nu","relic"):
            continue
        s = kinetic_entropy(species)
        if species["sector"] == "nu":
            visible = None if s is None or visible is None else visible+s
        else:
            hidden = None if s is None or hidden is None else hidden+s
    n, t = row["relic_n_MeV3"], row["relic_T_MeV"]
    if model.relic and n > 0:
        if model.dust or t <= 0:
            hidden = None
        else:
            m = model.mass
            z = m/t
            excitation = 1.5+15/(8*z) if z>1e6 else (row["rho"][4]/n-m)/t
            scaled_k = math.sqrt(math.pi/(2*z))*(1+15/(8*z)) if z>1e6 else kve(2,z)
            s = n*(1+excitation+math.log(model.degeneracy*m*m*t*scaled_k/(2*math.pi**2*n)))
            hidden = None if s < 0 or hidden is None else hidden+a3*s
    return {"S_X":hidden, "S_vis":visible, "R":hidden/visible if hidden is not None and visible else None}


def domination(time, scale, temperature, density):
    from .history import first_event
    rho = np.asarray(density)
    delta = rho[:,0]+rho[:,4]-rho[:,1]-rho[:,2]
    result = first_event(time, delta, 0.)
    if not result["censored"]:
        result.update(a=float(np.interp(result["time_s"],time,scale)),
                      T_gamma_MeV=float(np.interp(result["time_s"],time,temperature)))
    return {**result,"definition":"rho_bulk_X + rho_relic crosses rho_gamma + rho_nu; free radiation excluded"}
