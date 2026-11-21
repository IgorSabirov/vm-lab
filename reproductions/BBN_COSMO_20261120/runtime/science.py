"""Frozen BBN integrations and Boltzmann propagation for issue 140."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
VENDOR = Path(os.environ["GITHUB_WORKSPACE"]) / "vendor"
SPECIES = ["n", "p", "d", "t", "He3", "a", "Li7", "Be7"]
MASSES = np.array([1, 1, 2, 3, 3, 4, 7, 7])
CHANNELS = ("ddHe3n", "ddtp")
WINDOWS = {"early": (0.2, 2.0, 0.003), "late": (0.02, 0.2, 0.0055)}


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def json_digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def native_primat():
    from primat.backend import run_bbn
    opts = {"network": "small", "Omegabh2": 0.02242, "DeltaNeff": 0.0,
            "verbose": False, "output_time_evolution": True, "output_background_evolution": True}
    res = run_bbn(opts, force_backend="python", progress=False)
    scalars = {k: float(res[k]) for k in ("DoH", "YPBBN", "YPCMB", "Neff", "He3oH", "Li7oH")}
    scalars["Y_final"] = {k: float(v) for k, v in res["Y_final"].items()}
    scalars["reference_pass"] = (abs(scalars["YPBBN"] - 0.24699896) <= 1e-5
                                 and abs(scalars["DoH"] - 2.4358605e-5) <= 3e-9
                                 and abs(scalars["Neff"] - 3.0439772986) <= 1e-5)
    dump(OUT / "PRIMAT_NATIVE.json", {"options": opts, **scalars})
    for key, value in res.items():
        if isinstance(value, dict):
            arrays = {k: np.asarray(v) for k, v in value.items()
                      if isinstance(v, (list, np.ndarray)) and np.asarray(v).dtype.kind in "fiu"}
            if arrays:
                np.savez_compressed(OUT / ("native_" + key + ".npz"), **arrays)
    return scalars


def yields(y, cfg):
    yp = 4 * y[5]
    he = cfg.He4Overma * yp / 4
    return dict(Yp=float(yp), YHe_CMB=float(he / (he + cfg.HOverma * (1 - yp))),
                D_H=float(y[2]/y[1]), He3_H_late=float((y[3]+y[4])/y[1]),
                Li7_H_late=float((y[6]+y[7])/y[1]))


class Pair:
    def __init__(self):
        import jax
        jax.config.update("jax_enable_x64", True)
        import jax.numpy as jnp
        from linx import const, thermo
        from linx.nuclear import NuclearRates
        from linx.abundances import AbundanceModel
        from linx.background import BackgroundModel
        from primat.config import PRIMATConfig
        from primat.network_data import UpdateNuclearRates
        self.jax, self.jp, self.c, self.th = jax, jnp, const, thermo
        self.cfg = PRIMATConfig({"network": "small", "verbose": False})
        self.pr = UpdateNuclearRates(self.cfg)
        self.net = NuclearRates(nuclear_net="key_PRIMAT_2023", interp_type="linear")
        self.model = AbundanceModel(self.net)
        self.bg_model = BackgroundModel(n_out=512)
        self.mapping = json.loads((ROOT / "NETWORK_MAP.json").read_text())
        self.rxmap = {r["linx_id"]: r for r in self.mapping["reactions"]}
        self.names = list(self.net.reactions_names)
        assert self.pr.species_LT == ["n","p","H2","H3","He3","He4","Li7","Be7"]
        assert self.pr._lt_net.names == ["n__p"] + [self.rxmap[n]["primat_id"] for n in self.names]
        self.backgrounds = {}
        self.rho0 = float(const.ma * const.n0CMB * const.eta0 * const.MeV4_to_gcmm3)

    def background(self, delta, window, amplitude):
        c, jp = self.c, self.jp
        if delta not in self.backgrounds:
            self.backgrounds[delta] = tuple(np.array(v) for v in self.bg_model(jp.asarray(delta)))
        t, a, rg, rn, rx, px, neff = self.backgrounds[delta]
        tg, tn = (np.asarray(f(jp.asarray(v))) for f, v in
                  ((self.th.T_g, rg), (self.th.T_nu, rn)))
        if window:
            low, high, h = WINDOWS[window]
            lo_t, hi_t = np.exp(np.interp(np.log([high, low]), np.log(tg[::-1]), np.log(t[::-1])))
            change = amplitude * h
            t = t - change / (1 + change) * np.clip(t - lo_t, 0, hi_t-lo_t)
        assert (np.diff(t)>0).all() and (np.diff(tg)<0).all()
        weak = self.model.weak_rates(jp.asarray([tg, tn]), T_start=c.T_start, T_end=c.T_end,
                                     sampling_nTOp=150, me=c.me, xi_nu=0.)
        tw, fw, bw = (np.array(v)[::-1] for v in weak)
        return t, a, rg, rn, rx, px, neff, tg, tn, tw, fw / float(c.tau_n), bw / float(c.tau_n)

    def case(self, name, channel=None, q=0., window=None, amplitude=1., delta=0., tight=False):
        c, jp = self.c, self.jp
        path = OUT / "cases" / name
        path.mkdir(parents=True, exist_ok=True)
        t,a,rg,rn,rx,px,neff,tg,tn,tw,fw,bw = self.background(delta, window, amplitude)
        nbase = self.rho0/a**3
        history = dict(time_s=t.tolist(), scale_factor=a.tolist(), H_s_inv=np.gradient(np.log(a),t).tolist(),
                       T_gamma_MeV=tg.tolist(), T_nu_MeV=tn.tolist(), n_b_cm3=(nbase/1.66053906660e-24).tolist())
        np.savez_compressed(path/"plasma.npz", rho_gamma_MeV4=rg, rho_one_nu_MeV4=rn,
                            rho_extra_MeV4=rx, p_extra_MeV4=px, Neff=neff,
                            weak_T_MeV=tw, n_to_p_s_inv=fw, p_to_n_s_inv=bw, rho_b_g_cm3=nbase)
        qvec = np.zeros(len(self.names))
        if channel:
            qvec[self.names.index(channel)] = q
        tables = self.net.precompute_rate_tables(jp.asarray(qvec))
        grids = [np.asarray(r.T9_vec) for r in self.net.reactions]
        tables_np = [np.asarray(v) for v in tables]
        coeff = np.array([[float(r.alpha),float(r.beta),float(r.gamma)] for r in self.net.reactions]).T
        reactions = []
        for i,n in enumerate(self.names):
            rm = self.rxmap[n]
            reactions.append(dict(id=n, reactants=rm["reactants"], products=rm["products"],
                                  T9=grids[i].tolist(), values=tables_np[i].tolist()))
        rates = dict(network_id="PRIMAT_SMALL_TO_LINX_KEY_PRIMAT_2023", species=SPECIES, reactions=reactions,
                     temperature_unit="T9", rate_units="cm3 mol-1 s-1 (forward two-body nuclear rates)",
                     interpolation="linear", extrapolation="upstream-zero-linear",
                     detailed_balance_policy="LINX alpha*T9**beta*exp(gamma/T9), both engines")
        doc = dict(schema_version="vm-lab-canonical-bbn-input-v1", history=history, rates=rates,
                   provenance=dict(history_sha256=json_digest(history), rates_sha256=json_digest(rates),
                                   producer="LINX pinned GitHub workflow and fixed clock control",
                                   created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        import jsonschema
        jsonschema.validate(doc, json.loads((ROOT/"BBN_HISTORY.schema.json").read_text()))
        from validate_contract import validate_input
        validate_input(doc)
        dump(path/"canonical.json", doc)
        np.savez_compressed(path/"rate_parameters.npz", reverse_alpha_beta_gamma=coeff, q=qvec,
                            **{r.name:np.asarray(r.expsigma_vec) for r in self.net.reactions})
        rt, at = (3e-9, 3e-13) if tight else (2e-8, 2e-12)
        solution = self.model(*map(jp.asarray,(rg,rn,rx,px)), a_vec=jp.asarray(a), t_vec=jp.asarray(t),
                              nuclear_rates_q=jp.asarray(qvec), sampling_nTOp=150,
                              max_steps=8192, rtol=rt, atol=at, save_history=True)
        start, end = float(solution.t0), float(solution.t1)
        times = np.geomspace(start,end,384)
        lin = np.asarray(self.jax.vmap(solution.evaluate)(jp.asarray(times))).T
        assert np.isfinite(lin).all()
        np.savez_compressed(path/"linx.npz", time_s=times,Y=lin, species=SPECIES)
        log_t,log_a,log_tg = np.log(t), np.log(a), np.log(tg)
        alpha,beta,gamma = coeff
        def args_at(u):
            logu = np.log(u)
            T = np.exp(np.interp(logu,log_t,log_tg))
            T9 = T / float(c.kB) * 1.e-9
            f = np.array([np.interp(T9,g,v,left=0.,right=0.) for g,v in zip(grids,tables_np)])
            b = alpha*T9**beta*np.exp(gamma/T9)*f
            rates_buf = np.empty(2+2*len(f))
            rates_buf[:2] = [np.interp(T, tw, fw), np.interp(T, tw, bw)]
            rates_buf[2::2],rates_buf[3::2] = f,b
            return self.rho0*np.exp(-3*np.interp(logu,log_t,log_a)), rates_buf
        kernel = self.pr._K_LT
        pr = solve_ivp(lambda u,y:kernel.rhs(y,*args_at(u)), (start,end), lin[0],
                       method="BDF", jac=lambda u,y:kernel.jacobian(y,*args_at(u)), t_eval=times,
                       rtol=rt, atol=at*0.01)
        if not pr.success or pr.t[-1] != end:
            raise RuntimeError(pr.message)
        p = pr.y.T
        np.savez_compressed(path/"primat.npz", time_s=times,Y=p, species=SPECIES)
        result = dict(linx=yields(lin[-1],self.cfg), primat=yields(p[-1],self.cfg), Neff=float(neff[-1]),
                      omega_b=float(c.Omegabh2), linx_steps=int(solution.stats["num_steps"]),
                      primat_nfev=pr.nfev, rtol=rt, atol_linx=at, atol_primat=at*0.01,
                      max_baryon_error=max(float(np.max(np.abs(x@MASSES-1))) for x in (lin,p)))
        assert np.isfinite(p).all() and min(p[-1])>=0 and min(lin[-1])>=0
        result["agreement"] = {k:result["primat"][k]/v-1 for k,v in result["linx"].items()}
        result["control_pass"] = (result["max_baryon_error"]<1.e-6 and abs(result["agreement"]["Yp"])<1.e-4
                                  and abs(result["agreement"]["D_H"])<1.e-3)
        dump(path/"observables.json", result)
        return result


def cosmology(name, yhe, neff, omega):
    p = OUT/"class"/name
    p.mkdir(parents=True, exist_ok=True)
    pars = dict(H0=67.4, omega_b=omega, omega_cdm=.120, N_ur=neff, N_ncdm=0, YHe=yhe,
                T_cmb=2.7255, tau_reio=.054, n_s=.965, A_s=2.1e-9, output="tCl,pCl",
                l_max_scalars=2500, root=str(p/"spectra_"), headers="yes", format="class",
                write_background="yes")
    (p/"parameters.ini").write_text("".join(f"{k.replace('write_background','write background')} = {v}\n" for k,v in pars.items()))
    with (p/"CLASS.log").open("w") as log:
        subprocess.run([str(VENDOR/"class"/"class"), str(p/"parameters.ini")],
                       cwd=VENDOR/"class", stdout=log, stderr=subprocess.STDOUT, check=True)
    spectra = np.loadtxt(next(p.glob("*cl.dat")))
    assert np.array_equal(spectra[:,0],np.arange(2,2501)) and np.isfinite(spectra).all()
    background = np.loadtxt(next(p.glob("*background.dat")))
    assert background.shape[0]>500 and np.isfinite(background).all()
    return dict(YHe=yhe, N_ur=neff, omega_b=omega, n_ell=len(spectra), n_background=len(background),
                TT_ell200=float(spectra[198,1]))


def dd_summary(cases):
    out = {}
    for channel in CHANNELS:
        for h in (0.25,0.125):
            pos,neg = (cases[f"{channel}_{s*h:+g}"] for s in (1,-1))
            out[f"{channel}_{h}"] = {engine:{k:float(np.log(pos[engine][k]/neg[engine][k])/(2*h))
                                               for k in ("Yp","D_H")} for engine in ("linx","primat")}
    return out
