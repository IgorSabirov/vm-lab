"""Mathematical, saved-matrix and cache-resolver checks; no physical solver run.

External inputs are read at the frozen sources in SOURCES.json. Only three
pure file-path resolver functions are extracted from PRIMAT, not its imports,
weak-rate integrators, C backend or BBN engine. No network or RNG is used.
"""
import argparse
import ast
import hashlib
import json
import math
import os
import platform
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def nonlinear_checks():
    m = np.array([0., math.log(2.)])
    slopes = np.array([.1, .3])
    weights = np.array([.5, .5])
    def mid(q):
        return np.logaddexp(m[0]+slopes[0]*q, m[1]+slopes[1]*q)-math.log(2.)
    def grad(q):
        a = np.log(weights)+m+slopes*q
        p = np.exp(a-np.max(a)); p /= p.sum()
        return p@slopes
    rows = []
    # Independent quadrature orders check integration convergence.
    for sigma in (.3, 1., 3.):
        previous = None
        for n in (100, 200):
            q, wt = np.polynomial.hermite_e.hermegauss(n)
            q *= sigma; wt /= wt.sum()
            values = np.column_stack((slopes[0]*q, mid(q)))
            centered = values-wt@values
            cov = centered.T@(wt[:,None]*centered)
            if previous is not None:
                assert np.allclose(cov, previous, atol=2e-14, rtol=2e-12)
            previous = cov
        ev = np.linalg.eigvalsh(cov)
        assert ev[0] > 0 and np.linalg.matrix_rank(cov) == 2
        q_rec = values[:,0]/slopes[0]
        residual = float(np.max(np.abs(values[:,1]-mid(q_rec))))
        assert residual < 2e-13
        ranks = [int(np.linalg.matrix_rank(np.array([[slopes[0]],[grad(z)]]))) for z in (-2.,0.,2.)]
        assert ranks == [1,1,1]
        rows.append(dict(sigma=sigma,covariance=cov.tolist(),eigenvalues=ev.tolist(),covariance_numerical_rank=2,
                         jacobian_ranks_at_minus2_0_2=ranks,reconstruction_max_residual=residual))
    p=weights*np.exp(m);p/=p.sum()
    hessian=float(p@(slopes*slopes)-(p@slopes)**2)
    fd=(grad(1e-4)-grad(-1e-4))/2e-4
    assert math.isclose(hessian,fd,abs_tol=2e-11)
    assert math.isclose(hessian, .00888888888888889,rel_tol=1e-12)
    # Same physical grid/evaluation temperature, two interpolation conventions.
    T=np.array([1.,4.]); t=2.5
    alpha=(math.log(t)-math.log(T[0]))/(math.log(T[1])-math.log(T[0]))
    log_weights=np.array([1-alpha,alpha])
    log_slope=float(log_weights@slopes)
    affine_cov=np.outer([slopes[0],log_slope],[slopes[0],log_slope])
    assert np.linalg.matrix_rank(affine_cov)==1
    # Redundant inputs and a singular point disprove a universal rank(J)==r.
    assert np.linalg.matrix_rank([[1.,1.]])==1
    assert np.linalg.matrix_rank([[0.]])==0  # derivative of q^3 at zero
    assert np.linalg.matrix_rank([[3.]])==1
    return dict(rows=rows,quadrature_orders=[100,200],grid_T9=T.tolist(),evaluation_T9=t,
                linear_rate_hessian_q0=hessian,finite_difference_of_gradient=fd,
                log_interpolation_covariance_rank=1,
                latent_vs_active_examples={'q1_plus_q2':{'inputs':2,'active_rank':1},'q_cubed':{'rank_at_zero':0,'rank_at_regular_nonzero':1}},
                scope='Conditional mathematical model of tabular formulas, not execution of LINX or fit of a reaction posterior.')


def scaling_checks():
    C=np.array([[2.,.3],[.3,1.]])
    W=np.array([[1.,2.],[3.,-1.],[.5,.25]])
    D=np.diag([10.,.2]);Cp=D@C@D.T;Wp=W@np.linalg.inv(D)
    original=W@C@W.T;consistent=Wp@Cp@Wp.T
    delta=float(np.max(np.abs(original-consistent)))
    assert np.allclose(original,consistent,rtol=1e-13,atol=1e-13)
    assert not np.allclose(W@Cp@W.T,original)
    # Exactly rank two under invertible rescaling, but tolerance rank changes.
    tiny=np.diag([1.,1e-18])
    numeric=int(np.linalg.matrix_rank(tiny))
    assert numeric==1
    return dict(input_change_max_residual=delta,unchanged_W_changes_physical_output=True,
                exact_rank_diagonal_1_1e_minus18=2,numerical_rank=numeric,
                numpy_default_relative_rank_threshold=2*np.finfo(float).eps,
                scope='Explicit synthetic matrices, not Leonard, S-factor conversion or measured BBN information loss.')


