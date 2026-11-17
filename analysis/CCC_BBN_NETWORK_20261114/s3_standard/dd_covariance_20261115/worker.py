"""One bounded LINX BBN realization for the preregistered D+D response."""
import argparse
from pathlib import Path
import hashlib, importlib.metadata, json, math, os, resource, sys, time

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "infra/autonomy/admit.py").is_file())
ADAPTER = ROOT / "analysis/CCC_BBN_NETWORK_20261114/s3_standard/linx_dd_adapter_20261115"
CONTRACT = json.loads((HERE / "CONTRACT.json").read_text())

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=["baseline", "perturb"], required=True)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--admission", type=Path, required=True)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--background", type=Path)
    ap.add_argument("--background-sha256")
    ap.add_argument("--channel", choices=["ddHe3n", "ddtp"])
    ap.add_argument("--q", type=float)
    a = ap.parse_args()
    admission = json.loads(a.admission.read_text())
    if admission.get("admitted") is not True or admission.get("source_sha") != a.source_sha:
        raise ValueError("Fresh package admission/source mismatch")
    if admission.get("scientific_acceptance") is not False:
        raise ValueError("Scientific acceptance must remain false")
    if a.role == "baseline" and (a.channel is not None or a.q is not None or a.background is not None):
        raise ValueError("Baseline must be native q=0 and create its background")
    if a.role == "perturb" and (a.channel is None or a.q not in (-1.0, -0.5, 0.5, 1.0) or a.background is None):
        raise ValueError("Perturbation arguments are not preregistered")
    a.out.mkdir(parents=True, exist_ok=False)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    os.environ.update(JAX_ENABLE_X64="true", JAX_PLATFORMS="cpu",
                      OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    sys.path.insert(0, str(a.root.resolve()))
    sys.path.insert(0, str(ADAPTER.resolve()))

    import jax
    jax.config.update("jax_enable_x64", True)
    import jax.numpy as jnp
    import numpy as np
    from diffrax import Kvaerno3, Tsit5
    from linx.nuclear import NuclearRates
    from linx.abundances import AbundanceModel
    from linx.background import BackgroundModel
    from linx import const

    start, cpu_start = time.perf_counter(), time.process_time()
    b = dict(Delta_Neff_init=0.0, n_out=512, max_steps=512, decoupled=False,
             use_FD=True, collision_me=True, LO=True, NLO=True, rtol=1e-8, atol=1e-10)
    n = dict(T_start_K=1e11, T_end_K=6e7, eta_fac=1.0, tau_n_fac=1.0,
             xi_nu=0.0, sampling_nTOp=150, rtol=1e-6, atol=1e-9,
             max_steps=4096, save_history=True)
    if not math.isclose(const.T_start/const.kB, n["T_start_K"], rel_tol=2e-15):
        raise ValueError("Pinned LINX start temperature mismatch")
    if not math.isclose(const.T_end/const.kB, n["T_end_K"], rel_tol=2e-15):
        raise ValueError("Pinned LINX end temperature mismatch")
    versions = {k: importlib.metadata.version(k) for k in
                ("jax", "jaxlib", "equinox", "diffrax", "interpax", "numpy", "scipy")}
    lock = {x.split("==")[0]: x.split("==")[1] for x in
            (ADAPTER/"requirements.lock").read_text().splitlines() if "==" in x}
    if any(versions[k] != lock[k] for k in versions):
        raise ValueError("Numerical environment differs from pinned lock")

    names_expected = ("npdg","dpHe3g","ddHe3n","ddtp","tpag","tdan","taLi7g",
                      "He3ntp","He3dap","He3aBe7g","Be7nLi7p","Li7paa")
    net = NuclearRates(nuclear_net="key_PRIMAT_2023", interp_type="linear")
    if tuple(net.reactions_names) != names_expected:
        raise ValueError("Pinned reaction order changed")
    qvec = jnp.zeros(len(net.reactions), dtype=jnp.float64)
    model = AbundanceModel(net)

    if a.role == "baseline":
        bg = BackgroundModel(**{k:b[k] for k in ("n_out","max_steps","decoupled","use_FD","collision_me","LO","NLO")})(
            jnp.asarray(0.0), solver=Tsit5(), rtol=b["rtol"], atol=b["atol"])
        jax.block_until_ready(bg)
        background = a.out/"background.npz"
        np.savez(background, **{k:np.asarray(v) for k,v in zip(
            ("t","a","rho_g","rho_nu","rho_extra","p_extra","Neff"), bg)})
    else:
        if digest(a.background) != a.background_sha256:
            raise ValueError("Shared background SHA256 mismatch")
        background = a.background

    with np.load(background, allow_pickle=False) as z:
        bgv = {k:jnp.asarray(z[k]) for k in z.files}
    kw = dict(a_vec=bgv["a"], t_vec=bgv["t"], solver=Kvaerno3(),
              eta_fac=jnp.asarray(n["eta_fac"]), tau_n_fac=jnp.asarray(n["tau_n_fac"]),
              xi_nu=jnp.asarray(n["xi_nu"]), sampling_nTOp=n["sampling_nTOp"],
              rtol=n["rtol"], atol=n["atol"], max_steps=n["max_steps"],
              save_history=n["save_history"], nuclear_rates_q=qvec)
    rhs = (bgv["rho_g"], bgv["rho_nu"], bgv["rho_extra"], bgv["p_extra"])
    perturbation = None
    if a.role == "baseline":
        sol = model(*rhs, **kw)
    else:
        from dd_adapter import DDTable, UNITS, prepare_dd_tables, solve_with_dd
        replacements = {}
        for channel in CONTRACT["rate_model"]["channels"]:
            rxn = net.reactions[net.reactions_names.index(channel)]
            nodes = np.asarray(rxn.T9_vec, dtype=np.float64)
            median = np.asarray(rxn.mu_median_vec, dtype=np.float64)
            factor = np.asarray(rxn.expsigma_vec, dtype=np.float64)
            q = float(a.q) if channel == a.channel else 0.0
            values = median * np.exp(q * np.log(factor))
            replacements[channel] = DDTable(nodes, values.astype(np.float64), "linear", UNITS)
        native = tuple(net.precompute_rate_tables(qvec))
        prepared = prepare_dd_tables(net, replacements, qvec,
                    temperature_bounds_K=(n["T_end_K"], n["T_start_K"]),
                    boundary_policy="upstream-zero-linear")
        unchanged = all(np.asarray(native[i]).tobytes() == np.asarray(prepared.tables[i]).tobytes()
                        for i,name in enumerate(net.reactions_names)
                        if name not in CONTRACT["rate_model"]["channels"])
        if not unchanged:
            raise ValueError("A non-D+D native table changed")
        perturbation = {
            "channel": a.channel, "q": float(a.q), "other_reactions_q": "ALL_ZERO",
            "other_native_tables_unchanged": True,
            "rate_table_sha256": {k:hashlib.sha256(np.asarray(v.values,dtype="<f8").tobytes()).hexdigest()
                                  for k,v in replacements.items()}
        }
        adapter_kw = {k:v for k,v in kw.items() if k != "nuclear_rates_q"}
        sol = solve_with_dd(model, *rhs, replacements=replacements, nuclear_rates_q=qvec,
                 boundary_policy="upstream-zero-linear", **adapter_kw)

    jax.block_until_ready(sol)
    final = np.asarray(sol.evaluate(sol.t1), dtype=np.float64)
    initial = np.asarray(sol.evaluate(sol.t0), dtype=np.float64)
    if final.shape != (8,) or initial.shape != (8,) or not np.all(np.isfinite(final)) or np.any(final <= 0):
        raise ValueError("Invalid eight-species BBN output")
    yn, yh, yd, yt, yhe3, yhe4, yli7, ybe7 = map(float, final)
    observables = {"D_H":yd/yh, "Yp":4*yhe4,
                   "He3_H_late":(yhe3+yt)/yh, "Li7_H_late":(yli7+ybe7)/yh}
    if any(not math.isfinite(v) or v <= 0 for v in observables.values()):
        raise ValueError("Invalid derived BBN observable")
    result = {
        "role":a.role, "source_sha":a.source_sha,
        "contract_sha256":digest(HERE/"CONTRACT.json"), "background_sha256":digest(background),
        "upstream_root":a.root.name, "upstream_commit":CONTRACT["source"]["upstream_commit"],
        "network":"key_PRIMAT_2023", "reaction_order":list(net.reactions_names),
        "q_other_reactions":0.0, "perturbation":perturbation,
        "initial":initial.tolist(), "final":final.tolist(), "observables":observables,
        "solver_stats":{k:int(v) for k,v in sol.stats.items()}, "versions":versions,
        "wall_seconds":time.perf_counter()-start, "cpu_seconds":time.process_time()-cpu_start,
        "peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "scientific_acceptance":False
    }
    (a.out/"RESULT.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")

if __name__ == "__main__":
    main()
