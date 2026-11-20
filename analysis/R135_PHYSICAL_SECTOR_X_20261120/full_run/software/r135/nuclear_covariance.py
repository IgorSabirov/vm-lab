"""Propagate a registered, weighted nuclear-rate distribution through both BBN engines."""
from __future__ import annotations

import copy
import math
from pathlib import Path
import shutil
import numpy as np

from .common import InputError, canonical_hash, read_json, require_source, sha256, write_json
from .observations import CORNERS, MASSES, SPECIES, bridge_hash


# Exact upstream key_PRIMAT_2023 files at the LINX commit in backends.PINS.
RATE_SHA256 = {
    "Be7nLi7p": "fa69002432b915bcc4c1d1991ada432867bc3743ee46235ab0bcb53975d0230c",
    "He3aBe7g": "55df64bafef9b4cc9156b6c2a15e6e5fd432e09b93201718315ca879e12f6e2f",
    "He3dap": "b1ff33b4a272c15ebc39e7506f719c02b1e6db010e0bf939fd5d71f409979907",
    "He3ntp": "459d228ab72790006b6bb3bd1e4dbb04cff4699c4af499da9f26965a06b0619a",
    "Li7paa": "f0d89f4b88e84994467adc9b37f7274b65a63de469a88ec9004ae463bf40cadc",
    "ddHe3n": "2f25eb6683970d85f04ab9be6f5534391f697cb88c89bc0e4065a87d899718c5",
    "ddtp": "13f3b6962a7171b08758ba73016a8769f0d29f04bbf925fc9720d1d5c25ab33e",
    "dpHe3g": "02b0a3456b83b4a87991fce23b7d3009de3b43b4df0d441c6c5d9efce923f8ce",
    "npdg": "ffc0a608d4783adab7a3500d68ac586ce94c13feafb51c1a12ad2b44ee8a469c",
    "taLi7g": "68dd3e50759e2853de49a74ac7a2b8c4be251da36dd3c0bf2fd44ef53a89678a",
    "tdan": "224e37d4f2f9839a7b6c85436dac0ae9ee3cf82965ca66255873b6dc6de96907",
    "tpag": "38af347ca80d026f157c6def242b44b9e1efd04bd6c38de452baf733798af2e3"
}


def verify_rates(rates, q, root):
    for reaction, shift in zip(rates["reactions"], q, strict=True):
        name = reaction["id"]
        path = root/"nuclear_primary"/(name+".txt")
        if sha256(path) != RATE_SHA256[name]:
            raise InputError("primary nuclear table digest differs")
        grid, median, factor = np.loadtxt(path, unpack=True)
        expected = median * np.exp(float(shift)*np.log(factor))
        if (not np.array_equal(grid, reaction["T9"])
                or not np.allclose(expected, reaction["values"], rtol=2e-13, atol=0)):
            raise InputError("perturbed rates disagree with the registered q and primary table")


def validate_design(spec, reference):
    require_source(spec, "nuclear rate ensemble")
    names = [r["id"] for r in reference["reactions"]]
    central = np.asarray(spec.get("central_q", [0.] * len(names)), float)
    if central.shape != (len(names),) or not np.isfinite(central).all():
        raise InputError("invalid central nuclear parameter vector")
    if spec.get("reaction_order") != names:
        raise InputError("nuclear parameter order differs from the central P8 rates")
    rows = spec.get("nodes", [])
    if not isinstance(rows, list) or len(rows) < 2:
        raise InputError("nuclear covariance requires at least two distinct weighted nodes")
    q = np.asarray([row["q"] for row in rows], float)
    w = np.asarray([row["weight"] for row in rows], float)
    if (q.shape != (len(rows), len(names)) or not np.isfinite(q).all() or
            np.unique(q, axis=0).shape[0] != len(rows) or not np.isfinite(w).all() or
            np.any(w <= 0) or not math.isclose(float(w.sum()), 1., abs_tol=1e-12, rel_tol=0)):
        raise InputError("invalid normalized nuclear quadrature or duplicate rate realization")
    return rows


def covariance(values, weights):
    z = np.asarray(values, float)
    if z.shape != (len(weights), 2) or not np.isfinite(z).all():
        raise InputError("invalid BBN observable ensemble")
    w = np.asarray(weights) / sum(weights)
    delta = z - np.average(z, axis=0, weights=w)
    return ((delta.T*w) @ delta).tolist()


def with_rates(item, rates, reverse):
    item = copy.deepcopy(item)
    item["canonical"]["rates"] = rates
    item["canonical"]["provenance"]["rates_sha256"] = bridge_hash(rates)
    item["reverse_alpha_beta_gamma"] = reverse
    return item


