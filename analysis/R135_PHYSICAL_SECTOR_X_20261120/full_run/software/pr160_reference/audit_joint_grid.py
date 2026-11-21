"""Replay the P10 claim matrix for each completed coordinate of a technical paired fit."""
import argparse
import csv
from pathlib import Path
import sys
SOFTWARE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOFTWARE))
from r135 import audit
from r135.common import read_json, sha256, write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("grid","out","planck-root","planck-python"):
        p.add_argument("--"+k,type=Path,required=True)
    args=p.parse_args()
    args.out.mkdir(exist_ok=False,parents=True)
    spec=read_json(args.grid/"GRID.json")
    rows=[]
    for i, cell in enumerate(spec["cells"]):
        for model in ("baseline","X"):
            root=args.grid/str(i)/model
            receipt=read_json(root/"P9/EXECUTION_RECEIPT.json")
            key=receipt["key"]
            stages=("P1","P7","P8","P9") if (root/"P1").is_dir() else ("P7","P8","P9")
            config={"_mode":"validation","expected_keys":[key],"required_stages":{key["claim_id"]:list(stages)},
                    "results":[{"key":key,"stage":s,"manifest_input":s} for s in stages],
                    "planck_data_root":str(args.planck_root.resolve()),"planck_python":str(args.planck_python.absolute()),
                    "planck_python_sha256":sha256(args.planck_python)}
            output=args.out/str(i)/model
            audit.run(config,{s:root/s/"MANIFEST.json" for s in stages},output)
            detail=read_json(output/"audit_details.json")["stages"]
            with (output/"claim_matrix.csv").open() as stream:
                matrix=next(csv.DictReader(stream))
            rows.append({"coordinates":cell["coordinates"],"model":model,"claim_status":matrix["status"],
                         "gw_status":matrix["gw_status"],"stages":{s:detail[s]["status"] for s in stages},
                         "P7_reasons":detail["P7"].get("reasons",[]),"P9_reasons":detail["P9"].get("reasons",[]),
                         "lineage_reasons":{s:detail[s].get("lineage_reasons",[]) for s in stages},
                         "class_precision":detail["P9"]["cmb_precision"],
                         "max_P7_energy_or_work_quadrature_error":max(
                             max(v["relative_energy_quadrature_error"],v["relative_work_quadrature_error"])
                             for v in detail["P7"]["recomputed"].values()),
                         "expected_spectra":receipt["result"]["metrics"]["class_integrations"],
                         "native_trajectories":detail["P9"]["native_runs"],
                         "spectra_replayed":detail["P9"]["independently_replayed_spectra"]})
    if any(r["spectra_replayed"] != r["expected_spectra"] or r["native_trajectories"] != 30 for r in rows):
        raise RuntimeError("incomplete P10 numerical reconstruction")
    for row in rows:
        if "P1" in row["stages"]:
            numerical_checks = (row["stages"]["P7"] == "RECONSTRUCTED",
                                row["stages"]["P8"] == "RECONSTRUCTED",
                                not any(row["lineage_reasons"].values()),
                                all(e["status"] == "PASS" for e in row["class_precision"].values()),
                                all(reason.startswith("GW:") for reason in row["P9_reasons"]))
            if not all(numerical_checks):
                raise RuntimeError(f"incomplete linked BBN/CMB replay at {row['coordinates']} ({row['model']}): {row}")
    write_json(args.out/"VALIDATION.json",{"physical_point":False,"rows":rows,
               "producer_grid_sha256":sha256(args.grid/"joint_grid.json")})


if __name__=="__main__":
    main()
