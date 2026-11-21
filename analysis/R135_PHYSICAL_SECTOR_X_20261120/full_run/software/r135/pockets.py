"""Old-phase geometry and a *specified* trapped-radiation pocket closure.

Geometry uses the same Poisson nucleation/growth process as the P7 Avrami
moments. It does not infer surface dynamics from a volume fraction. Analytic
projection: Lu, Kawana, Xie, arXiv:2202.03439, Eqs. (4),(12),(14),(15).
Trapped thermal evolution: Kawana, Lu, Xie, arXiv:2206.09923, Eqs. (2.15),
(3.2)-(3.10). The latter is a local, subhorizon, negligible-surface-energy
model; it is not automatically a model of SU(3) remnants.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.integrate import cumulative_trapezoid, solve_ivp
from scipy.ndimage import label

from .common import G_NEWTON_MEV_MINUS2, HBAR_MEV_S, HBARC_MEV_CM, InputError, OpenInput, finite, require_source

C_CM_S = HBARC_MEV_CM / HBAR_MEV_S
GEOMETRY_SOURCE = "https://arxiv.org/abs/2202.03439"
DYNAMICS_SOURCE = "https://arxiv.org/abs/2206.09923"


def _history(history):
    fields = ("time_s", "scale_factor", "nucleation_rate_cm3_s", "wall_speed")
    t, a, g, v = [np.asarray(history[k], float) for k in fields]
    if (t.ndim != 1 or len(t) < 3 or any(x.shape != t.shape for x in (a, g, v))
            or not all(np.isfinite(x).all() for x in (t, a, g, v))
            or np.any(np.diff(t) <= 0) or np.any(a <= 0) or np.any(g < 0)
            or np.any((v < 0) | (v >= 1))):
        raise InputError("invalid nucleation history, physical cm^-3 s^-1 rates or wall speed")
    if np.any(np.diff(a) < 0):
        raise InputError("pocket geometry requires a noncontracting background")
    return t, a, g, v


def avrami_geometry(history):
    """Quadrature independent of the P7 four-moment ODE, with variable v(t)."""
    t, a, g, v = _history(history)
    chi = cumulative_trapezoid(C_CM_S*v/a, t, initial=0)
    intensity = np.zeros(len(t))
    for j in range(1, len(t)):
        intensity[j] = 4*np.pi/3*np.trapezoid(g[:j+1]*a[:j+1]**3*(chi[j]-chi[:j+1])**3, t[:j+1])
    return {"I": intensity, "old_fraction": np.exp(-intensity), "comoving_wall_distance_cm": chi}


def projected_distribution(history, index, *, constant_speed_rtol=1e-8):
    """General expansion-history projection, explicitly constant wall velocity.

    The ordered four integrals in Eq.12 are A^4/4!, since their integrands
    are identical. The d t'/d R = a(t')/[v a(t)] Jacobian in Eq.15 is
    retained. No fit to the printed shorthand Eq.20 is made (it omits the
    extra 1/v that follows from Eq.15). The tail needs a future history.
    """
    t, a, g, v = _history(history)
    if not 0 <= index < len(t)-1 or v[0] <= 0:
        raise InputError("projection needs an interior time and positive wall speed")
    if np.max(np.abs(v/v[0]-1)) > constant_speed_rtol:
        raise OpenInput("analytic remnant projection assumes constant wall speed; use voxel geometry for v(t)")
    speed = C_CM_S*v[0]
    conformal = cumulative_trapezoid(1/a, t, initial=0)
    geometry = avrami_geometry(history)
    rate = np.zeros(len(t))
    for j in range(1, len(t)):
        integral = np.trapezoid(g[:j+1]*a[:j+1]**3*(conformal[j]-conformal[:j+1])**2, t[:j+1])/a[j]
        rate[j] = (4/3)*np.pi**4*speed**9*geometry["old_fraction"][j]*integral**4
    radius = speed*a[index]*(conformal[index:]-conformal[index])
    density = (1-geometry["old_fraction"][index:])*rate[index:]/speed*(a[index:]/a[index])**4
    number = float(np.trapezoid(density, radius))
    sphere_volume = float(np.trapezoid(4*np.pi/3*radius**3*density, radius))
    return {"source": GEOMETRY_SOURCE, "time_s": float(t[index]),
            "radius_cm": radius.tolist(), "dn_dR_cm4": density.tolist(),
            "projected_collapse_rate_cm3_s": rate.tolist(),
            "number_density_cm3": number,
            "mean_radius_cm": float(np.trapezoid(radius*density, radius)/number) if number else None,
            "old_fraction": float(geometry["old_fraction"][index]),
            "spherical_volume_integral": sphere_volume,
            "volume_shape_factor_required": float(geometry["old_fraction"][index]/sphere_volume) if sphere_volume else None,
            "tail_status": "FINITE_FUTURE_HISTORY_NOT_EXTRAPOLATED",
            "terminal_old_fraction": float(geometry["old_fraction"][-1]),
            "interpretation": "projected distance to walls, not a physical late-time spherical radius"}


def component_catalog(old_mask, cell_size_cm):
    """Connected old-phase components with periodic face connectivity.

    Volume is exact for this voxelization. Surface is the grid-face area,
    not an isotropic continuum estimator. Seam contact is reported and is
    NOT identified with winding/percolation of a component.
    """
    mask = np.asarray(old_mask, bool)
    if mask.ndim != 3 or len(set(mask.shape)) != 1 or mask.shape[0] < 2:
        raise InputError("old-phase mask must be a cubic three-dimensional grid")
    dx = finite(cell_size_cm, "physical cell size", positive=True)
    labels, n = label(mask)
    parent = np.arange(n+1)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return int(x)

    seam = set()
    for axis in range(3):
        left, right = np.take(labels, 0, axis), np.take(labels, -1, axis)
        active = (left > 0) & (right > 0)
        pairs = np.unique(np.column_stack((left[active], right[active])), axis=0)
        for u, w in pairs:
            ru, rw = find(u), find(w)
            if ru != rw:
                parent[rw] = ru
            seam.update((int(u), int(w)))
    roots = np.array([find(i) for i in range(n+1)])
    labels = roots[labels]
    counts = np.bincount(labels.ravel(), minlength=n+1)
    faces = np.zeros(n+1, dtype=np.int64)
    for axis in range(3):
        for shift in (-1, 1):
            boundary = mask & ~np.roll(mask, shift, axis=axis)
            faces += np.bincount(labels[boundary], minlength=n+1)
    seam_roots = {find(i) for i in seam}
    components = []
    for i in np.flatnonzero(counts[1:])+1:
        volume = float(counts[i]*dx**3)
        components.append({"voxel_count": int(counts[i]), "volume_cm3": volume,
                           "equivalent_radius_cm": (3*volume/(4*np.pi))**(1/3),
                           "surface_grid_faces_cm2": float(faces[i]*dx**2),
                           "touches_periodic_seam": i in seam_roots})
    components.sort(key=lambda c: c["volume_cm3"], reverse=True)
    return {"old_fraction": float(mask.mean()), "components": components,
            "surface_grid_faces_cm2": float(faces.sum()*dx**2),
            "percolation_status": "NOT_INFERRED_FROM_SEAM_CONTACT"}


def sample_nucleations(history, box_comoving_cm, seed):
    """Poisson process on a periodic comoving volume; store all phantom events.

    For shared time-dependent wall speed, a bubble born inside converted
    space cannot outrun its parent. Keeping such events gives the same union
    and the standard Kolmogorov/Avrami survival probability.
    """
    t, a, g, _ = _history(history)
    length = finite(box_comoving_cm, "comoving box size", positive=True)
    rate = g*a**3*length**3
    cdf = cumulative_trapezoid(rate, t, initial=0)
    rng = np.random.default_rng(seed)
    count = int(rng.poisson(cdf[-1]))
    samples = np.sort(rng.uniform(0, cdf[-1], count))
    intervals = np.searchsorted(cdf, samples, side="right")-1
    intervals = np.minimum(intervals, len(t)-2)
    dt = np.diff(t)[intervals]
    base = rate[intervals]
    slope = np.diff(rate)[intervals]/dt
    mass = samples-cdf[intervals]
    # Stable inverse of base*x + slope*x^2/2 = mass.
    denom = base+np.sqrt(np.maximum(base**2+2*slope*mass, 0))
    offset = np.divide(2*mass, denom, out=np.zeros_like(mass), where=denom > 0)
    return {"birth_time_s": t[intervals]+offset,
            "centers_comoving_cm": rng.uniform(0, length, (count, 3)),
            "expected_events": float(cdf[-1]), "seed": int(seed)}


def voxel_geometry(history, *, box_comoving_cm, cells, seed, snapshot_indices):
    t, a, _, _ = _history(history)
    if type(cells) is not int or cells < 4:
        raise InputError("at least four integer grid cells per direction required")
    if not snapshot_indices or any(type(i) is not int or not 0 <= i < len(t) for i in snapshot_indices):
        raise InputError("explicit valid geometry snapshot indices required")
    length = finite(box_comoving_cm, "box size", positive=True)
    events = sample_nucleations(history, length, seed)
    analytic = avrami_geometry(history)
    chi = analytic["comoving_wall_distance_cm"]
    birth_chi = np.interp(events["birth_time_s"], t, chi)
    axis = (np.arange(cells)+.5)*length/cells
    result = []
    for j in snapshot_indices:
        old = np.ones((cells, cells, cells), dtype=bool)
        selected = np.flatnonzero(events["birth_time_s"] <= t[j])
        max_radius = 0.
        for k in selected:
            radius = float(chi[j]-birth_chi[k])
            max_radius = max(max_radius, radius)
            delta = [np.minimum(np.abs(axis-x), length-np.abs(axis-x))**2 for x in events["centers_comoving_cm"][k]]
            old &= (delta[0][:, None, None]+delta[1][None, :, None]+delta[2][None, None, :] > radius**2)
        catalog = component_catalog(old, a[j]*length/cells)
        catalog.update(time_s=float(t[j]), scale_factor=float(a[j]),
                       analytic_infinite_volume_old_fraction=float(analytic["old_fraction"][j]),
                       maximum_comoving_bubble_radius_cm=max_radius,
                       periodic_images_affect_bubbles=bool(max_radius >= length/2),
                       cell_size_cm=float(a[j]*length/cells))
        result.append(catalog)
    return {"source": GEOMETRY_SOURCE, "model": "Poisson_shared_speed_spherical_growth_periodic_voxels",
            "seed": int(seed), "cells": cells, "box_comoving_cm": length,
            "nucleation_events": len(events["birth_time_s"]), "expected_events": events["expected_events"],
            "snapshots": result, "surface_dynamics": "NOT_COMPUTED_BY_GEOMETRY",
            "uncertainties": "requires independent seeds, larger box and grid refinement"}


def geometry_from_p7(records, config):
    """Optional P7 artifact, computed from that corner's actual rate/a/v rows."""
    require_source(config, "pocket geometry")
    if records[0]["phase_fraction"] != 0:
        raise OpenInput("geometry needs a nucleation history starting wholly in the old phase")
    history = {k: [r[k] for r in records] for k in ("time_s", "scale_factor", "wall_speed")}
    history["nucleation_rate_cm3_s"] = [r["nucleation_rate_MeV4"]/(HBAR_MEV_S*HBARC_MEV_CM**3) for r in records]
    kind = config.get("kind")
    if kind == "projected_constant_speed":
        return projected_distribution(history, int(config["snapshot_index"]), constant_speed_rtol=config.get("constant_speed_rtol", 1e-8))
    if kind != "poisson_voxel":
        raise OpenInput("supported geometry models: poisson_voxel or projected_constant_speed")
    seeds = config.get("seeds", [])
    if not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int or s < 0 for s in seeds):
        raise InputError("geometry needs explicit independent integer seeds")
    runs = [voxel_geometry(history, box_comoving_cm=config["box_comoving_cm"], cells=config["cells"],
                           seed=s, snapshot_indices=config["snapshot_indices"]) for s in seeds]
    fractions = np.array([[v["old_fraction"] for v in r["snapshots"]] for r in runs])
    return {"source": config["source"], "runs": runs, "seed_mean_old_fraction": fractions.mean(axis=0).tolist(),
            "seed_standard_error": (fractions.std(axis=0, ddof=1)/math.sqrt(len(seeds))).tolist() if len(seeds) > 1 else None,
            "feedback_into_P7": False, "dynamics_status": "REQUIRES_SELECTED_TRAPPED_PARTICLE_MODEL"}


