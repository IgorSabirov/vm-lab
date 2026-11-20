"""Run the existing P7 exchange control at three resolutions and reconstruct its outputs."""
import argparse
from pathlib import Path
import sys

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOFTWARE), str(SOFTWARE/"tests")]
from test_history import fixture
from r135 import audit, history
from r135.common import read_json, sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=False)
    config, *inputs = fixture()
    config.update(dict(zip(("eos_bundle","nucleation_definition","wall_transport","collision_model","initial_history"),inputs)))
    config.update(samples=513, rtol=1e-9, atol_relative=1e-12, max_step_H0=.025, history_refinement={
        "coarser_levels":[{"rtol":1e-7,"atol_relative":1e-10,"max_step_H0":.1},
                          {"rtol":1e-8,"atol_relative":1e-11,"max_step_H0":.05}],
        "max_abs_normalized_change":1e-4})
    result = history.run(config,{},out)
    check = audit.audit_p7({"root":out,"request":{"config":config,"inputs":[]}})
    resolution = read_json(out/"history_refinement.json")
    if result["software_status"] != "PASS" or resolution["mixed"]["status"] != "PASS":
        raise RuntimeError("P7 diagnostic refinement did not pass")
    report = {"software_status":result["software_status"], "physical_point":False, "num_integrations":15,
              "max_balance":max(max(r["relative_balances"]) for r in resolution["corners"].values()),
              "mixed":resolution["mixed"], "audit_status":check["status"], "unresolved":check.get("reasons",[]),
              "config_sha256":sha256(out/"history_definition.json"), "raw_sha256":sha256(out/"phase_history.csv")}
    write_json(out/"VALIDATION.json",report)
    print(report)


if __name__ == "__main__":
    main()
