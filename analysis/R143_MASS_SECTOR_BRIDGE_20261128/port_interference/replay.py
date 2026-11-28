"""Reproduce finite-model port predictions and their controls with Python 3 and NumPy."""
import json
from pathlib import Path

import numpy as np


PHASES = [0.0, np.pi / 2, np.pi]
A, B = [0, 2, 4], [1, 3, 5, 6]
C1, C2, C3 = 48.02138333, 6.55375, 5.35703333


def bond(h, i, j, value):
    h[i, j] += value
    h[j, i] += np.conj(value)


def ring(phi, ts=(1.0,) * 6, g=1.0, c2=0.0, c3=0.0, scheme="seam"):
    h = np.zeros((7, 7), dtype=complex)
    for i, t in enumerate(ts):
        nearest = phi / 6 if scheme == "geom" else (phi if i == 5 else 0)
        chord = phi / 6 if scheme == "geom" else 0
        bond(h, i, (i + 1) % 6, t * np.exp(1j * nearest))
        bond(h, i, (i + 2) % 6, c2 * np.exp(1j * chord))
    for i in range(3):
        bond(h, i, i + 3, c3)
    bond(h, 0, 6, g)
    return h


def mode(h, target=0.0):
    e, v = np.linalg.eigh(h)
    i = np.argmin(abs(e - target))
    return float(e[i]), v[:, i]


def port(v):
    return float(abs(v[6]) ** 2)


def odds_formula(ts, phi, g=1):
    t0, t1, t2, t3, t4, t5 = ts
    k1, k2 = t0*t2*t4, t1*t3*t5
    d = g**2 * ((t2*t4)**2 + (t1*t4)**2 + (t1*t3)**2)
    power = abs(k1 + k2*np.exp(1j*phi))**2
    return power / (power + d)


def cofactors():
    ts = [1.1, .9, 1.2, .8, 1., 1.3]
    maximum = 0.
    for phi in np.linspace(0, 2*np.pi, 81):
        h = ring(phi, ts)
        q = h[np.ix_(A, B)]
        b = np.array([(-1)**k * np.linalg.det(np.delete(q, k, axis=1))
                      for k in range(4)])
        pp = abs(b[-1])**2 / np.linalg.det(q @ q.conj().T).real
        maximum = max(maximum, abs(pp - port(mode(h)[1])), np.linalg.norm(q @ b),
                      abs(pp - odds_formula(ts, phi)))
    # The seam orientation in ring() conjugates the polynomial. We report
    # winding in the explicit polynomial convention K1 + K2 exp(+i phi).
    phi = np.linspace(0, 2*np.pi, 401)
    loops = [2 + np.exp(1j*phi), 1 + 2*np.exp(1j*phi)]
    # Signed variation over the closed loop gives the oriented winding.
    wind = [int(round(np.diff(np.unwrap(np.angle(z))).sum()/(2*np.pi))) for z in loops]
    curves = [odds_formula([t0,1,1,1,1,t5], phi) for t0,t5 in [(2,1),(1,2)]]
    np.testing.assert_allclose(curves[0], curves[1], atol=2e-15)
    assert maximum < 1e-12 and wind == [0,1]
    return dict(max_residual=maximum, unequal_P=[odds_formula(ts,p) for p in PHASES],
                identical_port_curves_windings=wind, K1=1.32, K2=.936)


def fabricated():
    rows = {}
    for scheme in ("seam","geom"):
        e, v = np.linalg.eigh(ring(0, [C1]*6, C1, C2, C3, scheme))
        branch = v[:,np.argmin(abs(e))]
        points = []
        least = 1.
        for step, phi in enumerate(np.linspace(0, 12*np.pi, 2401)):
            h = ring(phi, [C1]*6, C1, C2, C3, scheme)
            e, v = np.linalg.eigh(h)
            overlaps = abs(branch.conj() @ v)
            i = int(np.argmax(overlaps))
            least = min(least, float(overlaps[i]))
            branch = v[:,i]
            if step in (0,100,200,400,2400):
                points.append(dict(phi_over_pi=phi/np.pi, offset_MHz=e[i], P=port(branch)))
        assert least > .99
        rows[scheme] = dict(points=points, least_step_overlap=least)
    for key, expected in [('seam',.00641045),('geom',.03464980)]:
        np.testing.assert_allclose(rows[key]['points'][2]['P'], expected, atol=1e-8)
    np.testing.assert_allclose(rows['geom']['points'][3]['P'], .58895515, atol=1e-8)
    np.testing.assert_allclose(rows['geom']['points'][4]['P'], rows['geom']['points'][0]['P'])
    return rows


def chiral_chords():
    rows = []
    for r in (0.,.05,C3/C1,.3):
        zstar = -1 + r*(1+r)
        probabilities = []
        for phi in PHASES:
            e, v = mode(ring(phi,c3=r))
            u = abs(np.exp(1j*phi) - zstar)**2
            np.testing.assert_allclose(port(v), u/(2+(1+r)**2+u), atol=1e-14)
            assert abs(e) < 1e-13
            probabilities.append(port(v))
        rows.append(dict(c3_over_t=r, root=zstar, P=probabilities))
    return rows


