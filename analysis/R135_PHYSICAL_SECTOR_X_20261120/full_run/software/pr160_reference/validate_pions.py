"""Compare two active-BBN kernels with a prescribed dilute pion population switched on and off."""
from pathlib import Path
import argparse
import copy
import math
import sys

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOFTWARE))
from r135.backends import NativePair
from r135.common import HBARC_MEV_CM, read_json, sha256, write_json
from r135.meson_conversion import project
from r135.observations import bridge_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    out = parser.parse_args().out
    out.mkdir(parents=True,exist_ok=False)
    base = SOFTWARE/"extensions_reference/p7_bbn_control"
    item, h = read_json(base/"BBN_input.json"), read_json(base/"P7_history.json")
    if bridge_hash(h) != item["source_history_sha256"]:
        raise ValueError("expected the retained P7 reference")
    times = h["time_s"]
    grid, mass = [0.,1.], 139.57039
    labels = ("pi_minus","pi_plus")
    h["kinetic_species"] = copy.deepcopy(h.get("kinetic_species", [[] for _ in times]))
    for t, a, species in zip(times,h["scale_factor"],h["kinetic_species"],strict=True):
        # Deliberately prescribed test number densities. No X yield or transport law is inferred.
        for name, density in zip(labels, (2e14,1e14),strict=True):
            f = 6*math.pi**2*(a*HBARC_MEV_CM)**3*density*math.exp(-t / 2.)
            species.append({"name":name, "mass_MeV":mass,"degeneracy":1,"statistics":"boson",
                            "q_edges_MeV":grid,"occupation":[f]})
    history_key = bridge_hash(h)
    spec = {"source":"constant cell cross sections assigned for the numerical control",
            "unit":"cm^3/s","time_s":times,"history_sha256":history_key, "channels":{}}
    for direction, label in zip(("pi_minus_p_to_n","pi_plus_n_to_p"),labels,strict=True):
        spec["channels"][direction] = {"species":label,"mass_MeV":mass,"q_edges_MeV":grid,"sigma_v":[[4e-17] for t in times]}
    added = project(h, spec, history_key)
    write_json(out/"projected_rates.json",added)
    pair = NativePair()
    results = {}
    tolerance = {"rtol":1e-7,"atol":1e-11}
    for e in ("linx","primat"):
        values = {}
        for state in ("off","on"):
            candidate = {**item,"source_history_sha256":history_key}
            if state == "on":
                candidate["pion_conversion"] = added
            y, receipt = pair.solve(candidate,e,tolerance,out/e/state)
            values[state] = {k:y[k] for k in ("D_H","Yp","max_baryon_error")}
        values["delta_Yp"] = values["on"]["Yp"] - values["off"]["Yp"]
        if values["delta_Yp"] <= 0:
            raise RuntimeError("the asymmetric pion-conversion check gave the wrong helium sign")
        results[e] = values
    if not math.isclose(results["linx"]["delta_Yp"],results["primat"]["delta_Yp"], rel_tol=.005):
        raise RuntimeError("native pion sensitivity differs between engines")
    report = {"status":"PASS","physical_point":False,"background":"fixed archived diagnostic P7",
              "input_sha256":sha256(base/"BBN_input.json"),"full_hadronic_cascade":False,
              "independent_native_solves":4,"tolerance":tolerance,"results":results}
    write_json(out/"VALIDATION.json",report)
    print(report)


if __name__ == "__main__":
    main()
