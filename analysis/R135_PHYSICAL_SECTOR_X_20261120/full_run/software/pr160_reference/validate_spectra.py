"""Compare both mass scales and independently parsed glueball spectra on the four FMS preparations."""
import argparse
import math
from pathlib import Path
import sys

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOFTWARE),str(SOFTWARE/"tests"),str(SOFTWARE/"donors")]
from audit import SM, boundary, gas_entropy
from kinetic_control import kinetic
from fetch import obtain, sources
from test_donor_inputs import donor_config
from r135.donor_inputs import prepare
from r135.common import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--stable-omega-threshold",type=float,
                        help="declared diagnostic density threshold for the stable single-species calculation")
    parser.add_argument("--offline",action="store_true")
    args = parser.parse_args()
    if args.stable_omega_threshold is not None and not (math.isfinite(args.stable_omega_threshold) and args.stable_omega_threshold>0):
        parser.error("the density threshold must be positive and finite")
    args.out.mkdir(parents=True,exist_ok=False)
    sm = SM(obtain(args.cache,sources()["sm"],args.offline))
    rows, source_ids = [], {}
    for panel in ("top-left","top-right","bottom-left","bottom-right"):
        for route in ("r0","string_tension"):
            gases = {}
            for model in ("fms","athenodorou_teper"):
                cfg = {**donor_config(str(args.cache)),"point_id":"XB-FMS-"+panel,"scale_method":route,
                       "spectrum_model":model,"offline":args.offline}
                d = prepare(cfg)
                point, states = d["literature_preparation"],d["relic_spectrum_control"]["states"]
                m, ratio = point["m0_GeV"], d["scale"]["ratio"]["value"]
                four = [s for s in states if (s.get("index") in (1,2,4,5) if model=="fms" else
                        s["level"]=="gs" and s["JPC"] in ("0^{++}","2^{++}","0^{-+}","2^{-+}"))]
                if len(four) != 4 or {s["JPC"] for s in four} != {"0^{++}","2^{++}","0^{-+}","2^{-+}"}:
                    raise ValueError("common quartet differs")
                source_ids[model] = d["relic_spectrum_control"]["donor_sha256"]
                gases[model] = {}
                for size,species in (("common_four",four),("all_listed",states)):
                    gases[model][size] = {"count":len(species)}
                    for name,bose in (("NR",False),("Bose",True)):
                        entropy = gas_entropy(species,1/ratio,bose)
                        gases[model][size][name] = boundary(sm,m,point["R_post"],1/ratio,entropy)
            rates = {str(B):kinetic(sm,m,point["R_post"],1/ratio,B=B)["Omega_h2"] for B in (.3,1.,3.)}
            rows.append({"preparation":point["point_id"],"scale":route,"Tc_over_m0":ratio,
                         "lattice_EOS_boundary":point,"ideal_gas_models":gases,"isolated_single_species_Omega_h2":rates})
    decisions = []
    for first, second in zip(rows[::2],rows[1::2],strict=True):
        stable = [entry["isolated_single_species_Omega_h2"] for entry in (first,second)]
        delta = {b:stable[1][b]/stable[0][b]-1 for b in stable[0]}
        threshold = args.stable_omega_threshold
        if threshold is None:
            disposition = "THRESHOLD_NOT_SPECIFIED"
        elif any((stable[0][b]>threshold) != (stable[1][b]>threshold) for b in delta):
            disposition = "SCALE_DEPENDENCE_UNRESOLVED"
        else:
            disposition = "SAME_STABLE_DENSITY_CLASSIFICATION_ON_TESTED_SCALES"
        decisions.append({"preparation":first["preparation"], "relative_change_string_vs_r0":delta,
                          "stable_omega_threshold":threshold, "scope":"stable single species only", "disposition":disposition})
    write_json(args.out/"VALIDATION.json",{"points":4,"scale_branches":2,"stable_single_species_integrations":24,
               "spectrum_sha256":source_ids,"results":rows,"scale_decisions":decisions,"full_X_outcome":"OPEN_INPUT",
               "combination":"separate model and scale sensitivities, no averaging"})


if __name__=="__main__":
    main()