def leonard_checks(path, sources):
    expected=sources['LEONARD_INPUT']['sha256'];assert digest(path)==expected
    d=json.loads(Path(path).read_text());C=np.asarray(d['covariance_a0'],dtype=float)
    assert C.shape==(16,16) and np.allclose(C,C.T,rtol=0,atol=1e-15)
    ev=np.linalg.eigvalsh(C);assert ev[0]>0
    rank=int(np.linalg.matrix_rank(C));assert rank==16
    return dict(input_sha256=expected,source_url=sources['LEONARD_INPUT']['url'],shape=[16,16],
                numerical_rank=rank,numpy_default_relative_rank_threshold=16*np.finfo(float).eps,
                eigenvalue_min=float(ev[0]),eigenvalue_max=float(ev[-1]),condition_number=float(np.linalg.cond(C)),
                representation='a0 (mb/sr); p eight energies then n eight',
                full_rate_posterior_reconstructed=False,physical_W_constructed=False,bbn_propagation_performed=False)


def resolver_checks(path, sources):
    expected=sources['PRIMAT_CACHE_RESOLVER']['sha256'];assert digest(path)==expected
    tree=ast.parse(Path(path).read_text())
    names={'_cache_bases','cache_write_dir','resolve_cache_file'}
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes}==names
    namespace={'os':os}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    resolve=namespace['resolve_cache_file']
    rows=[]
    with tempfile.TemporaryDirectory(prefix='integration-cache-paths-') as tmp:
        root=Path(tmp);data=root/'data';isolated=root/'isolated';overlay=root/'overlay'
        for base in [data/'cache_plasma_weak',isolated/'cache_plasma_weak',overlay]:
            (base/'weak').mkdir(parents=True)
        for filename in ['nTOp_example.txt','nTOp_thermal_example.txt']:
            original=data/'cache_plasma_weak'/'weak'/filename;original.write_text('synthetic original')
            a=resolve(SimpleNamespace(resolved_data_dir=str(data),cache_dir=str(overlay)),'weak',filename)
            assert Path(a)==original
            b=resolve(SimpleNamespace(resolved_data_dir=str(isolated),cache_dir=None),'weak',filename)
            assert not Path(b).exists()
            external=overlay/'weak'/filename;external.write_text('synthetic overlay')
            c=resolve(SimpleNamespace(resolved_data_dir=str(isolated),cache_dir=str(overlay)),'weak',filename)
            assert Path(c)==external
            external.unlink()
            rows.append(dict(filename=filename,empty_overlay_falls_back=True,isolated_no_overlay_misses=True,populated_overlay_wins=True))
    return dict(input_sha256=expected,functions=sorted(names),cases=rows,
                actual_weak_fingerprint_computed=False,weak_rate_integrators_run=False,c_backend_run=False,
                scope='Exact pinned Python resolver functions, synthetic filenames and contents; no full data tree or physical weak/BBN run.')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--leonard-input',required=True);ap.add_argument('--cache-utils',required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();t=time.perf_counter()
    sources=json.loads(Path(__file__).with_name('SOURCES.json').read_text())['sources']
    result=dict(schema='vm-lab-integration-followup-checks-v1',status='PASS',mode='MATHEMATICS_SAVED_MATRIX_AND_FILE_RESOLVER_ONLY',
                physical_solver_runs=0,LINX_executed=False,PRIMAT_BBN_executed=False,HNL_computed=False,
                nonlinear_rates=nonlinear_checks(),coordinate_scaling=scaling_checks(),
                leonard=leonard_checks(args.leonard_input,sources),cache_resolver=resolver_checks(args.cache_utils,sources),
                environment={'python':platform.python_version(),'numpy':np.__version__,'platform':platform.platform()},
                code_sha256=digest(__file__),elapsed_seconds=time.perf_counter()-t)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'groups':['nonlinear_rates','coordinate_scaling','leonard','cache_resolver'],
                      'elapsed_seconds':result['elapsed_seconds'],'physical_solver_runs':0}))

if __name__=='__main__':main()
