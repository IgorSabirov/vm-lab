"""Check three actual solver resolutions at fixed physics and sampling times."""
import copy
import numpy as np
from .common import finite, InputError


def curves(rows, energy_unit):
    return {"time_s":[r["time_s"] for r in rows],
            "f":[r["phase_fraction"] for r in rows],
            "H_over_H0":[r["H_s_inv"]/rows[0]["H_s_inv"] for r in rows],
            "T_X_over_T0":[r["T_X_MeV"]/rows[0]["T_X_MeV"] for r in rows],
            "delivered_energy":[(np.asarray(r["comoving_energy_sources_MeV4"])/energy_unit).tolist() for r in rows]}


def check(levels, limit):
    limit = finite(limit, "history convergence tolerance", positive=True)
    if len(levels) != 3:
        raise InputError("three actual resolution levels required for P7")
    deltas = []
    for coarse, fine in zip(levels, levels[1:]):
        if coarse["time_s"] != fine["time_s"]:
            raise InputError("P7 refinement changed the sampling coordinates")
        changes = {}
        for key in ("f","H_over_H0","T_X_over_T0","delivered_energy"):
            a, b = np.asarray(coarse[key]), np.asarray(fine[key])
            if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
                raise InputError("invalid P7 refinement observable")
            changes[key] = float(np.max(np.abs(a-b)))
        deltas.append(changes)
    return {"adjacent_max_abs":deltas, "tolerance":limit,
            "status":"PASS" if max(deltas[-1].values()) <= limit else "FAIL_CONVERGENCE"}


def run(model, corner, rows, meta, policy):
    from .history import summarize
    cfg = model.config
    if "atol_state" in cfg:
        raise InputError("relative P7 refinement requires atol_relative; explicit component tolerances need their own sequence")
    finest = {k:finite(cfg.get(k,d), k, positive=True) for k,d in
              (("rtol",1e-7),("atol_relative",1e-10),("max_step_H0",None))}
    coarse = policy.get("coarser_levels", [])
    definitions = [*coarse,finest]
    if (len(coarse) != 2 or any(set(level)!=set(finest) for level in coarse)
            or any(not finite(a[k],k,positive=True)>finite(b[k],k,positive=True)
                   for a,b in zip(definitions,definitions[1:]) for k in finest)):
        raise InputError("P7 requires ordered coarse, intermediate and fine step sizes and tolerances")
    scale = meta["a0"]**3 * meta["latent_heat_MeV4"]
    levels, balances, calls = [], [], []
    for level in coarse:
        candidate = copy.copy(model)
        candidate.config = {**cfg, **level}
        sample, settings = candidate.solve(corner)
        summary = summarize(sample,settings)
        levels.append(curves(sample,scale))
        balances.append(max(summary[k] for k in ("max_relative_sector_balance","max_relative_radiation_balance","max_relative_total_balance")))
        calls.append(settings["nfev"])
    summary = summarize(rows,meta)
    balances.append(max(summary[k] for k in ("max_relative_sector_balance","max_relative_radiation_balance","max_relative_total_balance")))
    levels.append(curves(rows,scale))
    calls.append(meta["nfev"])
    return {"settings":definitions,"nfev":calls,"levels":levels,"relative_balances":balances,
            "check":check(levels,policy["max_abs_normalized_change"])}


def mixed_check(cases, limit):
    residuals = {"full_minus_additive": [], "factorial_interaction": []}
    for i in range(3):
        c = {k: v["levels"][i] for k, v in cases.items()}
        times = c["00"]["time_s"]
        if any(row["time_s"] != times for row in c.values()):
            raise InputError("five-corner refinement needs a common saved time grid")
        pair = {name: {"time_s": times} for name in residuals}
        for key in ("f", "T_X_over_T0", "H_over_H0", "delivered_energy"):
            values = {corner: np.asarray(row[key]) for corner, row in c.items()}
            pair["full_minus_additive"][key] = (values["11full"] - values["11add"]).tolist()
            pair["factorial_interaction"][key] = (
                values["11full"] - values["10"] - values["01"] + values["00"]).tolist()
        for name, level in pair.items():
            residuals[name].append(level)
    checks = {name: check(levels, limit) for name, levels in residuals.items()}
    return {"residuals": checks, "status": "PASS" if all(
        result["status"] == "PASS" for result in checks.values()) else "FAIL_CONVERGENCE"}
