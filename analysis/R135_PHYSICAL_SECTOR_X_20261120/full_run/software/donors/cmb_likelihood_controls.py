"""Evaluate ACT DR6 and SPT-3G D1 with the collaborations' likelihoods on their test cosmologies."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
from importlib.metadata import version

import numpy as np
import yaml

from fetch import acquire


def evaluate(paths, folder):
    import act_dr6_cmbonly.act_dr6_cmbonly as act
    import candl
    from cobaya.model import get_model

    if (
        hashlib.sha256(Path(act.__file__).read_bytes()).digest()
        != hashlib.sha256(paths["act-implementation"].read_bytes()).digest()
    ):
        raise ValueError("ACT implementation does not match the donor revision")
    data = folder / "data/ACTDR6CMBonly/v1.0"
    data.mkdir(parents=True)
    with tarfile.open(paths["act-release"]) as archive:
        member = archive.getmember("v1.0/dr6_data_cmbonly.fits")
        with (
            archive.extractfile(member) as src,
            (data / "dr6_data_cmbonly.fits").open("wb") as out,
        ):
            shutil.copyfileobj(src, out)
    # Rerun precisely the registered upstream TTTEEE test; no fitting of the spectrum.
    params = dict(
        ombh2=0.022,
        omch2=0.117,
        ns=0.96,
        As=2e-9,
        tau=0.065,
        cosmomc_theta=0.010409,
        A_act=1.0,
        P_act=1.0,
    )
    info = {
        "params": params,
        "packages_path": str(folder),
        "theory": {
            "camb": {
                "path": "global",
                "extra_args": {
                    "lmax": 9000,
                    "lens_potential_accuracy": 8,
                    "min_l_logl_sampling": 6000,
                },
            }
        },
        "likelihood": {
            "act_dr6_cmbonly": {
                "input_file": "dr6_data_cmbonly.fits",
                "stop_at_error": True,
            }
        },
    }
    with get_model(info) as model:
        act_ll = float(model.loglikes({})[0][0])
    for name, path in paths.items():
        if name.startswith("spt-"):
            filename = name.removeprefix("spt-")
            directory = folder / "windows" if "window_functions" in filename else folder
            directory.mkdir(exist_ok=True)
            shutil.copyfile(path, directory / filename)
    test = yaml.safe_load(paths["spt-control-yaml"].read_bytes())
    spec = np.loadtxt(paths["spt-control-spectrum"])
    pars = dict(test["param_values"])
    pars["Dl"] = {
        name: spec[:, i]
        for i, name in enumerate(["ell", "TT", "TE", "EE", "BB", "pp", "kk"])
    }
    like = candl.Like(str(folder / "SPT3G_D1_TnE_lite.yaml"), feedback=False)
    spt_ll = float(like.log_like(pars))
    import re

    act_test = (
        paths["act-test"]
        .read_text()
        .split("def test_TTTEEE():")[1]
        .split("def test_Planck():")[0]
    )
    expected, atol = re.findall(
        r"np.isclose\(loglikes, ([-.\d]+), atol=([e\d-]+)\)", act_test
    )[0]
    # Match the published ACT tolerance, including numpy's default rtol.
    return {
        "ACT": {
            "logL": act_ll,
            "upstream": float(expected),
            "passed": bool(np.isclose(act_ll, float(expected), atol=float(atol))),
        },
        "SPT": {
            "logL": spt_ll,
            "upstream": test["test_logl"],
            "passed": abs(spt_ll / test["test_logl"] - 1) < 1e-3,
        },
        "versions": {
            p: version(p)
            for p in ("camb", "cobaya", "sacc", "candl-like", "numpy", "scipy")
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        result = evaluate(
            acquire(args.cache, {"cmb_extra", "cmb_controls"}, args.offline),
            Path(folder),
        )
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    if not all(result[k]["passed"] for k in ("SPT", "ACT")):
        raise SystemExit("Published likelihood control outside tolerance")