def passive():
    def bridge(g1):
        h=np.zeros((9,9),complex)
        h[:7,:7]=ring(0)
        bond(h,0,7,g1)
        bond(h,7,8,1)
        bond(h,8,5,1)
        return h

    def single(delta, error):
        ga=np.sqrt(2*delta)*(1+error)
        h=np.zeros((8,8),complex)
        h[:7,:7]=ring(0)
        bond(h,0,7,ga)
        bond(h,5,7,ga)
        h[7,7]=delta
        h[0,0]=h[5,5]=ga**2/delta
        return h

    h=bridge(2)
    e,v=mode(h)
    gap=sorted(abs(np.linalg.eigvalsh(h)))[1]
    assert abs(e)<1e-13 and port(v)<1e-25
    np.testing.assert_allclose(abs(v[7])**2,.25)
    rows=[]
    for g1 in [0.,.5,1.,1.5,1.98,2.,2.02,2.5,3.]:
        e,v=mode(bridge(g1))
        pred=(2-g1)**2/(4+(2-g1)**2)
        np.testing.assert_allclose(port(v),pred,atol=1e-13)
        rows.append(dict(g1=g1,E=e,P=port(v)))
    aux=[]
    for delta in (10.,20.,50.,100.,200.):
        for error in ([-.01,0.,.01] if delta==20 else [0.]):
            e,v=mode(single(delta,error))
            assert abs(e)<1e-12
            if error==0: assert port(v)<1e-24
            aux.append(dict(delta=delta,error=error,E=e,P=port(v)))
    return dict(gap=gap,bridge=rows,single_compensated=aux)


def mass_and_scale():
    gamma=np.diag([1.,-1.,1.,-1.,1.,-1.,-1.])
    h=ring(.7,c3=C3/C1)
    _,v=mode(h)
    projector=np.outer(v,v.conj())
    worst=0.
    for m in (0.,.3,1.,3.,10.):
        e,w=mode(h-m*gamma,m)
        worst=max(worst, np.max(abs(np.outer(w,w.conj())-projector)))
        assert abs(e-m)<1e-12
    assert worst<1e-11
    dm=h-gamma
    port_probe=np.diag([0.]*6+[1.])
    def slope(probe):
        step=1e-5
        return (mode(dm+step*probe,1)[0]-mode(dm-step*probe,1)[0])/(2*step)
    v2=ring(.7,c2=1.,c3=C3/C1)-h
    a_only=np.zeros_like(dm)
    a_only[np.ix_(A,A)]=v2[np.ix_(A,A)]
    np.testing.assert_allclose((dm+a_only)@v,v,atol=1e-13)
    slopes=dict(mass=slope(-gamma),port=slope(port_probe),c2=slope(v2))
    np.testing.assert_allclose([slopes['mass'],slopes['port'],slopes['c2']],
                               [1,port(v),np.vdot(v,v2@v).real],atol=3e-9)
    scale=[]
    mx,eps=15.85,9.8910767  # keV, conditional corpus inputs
    for phi in PHASES:
        q=ring(phi)[np.ix_(A,B)]
        s=np.linalg.svd(q,compute_uv=False)
        shift=np.roll(np.eye(6,dtype=complex),-1,axis=0)
        shift[-1,0]=np.exp(1j*phi)
        d=6*(np.eye(6)-shift)
        scale.append(dict(phi_over_pi=phi/np.pi,s=s.tolist(),
                          cycle_nullity=6-int(np.linalg.matrix_rank(d)),
                          rectangular_nullity=4-int(np.linalg.matrix_rank(q)),
                          kinetic_keV=(np.hypot(mx,eps*s)-mx).tolist(),
                          quadratic_keV=(eps**2*s**2/(2*mx)).tolist()))
    assert [row['cycle_nullity'] for row in scale]==[1,0,0]
    assert all(row['rectangular_nullity']==1 for row in scale)
    return dict(slopes=slopes,projector_max_error=worst,c2_exact_shift=mode(dm+.13648*v2,1)[0]-1,
                M_keV=mx,epsilon_keV=eps,conditional_spectra=scale)


def tolerance():
    def simulate(seed,n,sigmas):
        rng=np.random.default_rng(seed)
        rows=[]
        for sigma in sigmas:
            ts=1+rng.normal(0,sigma,(n,6))
            p=odds_formula(ts.T,np.pi)
            rows.append(dict(sigma=sigma,mean=p.mean(),median=np.median(p),
                             p95=np.quantile(p,.95),fraction_below_1e_3=np.mean(p<.001)))
        return rows
    return dict(assumptions="Independent Gaussian nearest-neighbour bonds, mean t=g=1, c2=c3=0.",
                seed_3_n_20000=simulate(3,20000,[.005,.01,.02,.05]),
                seed_2026_n_400000=simulate(2026,400000,[.0114,.02,.022,.02236]))


if __name__ == "__main__":
    result=dict(scope="FINITE_MODEL_ONLY",phase_order_over_pi=[0,.5,1],
                couplings_MHz=dict(c1=C1,c2=C2,c3=C3,g_assumed=C1),
                cofactors=cofactors(),chords=chiral_chords(),full_ring=fabricated(),
                passive=passive(),mass=mass_and_scale(),tolerance=tolerance())
    Path(__file__).with_name('RESULTS.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
