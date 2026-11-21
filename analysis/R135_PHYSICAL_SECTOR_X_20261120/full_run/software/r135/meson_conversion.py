"""Charged-pion conversion of free nucleons on a prescribed P7 pion distribution."""
import math
import numpy as np

from .common import HBARC_MEV_CM, InputError, canonical_hash, finite, require_source


def project(history, reference, history_sha):
    """Fold cell-averaged sigma*v (cm^3/s) with physical pion number in each q cell."""
    require_source(reference, "charged-pion transport kernel")
    if (reference.get("history_sha256") != history_sha or reference.get("unit") != "cm^3/s"
            or reference.get("time_s") != history["time_s"]):
        raise InputError("pion conversion kernel does not match the history, time grid or units")
    channels = reference.get("channels", {})
    if set(channels) != {"pi_minus_p_to_n", "pi_plus_n_to_p"}:
        raise InputError("both charged pion conversion directions must be specified")
    result = {"time_s": history["time_s"], "history_sha256": history_sha, "kernel_sha256":canonical_hash(reference)}
    snapshots = history.get("kinetic_species", [])
    if len(snapshots) != len(history["time_s"]):
        raise InputError("pion conversion needs the resolved P7 distributions")
    names = [ch["species"] for ch in channels.values()]
    if len(set(names)) != 2:
        raise InputError("the two charged pion species must be distinct")
    for direction, key in (("pi_minus_p_to_n","p_to_n_s_inv"), ("pi_plus_n_to_p","n_to_p_s_inv")):
        channel = channels[direction]
        mass = finite(channel["mass_MeV"], "pion mass", positive=True)
        if len(channel["sigma_v"]) != len(snapshots):
            raise InputError("pion conversion kernel has the wrong number of times")
        values = []
        for i, snapshot in enumerate(snapshots):
            matches = [s for s in snapshot if s["name"] == channel["species"]]
            if len(matches) != 1:
                raise InputError("pion transport species is absent or ambiguous")
            s = matches[0]
            if (s["mass_MeV"] != mass or s["statistics"] not in ("boson","BE") or s["degeneracy"] != 1
                    or s["q_edges_MeV"] != channel["q_edges_MeV"]):
                raise InputError("pion identity or momentum support differs")
            q = np.asarray(s["q_edges_MeV"],float)
            f, kernel = np.asarray(s["occupation"],float), np.asarray(channel["sigma_v"][i],float)
            if (f.ndim != 1 or q.shape != (len(f)+1,) or q[0] != 0 or not np.isfinite(q).all()
                    or np.any(np.diff(q)<=0) or kernel.shape != f.shape or
                    not np.isfinite(f).all() or np.any(f<0) or not np.isfinite(kernel).all() or np.any(kernel<0)):
                raise InputError("invalid pion occupation or cell conversion kernel")
            a = finite(history["scale_factor"][i], "pion scale factor", positive=True)
            density_cm3 = np.diff(q**3)*f/(6*math.pi**2*(a*HBARC_MEV_CM)**3)
            values.append(finite(density_cm3 @ kernel, "pion conversion rate", nonnegative=True))
        result[key] = values
    return result
