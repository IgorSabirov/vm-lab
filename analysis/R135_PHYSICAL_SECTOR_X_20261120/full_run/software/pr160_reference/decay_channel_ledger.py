"""Reconstruct integrated forward and inverse energy by exclusive P6 decay channel on a saved P7 trajectory."""
import argparse
import sys
from pathlib import Path

import numpy as np
from scipy.integrate import trapezoid

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOFTWARE))
from r135.collisions import CORNERS, decay_table
from r135.common import HBAR_MEV_S, InputError, OpenInput, read_json, sha256, write_json
from r135.history import ENERGY, SECTORS, equilibrium_relic_density


def integral(times, power, activation):
    if activation >= times[-1]:
        return 0.
    start = max(times[0], activation)
    active = times > start
    t = np.r_[start, times[active]]
    p = np.r_[np.interp(start, times, power), power[active]]
    return float(trapezoid(p, t))


def ledger(root):
    definition = read_json(root/"history_definition.json")
    config = definition["config"]
    relic = config.get("relic")
    if not relic:
        raise OpenInput("P7 must contain an explicit relic with resolved exclusive widths")
    widths = [r for r in decay_table([relic]) if r["recipient"] in SECTORS[1:4]]
    if len({r["channel"] for r in widths}) != len(widths):
        raise InputError("duplicate exclusive decay channel")
    history = read_json(root/"channel_history.json")["histories"]
    balances = read_json(root/"balance.json")["corners"]
    mass = relic["mass_MeV"]
    output = {}
    files = [root/name for name in ("channel_history.json","history_definition.json","balance.json")]
    for corner in CORNERS:
        channel, meta = history[corner], balances[corner]
        cp_path = root/f"checkpoint_{corner}.json"
        files.append(cp_path)
        cp = read_json(cp_path)
        if cp["corner"] != corner or cp["input_sha256"] != meta["input_sha256"]:
            raise InputError("relic numbers and phase history have different provenance")
        t = np.asarray(channel["time_s"])
        a = np.asarray(channel["scale_factor"])
        stored_t = meta["t0_s"]+np.asarray(cp["sample_tau"])/meta["H0_s_inv"]
        state = np.asarray(cp["sample_states"])
        if (not np.array_equal(stored_t,t) or np.any(np.diff(t) <= 0)
                or not np.allclose(meta["a0"]*np.exp(state[:,0]),a,rtol=1e-13,atol=0)):
            raise InputError("P7 checkpoint and exported time or scale factor disagree")
        n = np.maximum(state[:,5],0)
        active_since = meta["isolation_model"]["decay_activation_s"]
        thin = np.unique(np.r_[np.arange(0,len(t),2),len(t)-1])
        rows = []
        for width in widths:
            bath = width["recipient"]
            coef = a**3 * mass * width["width_MeV"]/HBAR_MEV_S
            forward = coef*n
            inverse = np.zeros_like(forward)
            if width["width_MeV"] and relic["kinetic_model"] == "relativistic_MB":
                temperatures = channel["T_"+bath+"_MeV"]
                inverse = coef*np.array([equilibrium_relic_density(T,mass,relic.get("degeneracy",1))[0]
                                         for T in temperatures])
            fwd, inv = [integral(t,p,active_since) for p in (forward,inverse)]
            coarse = [integral(t[thin],p[thin],active_since) for p in (forward,inverse)]
            rows.append({"id":width["channel"],"recipient":bath,"source":width["source"],
                         "width_MeV":width["width_MeV"],"forward_MeV4":fwd,"inverse_MeV4":inv,
                         "net_MeV4":fwd-inv,"coarse_fine_absolute_MeV4":max(abs(fwd-coarse[0]),abs(inv-coarse[1]))})
        emitted = sum(r["forward_MeV4"] for r in rows)
        total = sum(r["net_MeV4"] for r in rows)
        for r in rows:
            r["fraction_of_forward_energy"] = r["forward_MeV4"]/emitted if emitted else None
            r["net_over_initial_comoving_latent_heat"] = r["net_MeV4"]/(meta["a0"]**3*meta["latent_heat_MeV4"])
        # The P7 integrated relic source contains phase formation minus net decays.
        # When formation is off it independently checks the exclusive energy sum.
        mismatch = None
        if not relic.get("latent_energy_fraction",0):
            expected = -state[-1,ENERGY][SECTORS.index("relic")]
            mismatch = float(abs(total-expected)/max(emitted,sum(r["inverse_MeV4"] for r in rows),1e-300))
        output[corner] = {"channels":rows,"forward_total_MeV4":emitted,"net_total_MeV4":total,
                          "relative_mismatch_with_independent_relic_source":mismatch}
    return {"units":"comoving energy = integral a^3 Q dt in MeV^4","source_sha256":{p.name:sha256(p) for p in files},
            "relic":relic["id"],"kinetic_model":relic["kinetic_model"],"corners":output}


def control(root):
    sys.path.insert(0,str(SOFTWARE/"tests"))
    from test_history import fixture
    from r135 import history
    cfg,eos,kernel,wall,coll,init = fixture()
    coll["thermal_channels"] = []
    channels = [{"id":ident,"recipient":bath,"width_MeV":rate*HBAR_MEV_S,"kind":"supplied_width",
                 "daughter_masses_MeV":[0,0],"source":"assigned exclusive control width"}
                for ident,bath,rate in (("em_a","gamma",.05),("em_b","gamma",.10),("invisible","free",.10))]
    cfg.update(samples=1025,rtol=1e-9,atol_relative=1e-12,
               relic={"id":"unstable_control","mass_MeV":2,"source":"conditional single MB parent",
                      "kinetic_model":"relativistic_MB","instant_thermalization":True,"channels":channels,
                      "excluded_from_phase_eos":True},
               collision_model=coll,wall_transport=wall,eos_bundle=eos,nucleation_definition=kernel,initial_history=init)
    init.update(surface="postconfinement",phase_fraction=1.,relic_n_MeV3=.01,relic_T_MeV=.2)
    result = history.run(cfg,{},root)
    if result["software_status"] != "PASS":
        raise RuntimeError("conditional P7 decay run failed: "+str(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--p7",type=Path)
    mode.add_argument("--control",action="store_true")
    parser.add_argument("--out",required=True,type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    if args.control:
        args.p7 = args.out/"P7"
        control(args.p7)
    result = ledger(args.p7)
    if args.control:
        for corner in result["corners"].values():
            fractions = [r["fraction_of_forward_energy"] for r in corner["channels"]]
            if (not np.allclose(fractions,[.2,.4,.4]) or not all(r["inverse_MeV4"]>0 for r in corner["channels"])
                    or corner["relative_mismatch_with_independent_relic_source"] > 1e-3):
                raise RuntimeError("exclusive energy check failed")
        result["physical_point"] = False
    write_json(args.out/"decay_channels.json",result)
