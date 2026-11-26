"""Port symmetries and measurement operators plus a calibrated analytic BBN control."""
from fractions import Fraction
from pathlib import Path
import json
import math
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import local_chi
from word_rule import F_word, I_word, T_word, canon_cycle, state_to_word, word_to_state


def check_layer(length, active):
    u, v = ((length + 1) // 2, (length - 1) // 2) if active else (0, 0)
    words = [state_to_word((t, u, (t + v) % length), length) for t in range(length)]
    assert all(local_chi(w) == 0 for w in words) and (u + v) % length == 0
    eye = np.eye(length)
    def matrix(rule):
        cols = []
        for w in words:
            target = rule(w)
            t, new_u, last = word_to_state(target)
            assert len(target) == length and (new_u, (last-t) % length) == (u,v)
            cols.append(t)
        assert len(set(cols)) == length
        return eye[:,cols]
    step, refl = matrix(F_word), matrix(T_word)
    order = [0] + list(range(2,length)) if active else list(range(length))
    n = len(order)
    for j,t in enumerate(order):
        assert step[order[(j+1) % n], t] == 1
    assert np.array_equal(refl @ step @ refl, step.T)
    fixed = list(np.flatnonzero(np.diag(refl)).astype(int).tolist())
    assert fixed == ([0, 1, (length+1)//2] if active else [0])
    # A sign on the closing edge implements exactly pi, with no residual sin(pi).
    twist = step.copy()
    twist[order[0],order[-1]] = -1
    def counts(op):
        return [length - int(np.linalg.matrix_rank(op-s*eye)) for s in (1,-1)]
    assert counts(step) == ([2,1] if active else [1,0])
    assert counts(twist) == ([1,0] if active else [0,1])
    # The reflecting operator in the signed gauge fixes e_0 and reverses cycle powers.
    signed = refl.copy()
    signed[:, order[1:]] *= -1
    assert np.array_equal(signed @ twist @ signed, twist.T)
    assert np.array_equal(signed @ signed, eye)
    indicator = np.array([int(canon_cycle(I_word(w))!=canon_cycle(w)) for w in words])
    assert list(np.flatnonzero(indicator)) == ([0,1] if active else [])
    out = dict(uv=[u,v], fixed_T=fixed, untwisted=counts(step), pi_seam=counts(twist),
               trace_dressed_T_at_pi=int(signed.trace()), long_orbit_C=str(Fraction(int(sum(indicator[order])),n)))
    if active:
        e = eye[:,1]
        even = eye[:,order].sum(axis=1)/math.sqrt(n)
        alternating = eye[:,order] @ (-1.)**np.arange(n)/math.sqrt(n)
        V = np.column_stack((e,even,alternating))
        contact = np.diag(indicator)
        projection = V.T @ contact @ V
        Cbar = np.diag([1.,1./n,1./n])
        reduced = V.T @ step @ V
        assert np.allclose(reduced,np.diag([1,1,-1]))
        # On this three-mode space F^2=1, so two conjugates implement period averaging.
        assert np.allclose((projection+reduced.T@projection@reduced)/2, Cbar)
        design = np.column_stack((np.ones(3),np.diag(Cbar),np.diag(reduced)))
        assert np.isclose(np.linalg.det(design),2*(1-1/n))
        target = np.array([1.,2.,4.])
        couplings = np.linalg.solve(design,target)
        assert np.allclose(design@couplings,target)
        out.update(fixed_orbit_C=int(indicator[1]),mass_design_det=str(2*(1-Fraction(1,n))))
    return out


def helium():
    target, sigma, old_sigma = .2467,.0013,.0033
    dm, temp, life, g = 1.2933,.8,878.4,10.75
    x = dm/temp
    r = target/(2-target)
    t = -life * (math.log(r)+x)
    y = t/life
    prefactor = 2*r/(1+r)**2
    decay, full = prefactor*y, prefactor*(x/3+y)
    def abundance(factor=1., dspecies=0., weak=True):
        relative_g = (g+1.75*dspecies)/g
        relative_T = (factor**(1/3) if weak else 1.) * relative_g**(1/6)
        ratio = math.exp(-x/relative_T-y*relative_g**(-.5)/factor)
        return 2*ratio/(1+ratio)
    h = .001
    slope = (abundance(1+h/life)-abundance(1-h/life))/(2*h)
    assert math.isclose(slope,full/life,rel_tol=1e-8)
    additive = prefactor*(x/6+y/2)*1.75/g
    secant = (abundance(dspecies=1)-abundance(dspecies=-1))/2
    h2 = 1e-4
    assert math.isclose((abundance(dspecies=h2)-abundance(dspecies=-h2))/(2*h2), additive,rel_tol=1e-8)
    assert math.isclose(abundance(),target)
    drift=1.542610941775518e-15
    # Local response from Yeh, Olive & Fields (2023), equations (13)-(14).
    network_jacobian = np.array([[.730,.163/3],[.413,.405/3]])
    return dict(network_fit=dict(dY_dtau=target*.730/life,dY_dN=target*.163/3,
                                 sigmaN_helium_only=sigma/(target*.163/3),
                                 log_Yp_DH_by_log_tau_and_delta_N=network_jacobian.tolist(),
                                 determinant=float(np.linalg.det(network_jacobian))),
                calibrated_dt=t,r=r,dY_dlnr=prefactor,decay_only=decay,full=full,
                dY_dtau=slope,dY_dN_local=additive,dY_dN_secant=secant,
                sigmaN_local=sigma/additive,sigmaN_secant=sigma/secant,
                small_positive_drift_dY=[drift*decay,drift*full],
                lifetime_controls={str(f):{'both':abundance(f),'decay_only':abundance(f,weak=False)}
                                   for f in (3.66,1/3.66)},
                laboratory_offsets={str(s):{'linear':s*slope,'exact':abundance(1+s/life)-target}
                                    for s in (8.7,10)},
                independent_error_pull=(target-.2458)/math.hypot(sigma,.0002),
                sigma_ratio=old_sigma/sigma,tolerance_to_drift=(1e-12/(2*math.pi))/drift)


if __name__ == '__main__':
    print(json.dumps(dict(layers={L:{key:check_layer(L,on) for key,on in [('A',False),('B',True)]}
                                 for L in (3,5,7,9,11,15,17,25,33)}, helium=helium()),indent=2))
