#!/usr/bin/env python3
"""Autonomous seed-unfolding model; abstract particles, no hard-sphere collisions.

The target is used ONLY to set the first particle's initial internal state and
to compute diagnostics. It is not an argument of the evolution operator.
Run: python model.py --out RESULTS_DIR
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy
from scipy.linalg import eigvals, expm
from scipy.integrate import solve_ivp
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import expm_multiply


def ring(n):
    lap = 2 * np.eye(n) - np.roll(np.eye(n), 1, axis=0) - np.roll(np.eye(n), -1, axis=0)
    return lap


def build(n=8, kind="full", lap=None, eta=1.5):
    d = 2
    m = d * n if kind == "full" else 5
    lap = ring(n) if lap is None else lap
    lq, lc = np.kron(lap, np.eye(d)), np.kron(lap, np.eye(m))
    nq, nc = n * d, n * m
    alpha, beta, kappa, gamma = 3.0, 0.4, 4.0, 2.0
    r = alpha * np.eye(nq) + beta * lq
    b = np.zeros((nq, nc))
    for i in range(n):
        if kind == "full":
            bi = np.zeros((d, m))
            bi[:, d*i:d*i+d] = np.eye(d)
        else:
            theta = 2 * np.pi * i / n
            u = np.array([np.cos(theta), np.sin(theta)])
            bi = np.column_stack([np.eye(2), u, np.cos(2*theta)*u, np.sin(2*theta)*u])
        b[d*i:d*i+d, m*i:m*i+m] = bi
    hcc = b.T @ r @ b + kappa * lc
    matrix = np.block([
        [np.zeros((nq, nq)), np.eye(nq), np.zeros((nq, nc))],
        [-r, -gamma*np.eye(nq), r @ b],
        [eta*lc @ b.T @ r, np.zeros((nc, nq)), -eta*lc @ hcc],
    ])
    hessian = np.block([
        [r, np.zeros((nq,nq)), -r @ b],
        [np.zeros((nq,nq)), np.eye(nq), np.zeros((nq,nc))],
        [-b.T @ r, np.zeros((nc,nq)), hcc],
    ])
    mu_op = np.column_stack([-b.T @ r, np.zeros((nc,nq)), hcc])
    dissipation = eta * mu_op.T @ lc @ mu_op
    dissipation[nq:2*nq,nq:2*nq] += gamma * np.eye(nq)
    mean_op = np.zeros((m, 2*nq+nc))
    mean_op[:,2*nq:] = np.kron(np.ones((1,n))/n, np.eye(m))
    return dict(n=n, d=d, m=m, nq=nq, nc=nc, L=lap, Lc=lc, B=b,
                R=r, M=matrix, H=hessian, D=dissipation, C=mean_op,
                parameters=dict(alpha=alpha,beta=beta,kappa=kappa,gamma=gamma,eta=eta), kind=kind)


def initial(model, seed, distribution="first", kick=True):
    n, d, m = model["n"], model["d"], model["m"]
    q = np.column_stack([np.arange(n) % 4, np.arange(n) // 4]).astype(float)
    q -= q.mean(axis=0)
    v = np.zeros((n,d))
    if kick:
        v[0] = [0.4,0.1]
    c = np.zeros((n,m))
    if distribution == "first":
        c[0] = n * seed
    elif distribution == "uniform":
        c[:] = seed
    else:
        raise ValueError(distribution)
    return np.r_[q.ravel(),v.ravel(),c.ravel()]


def predicted_equilibrium(model, seed):
    code = np.tile(seed, model["n"])
    return np.r_[model["B"] @ code, np.zeros(model["nq"]), code]


def main(out):
    wall_start = time.perf_counter()
    out.mkdir(parents=True,exist_ok=True)
    model = build()
    n, nq = model["n"], model["nq"]
    # Sixteen independent target coordinates, held only by particle 1 initially.
    target = np.array([[-2.,-1.],[-.7,-1.4],[.8,-1.2],[2.1,-.5],
                       [1.8,1.3],[.4,1.8],[-1.2,1.5],[-2.1,.2]])
    seed = target.ravel()
    z0 = initial(model,seed)
    zstar = predicted_equilibrium(model,seed)
    ts = np.linspace(0,100,201)
    trajectory = expm_multiply(csr_matrix(model["M"]),z0,start=0,stop=ts[-1],num=len(ts))
    energy = 0.5*np.einsum("ti,ij,tj->t",trajectory,model["H"],trajectory)
    qerr = np.max(np.abs(trajectory[:,:nq]-zstar[:nq]),axis=1)
    allerr = np.max(np.abs(trajectory-zstar),axis=1)
    avgerr = np.max(np.abs(trajectory @ model["C"].T-seed),axis=1)
    codeerr = np.max(np.abs(trajectory[:,2*nq:]-np.tile(seed,n)),axis=1)
    evalues = eigvals(model["M"])
    nonzero = evalues[np.abs(evalues)>1e-8]
    exact_end = expm(model["M"]*ts[-1]) @ z0
    # Independent ODE integration checks a shorter trajectory against exp(Mt).
    sol = solve_ivp(lambda t,z:model["M"]@z,[0,10],z0,method="DOP853",rtol=1e-10,atol=1e-12)
    independent_error = np.max(np.abs(sol.y[:,-1]-expm(model["M"]*10)@z0))
    uniform_end = expm(model["M"]*ts[-1]) @ initial(model,seed,"uniform")
    nokick_end = expm(model["M"]*ts[-1]) @ initial(model,seed,kick=False)
    altered = seed.copy(); altered[6] += 0.25
    altered_end = expm(model["M"]*ts[-1]) @ initial(model,altered)
    off = build(eta=0.0)
    off_end = expm(off["M"]*ts[-1]) @ initial(off,seed)
    split_lap = scipy.linalg.block_diag(ring(n//2),ring(n//2))
    split = build(lap=split_lap)
    split_end = expm(split["M"]*ts[-1]) @ initial(split,seed)
    component_code = np.vstack([np.tile(2*seed,(n//2,1)),np.zeros((n//2,len(seed)))])
    split_star = np.r_[split["B"]@component_code.ravel(),np.zeros(nq),component_code.ravel()]
    compact = build(n=12,kind="compressed")
    compact_seed = np.array([.2,-.1,2.,.35,-.2])
    compact_star = predicted_equilibrium(compact,compact_seed)
    compact_end = expm(compact["M"]*150) @ initial(compact,compact_seed)
    algebra = dict(
        mean_invariance_residual=float(np.max(np.abs(model["C"]@model["M"]))),
        energy_identity_residual=float(np.max(np.abs(model["M"].T@model["H"]+model["H"]@model["M"]+2*model["D"]))),
        equilibrium_residual=float(np.max(np.abs(model["M"]@zstar))),
    )
    metrics = dict(
        model="autonomous_seed_unfolding_v1", scope="abstract graph-coupled particles; no hard-sphere impacts",
        parameters=model["parameters"],particles=n,position_dimension=2,code_dimension_per_particle=len(seed),
        state_dimension=len(z0),horizon=float(ts[-1]),time_units="dimensionless",
        seed=seed.tolist(),first_internal_state=(n*seed).tolist(),
        final_position_max_abs_error=float(qerr[-1]),final_full_state_max_abs_error=float(allerr[-1]),
        maximum_mean_code_error=float(avgerr.max()),final_velocity_max_abs=float(np.max(abs(trajectory[-1,nq:2*nq]))),
        maximum_sampled_energy_increase=float(np.max(np.diff(energy))),initial_energy=float(energy[0]),final_energy=float(energy[-1]),
        zero_eigenvalues=int(np.sum(np.abs(evalues)<1e-8)),largest_nonzero_eigenvalue_real_part=float(nonzero.real.max()),
        independent_ode_success=bool(sol.success),independent_ode_vs_matrix_error=float(independent_error),
        expm_multiply_vs_expm_final_error=float(np.max(abs(trajectory[-1]-exact_end))),
        same_mean_different_distribution_final_error=float(np.max(abs(uniform_end-zstar))),
        zero_mechanical_kick_final_error=float(np.max(abs(nokick_end-zstar))),
        changed_seed_predicted_equilibrium_error=float(np.max(abs(altered_end-predicted_equilibrium(model,altered)))),
        changed_seed_max_final_coordinate_difference=float(np.max(abs(altered_end[:nq]-trajectory[-1,:nq]))),
        disabled_exchange_target_error=float(np.max(abs(off_end[:nq]-zstar[:nq]))),
        disconnected_graph_component_prediction_error=float(np.max(abs(split_end-split_star))),
        disconnected_graph_global_target_error=float(np.max(abs(split_end[:nq]-zstar[:nq]))),
        compressed_example=dict(particles=12,code_dimension=5,horizon=150,seed=compact_seed.tolist(),
                                final_max_error=float(np.max(abs(compact_end-compact_star)))),
        algebra=algebra,
        environment=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,platform=platform.platform(),
                         dtype="float64",executable=sys.executable,
                         threads={k:os.environ.get(k) for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"]}),
    )
    checks = dict(
        equilibrium_reached=allerr[-1]<1e-7,
        mean_code_conserved=avgerr.max()<1e-8,
        energy_nonincreasing=np.max(np.diff(energy))<1e-8,
        algebra_identities=max(algebra.values())<1e-8,
        neutral_modes_match_conserved_code=np.sum(np.abs(evalues)<1e-8)==len(seed),
        transverse_modes_stable=nonzero.real.max()<-1e-6,
        independent_numerics=sol.success and independent_error<1e-7,
        redistributing_same_code_preserves_limit=np.max(abs(uniform_end-zstar))<1e-7,
        mechanical_kick_does_not_encode_target=np.max(abs(nokick_end-zstar))<1e-7,
        seed_change_selects_new_target=np.max(abs(altered_end-predicted_equilibrium(model,altered)))<1e-7,
        no_exchange_loses_global_target=np.max(abs(off_end[:nq]-zstar[:nq]))>1,
        disconnected_graph_matches_component_means=np.max(abs(split_end-split_star))<1e-7,
        compressed_example_matches_prediction=np.max(abs(compact_end-compact_star))<1e-7,
    )
    checks={k:bool(v) for k,v in checks.items()}
    if not all(checks.values()):
        raise RuntimeError(json.dumps(checks,indent=2))
    with (out/"final_configuration.csv").open("w",newline="") as f:
        w=csv.writer(f);w.writerow(["particle","x_initial","y_initial","x_final","y_final","x_expected","y_expected"])
        for i in range(n):w.writerow([i+1,*z0[2*i:2*i+2],*trajectory[-1,2*i:2*i+2],*target[i]])
    np.savez_compressed(out/"trajectory.npz",time=ts,state=trajectory,energy=energy,seed=seed,matrix=model["M"],decoder=model["B"])
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout="constrained")
    colors=plt.get_cmap("tab10")(np.arange(n))
    for i in range(n):
        xy=trajectory[:,2*i:2*i+2]
        axs[0].plot(xy[:,0],xy[:,1],color=colors[i],alpha=.75,lw=1.4)
        axs[0].scatter(*xy[0],marker="s",s=28,color=colors[i])
        axs[0].scatter(*xy[-1],s=65,color=colors[i],edgecolor="white",zorder=3)
        axs[0].annotate(str(i+1),xy[-1],xytext=(5,5),textcoords="offset points")
    axs[0].scatter(target[:,0],target[:,1],s=120,facecolors="none",edgecolors="black",linewidths=.8,label="Analytical limit")
    axs[0].set(title="Abstract particle trajectories",xlabel="x",ylabel="y",aspect="equal")
    axs[0].legend(fontsize=8);axs[0].grid(alpha=.2)
    axs[1].semilogy(ts,np.maximum(qerr,1e-15),label="Position error")
    axs[1].semilogy(ts,np.maximum(codeerr,1e-15),label="Internal-code disagreement")
    axs[1].semilogy(ts,np.maximum(avgerr,1e-15),label="Conserved-mean numerical error")
    axs[1].set(title="Convergence and conserved code",xlabel="Dimensionless time",ylabel="Maximum absolute error")
    axs[1].grid(alpha=.2);axs[1].legend(fontsize=8)
    fig.suptitle("One initial payload, autonomous coupled dynamics — mathematical toy model",fontsize=12)
    fig.savefig(out/"diagnostics.png",dpi=160)
    plt.close(fig)
    metrics["wall_seconds"]=time.perf_counter()-wall_start
    (out/"metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+"\n")
    (out/"checks.json").write_text(json.dumps(checks,indent=2)+"\n")
    print(json.dumps({"checks":checks,"position_error":metrics["final_position_max_abs_error"],
                      "code_conservation_error":metrics["maximum_mean_code_error"],
                      "wall_seconds":metrics["wall_seconds"]},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--out",type=Path,default=Path("results"))
    main(parser.parse_args().out)
