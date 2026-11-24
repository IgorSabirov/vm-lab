"""Reproduce R149.10 and R149.11. Python 3 and mpmath 1.3.0. Run: python verify.py"""
import json
from fractions import Fraction
from math import comb
from pathlib import Path

import mpmath as mp

mp.mp.dps = 32
I = mp.j
TAU = 2 * mp.pi
HALF = mp.mpf("0.5")


def increments(values):
    return [mp.arg(b / a) for a, b in zip(values, values[1:])]


def circle(center, radius, n):
    points = [center + radius * mp.expj(TAU * k / n) for k in range(n)]
    return points + [points[0]]


def box(n):
    lo, hi = mp.mpf("0.2"), mp.mpf("0.8")
    corners = [lo + I, hi + I, hi + 26*I, lo + 26*I]
    return [a + (b-a)*j/n for a,b in zip(corners, corners[1:]+corners[:1])
            for j in range(n)] + corners[:1]


def contour(points, expected):
    values = [mp.zeta(p) for p in points]
    fine = increments(values)
    coarse = increments(values[::2])
    for steps in (coarse, fine):
        assert max(map(abs, steps)) < mp.pi * mp.mpf("0.9")
        assert abs(sum(steps)/TAU - expected) < mp.mpf("1e-25")
    total = mp.mpf(0)
    trace = [0.]
    for step in fine:
        total += step / TAU
        trace.append(round(float(total), 8))
    return dict(charge=expected, segments=len(fine), phase_turns=trace,
                max_phase_increment=float(max(map(abs, fine))))


def count_zeros(t):
    # Continue the argument from zeta(2)>0, first vertically and then horizontally.
    nodes = [2+I*t*j/128 for j in range(129)]
    nodes += [2+I*t-(2-HALF)*j/64 for j in range(1,65)]
    values = [mp.zeta(s) for s in nodes]
    fine, coarse = increments(values), increments(values[::2])
    assert abs(sum(fine)-sum(coarse)) < mp.mpf("1e-25")
    theta_pi = mp.siegeltheta(t)/mp.pi
    s_t = sum(fine)/mp.pi
    count = mp.nzeros(t)
    assert abs(theta_pi + 1 + s_t - count) < mp.mpf("1e-25")
    return dict(t=t, theta_pi=float(theta_pi), S=float(s_t), count=int(count))


def completed(s):
    return mp.power(mp.pi,-s/2)*mp.gamma(s/2)*mp.zeta(s)


def scatter(s):
    return completed(2*s-1)/completed(2*s)


def arithmetic():
    roots = [mp.zetazero(i) for i in range(1,4)]
    rings = {r:contour(circle(roots[0],mp.mpf(r),128),1) for r in ["0.3","0.5","2","4"]}
    controls = {"pole":contour(circle(1,HALF,128),-1),
                "trivial":contour(circle(-2,HALF,128),1), "box":contour(box(128),3)}
    hardy = []
    for t in map(mp.mpf,["10","14","14.3","20"]):
        value = mp.zeta(HALF+I*t)
        theta = mp.siegeltheta(t)
        z = mp.siegelz(t)
        residual = abs(mp.arg(value*mp.expj(theta) * (1 if z>0 else -1)))
        assert abs(mp.expj(theta)*value-z) < mp.mpf("1e-25") and residual < mp.mpf("1e-25")
        hardy.append(dict(t=float(t),Z=float(z),phase_residual=float(residual)))
    assert hardy[1]['Z'] < 0 < hardy[2]['Z']
    counts = [count_zeros(t) for t in [14,20,26,50]]
    assert [x['count'] for x in counts] == [0,1,3,10]
    for t in [3,9,17]:
        s=HALF+I*t
        assert abs(abs(scatter(s))-1) < mp.mpf("1e-25")
        assert abs(scatter(s)*scatter(1-s)-1) < mp.mpf("1e-25")
        assert abs(mp.arg(scatter(s)/mp.expj(2*mp.arg(completed(2*I*t))))) < mp.mpf("1e-25")
    s0=roots[0]/2
    residue=completed(2*s0-1)/(2*mp.diff(completed,roots[0]))
    approach=[]
    for eps in map(mp.mpf,["0.05","0.01","0.002"]):
        value=scatter(s0+eps)
        approach.append([float(eps),float(abs(value)),float(abs(eps*value-residue))])
    assert approach[2][2] < approach[1][2] < approach[0][2]
    phase=mp.mpf("2.9546326624")-mp.mpf("0.6525249472")
    det=mp.expj(phase)
    return dict(heights=[float(z.imag) for z in roots],rings=rings,controls=controls,
                hardy=hardy,counts=counts,modular_pole=approach,
                r147=dict(det=[float(det.real),float(det.imag)],xi_mod_one=float((-phase/TAU)%1)))


def orbits():
    cycles={2:4,10:204}
    degree=sum(k*v for k,v in cycles.items())
    coeff=[0]*(degree+1)
    for i in range(5):
        for j in range(205):
            coeff[2*i+10*j] += (-1)**(i+j)*comb(4,i)*comb(204,j)
    assert coeff == coeff[::-1]
    multiplicities=[sum(c for l,c in cycles.items() if k*l%10==0) for k in range(10)]
    assert sum(multiplicities)==degree==2048
    fixed=[sum(l*c for l,c in cycles.items() if n%l==0) for n in range(1,13)]
    # Independent extraction of the coefficients of log P from P' = P (log P)'.
    logp=[Fraction(0)]
    for n,fix in enumerate(fixed,1):
        a=Fraction(n*coeff[n]-sum(i*logp[i]*coeff[n-i] for i in range(1,n)),n)
        assert a==Fraction(-fix,n)
        logp.append(a)
    return dict(cycles=cycles,degree=degree,multiplicities=multiplicities,fixed=fixed,
                log_coefficients=[str(a) for a in logp[1:]],reciprocal=True)


if __name__ == "__main__":
    data=dict(dps=mp.mp.dps,mpmath=mp.__version__,arithmetic=arithmetic(),orbits=orbits())
    path=Path(__file__).with_name("CHECKS.json")
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("PASS",path)