def propagate(spec, histories, pair, tolerance, out):
    from .backends import prepare_native_rates
    base, reverse = prepare_native_rates(spec.get("central_q"))
    nodes = validate_design(spec, base)
    primary = Path(pair.sources["linx"]["source_root"])/"linx/data/nuclear_rates/key_PRIMAT_2023"
    (out/"nuclear_primary").mkdir(exist_ok=True, parents=True)
    for name in RATE_SHA256:
        shutil.copyfile(primary/(name+".txt"), out/"nuclear_primary"/(name+".txt"))
    verify_rates(base, spec.get("central_q", [0.]*len(RATE_SHA256)), out)
    for item in histories.values():
        if (bridge_hash(base) != item["canonical"]["provenance"]["rates_sha256"]
                or canonical_hash(reverse) != canonical_hash(item["reverse_alpha_beta_gamma"])):
            raise InputError("ensemble central nuclear rates differ from the actual P8 input")
    slots, solutions = {}, {}
    for i, node in enumerate(nodes):
        rates, rev = prepare_native_rates(node["q"])
        write_json(out/"nuclear_draws"/str(i)/"rates.json", {"rates": rates, "reverse": rev})
        for corner in CORNERS:
            varied = with_rates(histories[corner], rates, rev)
            for engine in ("linx", "primat"):
                key = canonical_hash([engine, varied, tolerance])
                directory = out/"nuclear_solves"/key
                if key not in solutions:
                    answer, _ = pair.solve(varied, engine, tolerance, directory)
                    solutions[key] = [math.log10(answer["D_H"]), answer["Yp"]]
                slots[f"{i}/{engine}/{corner}"] = key
    matrices = {f"{e}/{c}":covariance([solutions[slots[f"{i}/{e}/{c}"]] for i in range(len(nodes))],
                                        [n["weight"] for n in nodes])
                for e in ("linx","primat") for c in CORNERS}
    report = {"ensemble_sha256":canonical_hash(spec), "central_rates_sha256":bridge_hash(base),
              "coordinate_order":["log10_D_over_H","Yp"], "measure":"normalized discrete population",
              "slots":slots, "unique_native_solves":len(solutions), "covariances":matrices}
    write_json(out/"nuclear_covariance.json", report)
    return matrices


def reconstruct(spec, histories, tolerance, root):
    """Recover each ensemble observation from raw native abundances and input-consumption receipts."""
    report = read_json(root/"nuclear_covariance.json")
    nodes = validate_design(spec, histories[CORNERS[0]]["canonical"]["rates"])
    if canonical_hash(spec) != report["ensemble_sha256"]:
        raise InputError("nuclear posterior differs from the registered input")
    base = histories[CORNERS[0]]["canonical"]["rates"]
    verify_rates(base, spec.get("central_q", [0.]*len(RATE_SHA256)), root)
    if any(item["canonical"]["rates"] != base for item in histories.values()):
        raise InputError("different central nuclear rates across the ensemble")
    weights = [n["weight"] for n in nodes]
    values = {f"{e}/{c}":[] for e in ("linx","primat") for c in CORNERS}
    seen = {}
    slots = {}
    for i, node in enumerate(nodes):
        draw = read_json(root/"nuclear_draws"/str(i)/"rates.json")
        verify_rates(draw["rates"], node["q"], root)
        for changed, central in zip(draw["rates"]["reactions"], base["reactions"], strict=True):
            if {k:v for k,v in changed.items() if k != "values"} != {k:v for k,v in central.items() if k != "values"}:
                raise InputError("perturbed nuclear table changed reaction metadata")
        if ([r["id"] for r in draw["rates"]["reactions"]] != spec["reaction_order"]
                or draw["reverse"] != histories[CORNERS[0]]["reverse_alpha_beta_gamma"]):
            raise InputError("nuclear ensemble changed reaction order or detailed balance")
        for c in CORNERS:
            item = with_rates(histories[c], draw["rates"], draw["reverse"])
            for e in ("linx","primat"):
                key = canonical_hash([e, item, tolerance])
                slots[f"{i}/{e}/{c}"] = key
                if key not in seen:
                    path = root/"nuclear_solves"/key
                    receipt, fingerprint = read_json(path/"receipt.json"), read_json(path/"input.json")
                    if (canonical_hash(fingerprint) != receipt["input_cache_key"]
                            or fingerprint["input"] != item or fingerprint["policy"] != tolerance
                            or receipt["engine"] != e or fingerprint["engine"] != e or receipt["history_reads"] <= 0
                            or receipt["nuclear_rates_sha256"] != bridge_hash(draw["rates"])
                            or sha256(path/"trajectory.npz") != receipt["files"]["trajectory.npz"]):
                        raise InputError("nuclear realization lacks a matching native consumption receipt")
                    with np.load(path/"trajectory.npz", allow_pickle=False) as raw:
                        y = raw["Y"]
                        if (raw["species"].tolist() != list(SPECIES) or not np.isfinite(y).all()
                                or y.shape != (len(item["canonical"]["history"]["time_s"]), 8)
                                or np.max(np.abs(y @ MASSES-1)) > 1e-6):
                            raise InputError("invalid nuclear realization trajectory")
                        seen[key] = [math.log10(y[-1,2]/y[-1,1]), 4*y[-1,5]]
                values[f"{e}/{c}"].append(seen[key])
    if slots != report["slots"] or len(seen) != report["unique_native_solves"]:
        raise InputError("nuclear covariance evidence has mismatched solver slots")
    matrices = {k:covariance(v, weights) for k,v in values.items()}
    for k,m in matrices.items():
        if not np.allclose(m, report["covariances"][k], rtol=1e-10, atol=1e-27):
            raise InputError("nuclear covariance differs from raw abundances")
    return matrices