def evolve_thermal_pocket(config):
    """Pressure-controlled radius + trapped energy + emitted energy, in seconds.

    This is Eqs.3.2-3.6 with supplied constant DeltaV, surface emissivity
    xi and volumetric cooling C. Conservation includes the disappearing
    vacuum volume. Radius and density change together; cooling changes the
    pressure and hence velocity. Surface tension/inertia/FRW gradients are
    not part of this declared local model and are checked as small inputs.
    """
    require_source(config, "thermal pocket parameters")
    domain = config.get("domain", {})
    if any(domain.get(k) is not True for k in ("thermal_massless_trapped_particles", "negligible_wall_inertia",
                                              "negligible_surface_energy", "negligible_self_gravity")):
        raise OpenInput("thermal pocket evolution requires the four explicit applicability conditions")
    if not domain.get("source"):
        raise OpenInput("pocket applicability needs an independent model source")
    radius0 = finite(config["radius0_cm"], "initial pocket radius", positive=True)
    rho0 = finite(config["rho0_MeV4"], "initial trapped density", positive=True)
    vacuum = finite(config["delta_v_MeV4"], "vacuum pressure", positive=True)
    g = finite(config["g_trapped"], "trapped effective DOFs", positive=True)
    xi = finite(config.get("surface_emissivity", 0), "surface emissivity", nonnegative=True)
    cooling = finite(config.get("volume_cooling_MeV4_s", 0), "volume cooling", nonnegative=True)
    time = np.asarray(config["time_s"], float)
    if time.ndim != 1 or len(time) < 2 or not np.isfinite(time).all() or np.any(np.diff(time) <= 0):
        raise InputError("pocket times must be strictly increasing")
    h = finite(domain["max_H_s_inv"], "local Hubble bound", nonnegative=True)
    expansion_tolerance = finite(domain.get("max_H_delta_t", .01), "neglected expansion tolerance", positive=True)
    if h*max(time[-1]-time[0], radius0/C_CM_S) > expansion_tolerance:
        raise OpenInput("local pocket approximation does not cover the requested Hubble duration")
    if rho0 > 3*vacuum*(1+1e-12):
        raise OpenInput("initial pocket would expand; this closure implements shrinking/stalled pockets")
    cutoff = finite(config.get("minimum_radius_fraction", 1e-4), "small-radius cutoff", positive=True)
    if cutoff >= 1:
        raise InputError("minimum radius fraction must be below one")
    compactness_limit=finite(domain.get("max_compactness",.01),"negligible-gravity compactness limit",positive=True)
    if compactness_limit>.1:
        raise OpenInput("a compactness limit above .1 cannot establish negligible self-gravity")
    def compactness(radius,density):
        return (8*np.pi/3)*G_NEWTON_MEV_MINUS2*(density+vacuum)*(radius/HBARC_MEV_CM)**2
    if compactness(radius0,rho0)>=compactness_limit:
        raise OpenInput("initial pocket violates the declared negligible-self-gravity compactness bound")
    energy0 = 4*np.pi/3*radius0**3*(rho0+vacuum)/HBARC_MEV_CM**3

    def rhs(t, y):
        # Log coordinates keep adaptive trial stages positive while an event
        # locates the supplied small-radius cutoff. A valid collapse must not
        # fail because an explicit RK trial stepped through R=0 beforehand.
        r, rho = radius0*math.exp(y[0]),rho0*math.exp(y[1])
        alpha = vacuum/rho
        v = max(0., 4/(1+math.sqrt(1+8/(3*alpha)))-1)
        dr = -C_CM_S*v
        loss = 3*xi*C_CM_S*rho/r+cooling
        drho = -3*dr*(rho+vacuum)/r-loss
        power = 4*np.pi/3*r**3*loss/HBARC_MEV_CM**3
        return np.array([dr/r, drho/rho, power/energy0])

    def small(t, y):
        return y[0]-math.log(cutoff)
    small.terminal = True
    small.direction = -1
    def gravity(t,y):
        return compactness_limit-compactness(radius0*math.exp(y[0]),rho0*math.exp(y[1]))
    gravity.terminal=True;gravity.direction=-1
    sol = solve_ivp(rhs, (float(time[0]), float(time[-1])), [0.,0.,0.], dense_output=True,
                    events=(small,gravity), rtol=config.get("rtol", 1e-9),
                    atol=config.get("atol_relative", 1e-11), method="DOP853")
    if not sol.success:
        raise RuntimeError(sol.message)
    selected = time[time <= sol.t[-1]]
    if selected[-1] < sol.t[-1]:
        selected = np.r_[selected, sol.t[-1]]
    log_state=sol.sol(selected)
    y=np.vstack((radius0*np.exp(log_state[0]),rho0*np.exp(log_state[1]),energy0*log_state[2]))
    energy = 4*np.pi/3*y[0]**3*(y[1]+vacuum)/HBARC_MEV_CM**3
    balance = (energy+y[2]-energy0)/energy0
    return {"source": DYNAMICS_SOURCE, "parameter_source": config["source"],
            "time_s": selected.tolist(), "radius_cm": y[0].tolist(), "rho_MeV4": y[1].tolist(),
            "temperature_MeV": ((30*y[1]/(np.pi**2*g))**.25).tolist(),
            "surface_area_cm2": (4*np.pi*y[0]**2).tolist(),
            "wall_speed": [max(0., 4/(1+math.sqrt(1+8*r/(3*vacuum)))-1) for r in y[1]],
            "emitted_energy_MeV": y[2].tolist(), "remaining_energy_MeV": energy.tolist(),
            "relative_energy_balance": balance.tolist(),
            "max_relative_energy_balance": float(np.max(np.abs(balance))),
            "compactness_2GE_over_R":compactness(y[0],y[1]).tolist(),
            "max_compactness":float(np.max(compactness(y[0],y[1]))),
            "declared_compactness_limit":compactness_limit,
            "terminal_radius_without_cooling_cm": radius0*((1+vacuum/rho0)/(4*vacuum/rho0))**(1/3),
            "termination": ("SMALL_RADIUS_REQUIRES_NEW_PHYSICS" if len(sol.t_events[0]) else
                            "SELF_GRAVITY_REQUIRES_NEW_PHYSICS" if len(sol.t_events[1]) else "REQUESTED_TIME"),
            "feedback_into_P7": False,
            "limitations": ["spherical thermal trapped radiation; specified pressure and cooling",
                            "no trapping calculation, surface tension, self-gravity or spatial hydrodynamics",
                            "emission recipient/spectrum and embedding into the global history remain model inputs"]}


def main():
    import argparse
    from pathlib import Path
    from .common import read_json, write_json, canonical_hash, sha256
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("geometry","dynamics"))
    parser.add_argument("config",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    if args.output.exists():
        raise InputError("preserve existing pocket output and choose a new path")
    config=read_json(args.config)
    if args.mode=="geometry":
        result=voxel_geometry(config["history"],**config["numerics"])
    else:
        result=evolve_thermal_pocket(config)
    write_json(args.output,{"schema":"r135-pocket-extension-v1","input":config,"input_sha256":canonical_hash(config),
                            "source_sha256":sha256(Path(__file__)),"result":result,
                            "evidence_status":"CONDITIONAL","scientific_acceptance":"owner_review"})


if __name__=="__main__":main()
