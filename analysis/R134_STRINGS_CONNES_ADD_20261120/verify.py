"""Audit pinned donors. See REPORT.md for input locations and normalization."""
import argparse
import csv
import hashlib
import io
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from runpy import run_path

import mpmath as mp
import numpy as np
import sympy as sp

HERE = Path(__file__).resolve().parent
DEMO = 'a71bd690a128e725fd1e900ac54133bd5bc3b907'
NOTEBOOK = '101f8d95525e884f40e69e0e993eea5fb177babcace2016ad9e1f5f6d8fec6c6'


def four_points(root):
    root = root.resolve()
    assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'], text=True).strip() == DEMO
    for filename in ('veneziano.py', 'virasoro_shapiro.py', 'coon.py', 'partial_waves.py'):
        raw = subprocess.check_output(['git','-C',str(root),'show',f'{DEMO}:sim/{filename}'])
        assert raw == (root/'sim'/filename).read_bytes()
    sys.path.insert(0, str(root/'sim'))
    from veneziano import veneziano, residue_pochhammer
    from virasoro_shapiro import virasoro_shapiro
    from coon import coon_amplitude
    from partial_waves import project_legendre
    def closed(s,t):
        return mp.fprod(mp.gamma(-u)/mp.gamma(1+u) for u in (s,t,-s-t))

    s,t = mp.mpf('-1.37'),mp.mpf('-.6')
    assert abs(mp.beta(-s,-t) + veneziano(float(s-1), float(t-1))) < 1e-13
    assert abs(closed(s,t) + virasoro_shapiro(float(4*s),float(4*t))) < 1e-12 * abs(closed(s,t))
    # Independent extraction on the side s=n-epsilon, so A ~ R/(n-s).
    eps = mp.mpf('1e-24')
    for n in range(9):
        r = mp.rf(1+t,n)/mp.factorial(n)
        assert abs(eps*mp.beta(-n+eps,-t)-r) < 1e-21
        assert abs(float(r)-residue_pochhammer(n,float(t-1))) < 1e-13
        for j in range(1,n+1):
            assert residue_pochhammer(n,-j-1) == 0
        rc = (-1)**n * mp.gamma(-t)*mp.gamma(n+t)/(mp.factorial(n)**2*mp.gamma(1+t)*mp.gamma(1-n-t))
        assert abs(eps*closed(n-eps,t)-rc) < 1e-21
    p_leg = project_legendre(lambda n,x: residue_pochhammer(n,x), 2)
    # n=2 in the demo: t=(z-1)/2, so R=(z+3)(z+5)/8.
    assert np.allclose(p_leg,[23/12,1,1/12])
    imag = mp.im(-mp.beta(-s-mp.mpc(0,'.35'),-t))
    assert abs(imag) > mp.mpf('.01') and np.isrealobj(veneziano(complex(s-1,.35),float(t-1)))
    with np.errstate(invalid='ignore'):
        assert np.isnan(veneziano(1.,-.7))
    actual = float(coon_amplitude(.5,-1.6,.5)[0])
    # S=s_demo+1. At S=[2]_(1/2)=1.5 the logarithmic trajectory equals 2.
    assert np.isfinite(actual) and actual < 1
    q = mp.mpf('.5')
    alpha = lambda v: mp.log1p((q-1)*v)/mp.log(q)
    at = alpha(t)
    def coon_pole(delta):
        a_s = alpha(mp.mpf('1.5')-delta)
        return delta*q**(a_s*at)*mp.qgamma(-a_s,q)*mp.qgamma(-at,q)/mp.qgamma(-a_s-at,q)
    small = mp.mpf('1e-15')
    limit = coon_pole(small)
    assert abs(limit) > mp.mpf('.001') and abs(limit-coon_pole(small/2)) < mp.mpf('1e-13')
    qone,qtwo = (float(coon_amplitude(-2.4,-1.6,q)[0]) for q in (1.,2.))
    assert qone == qtwo and veneziano(-2.4,-1.6) < 0
    return {'open_and_closed_levels_checked':9, 'required_open_zeros':36,
            'demo_exact_pole':'nan', 'true_demo_sign_complex_imag':mp.nstr(imag,12),
            'q_half_demo_at_expected_second_level':round(actual,10),
            'coon_reference_scaled_pole':mp.nstr(limit,12),
            'q_one_and_two_demo_identical':True, 'D4_legendre_level_2':['23/12','1','1/12']}


def five(s1,s2,a,b,c):
    return mp.beta(-s1,-a)*mp.beta(-s2,-b)*mp.hyper(
        [-s1,-s2,c-a-b],[-s1-a,-s2-b],1)


def five_checks(nb):
    raw = nb.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == NOTEBOOK
    assert all(s in raw for s in (b'"NIntegrate"', b'"Aclosed5"', b'"A5"', b'143.90870132439917'))
    args = sp.symbols('d12 d13 d23 d24 d34')
    u,v,w,z,k = args
    s1,s2,a,b,c = u-1,u+v+w-2,w-1,k-1,z+w+k-2
    # All beta arguments, the mixed upper parameter and both lower ones in Eq. A6.
    assert tuple(map(sp.expand,(-s1,-a,-s2,-b,c-a-b,-s1-a,-s2-b))) == (
        1-u,1-w,2-u-v-w,1-k,z,2-u-w,3-u-v-w-k)
    # Ordered adjacent channels (12,23,34,45,51). Test all five label rotations.
    channels = (-1,-2,-1,-2,-4)
    values = []
    for j in range(5):
        u,a,b,v,c = channels[j:]+channels[:j]
        values.append(five(u,v,a,b,c))
    # At the first ordering the Euler integrand is y(1-x)(1-xy).
    val = mp.mpf(7)/36
    assert max(abs(x-val) for x in values) < mp.mpf('1e-40')
    assert abs(five(-1,-1,-1,-1,-1)-mp.zeta(2)) < mp.mpf('1e-40')
    # Direct integration of the ordered disk integral at the asymmetric point.
    integral = mp.quad(lambda y: mp.quad(lambda x: y*(1-x)*(1-x*y),[0,1]),[0,1])
    assert abs(integral-val) < mp.mpf('1e-40')
    return {'notebook_sha256':NOTEBOOK,'bytes':len(raw),'notebook_runtime_executed':False,
            'asymmetric_amplitude':'7/36','cyclic_orders_checked':len(values),
            'all_adjacent_channels_minus_one':'pi^2/6'}


def residues_table():
    # Coefficients of (1-x)^9(1-y)^5(1-xy)^9 in the Euler integrand.
    expanded = defaultdict(int)
    for i in range(10):
        for j in range(6):
            for k in range(10):
                expanded[i+k,j+k] += (-1)**(i+j+k)*math.comb(9,i)*math.comb(5,j)*math.comb(9,k)
    # Independently evaluate the pole-cancelled finite sum of Eq. 23.
    def binom(d,k):
        return math.comb(d,k) if 0 <= k <= d else 0
    stream = io.StringIO()
    writer = csv.writer(stream,lineterminator='\n')
    writer.writerow(('n1','n2','inside_D','double_residue'))
    inside = 0
    zeros = []
    for n in range(20):
        for m in range(16):
            v = sum((-1)**(n+m-k)*binom(9,k)*binom(9,n-k)*binom(5,m-k) for k in range(min(n,m)+1))
            domain = n<19 and m<15 and -6<n-m<10
            assert v == expanded[n,m] and (domain or v == 0)
            inside += int(domain)
            if domain and v==0:
                zeros.append([n,m])
            writer.writerow((n,m,int(domain),v))
    assert inside==195 and len(zeros)==9 and [1,3] in zeros
    # Extract selected residues from the full A6 amplitude along an off-pole path.
    eps = mp.mpf('1e-19')
    checked_levels = [(0,0),(1,1),(1,3),(5,5),(6,2)]
    for n,m in checked_levels:
        measured = 2*eps**2 * five(n-eps,m-2*eps,-10,-6,-25)
        assert abs(measured-expanded[n,m]) < mp.mpf('1e-12')
    # A factor (1+xy) leaves both one-channel boundaries unchanged.
    def modified(n,m):
        return expanded[n,m] + (expanded[n-1,m-1] if n>0 and m>0 else 0)
    assert all(modified(n,0)==expanded[n,0] for n in range(20))
    assert all(modified(0,m)==expanded[0,m] for m in range(16))
    assert (expanded[1,1],modified(1,1)) == (36,37)
    return stream.getvalue(),{'mixed_level_control':[36,37], 'full_amplitude_limits_checked':checked_levels, 'grid':[20,16],'domain_points':inside,'nonzero':inside-len(zeros),
                              'internal_zeros':zeros}


def ring_control():
    graph = run_path(str(HERE.parent/'R132_ADD_YM_CCM_20261119/verify.py'))['graph_operators']
    D = sp.Matrix(graph(3))
    v = D.eigenvals()
    assert v == {0:2,sp.sqrt(3):2,-sp.sqrt(3):2}
    return {'R132_L3_distinct_eigenvalues':['-sqrt(3)','0','sqrt(3)'],'multiplicities':[2,2,2]}


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--demo',type=Path,required=True)
    p.add_argument('--notebook',type=Path,required=True)
    p.add_argument('--write-csv',action='store_true')
    args=p.parse_args()
    mp.mp.dps=55
    table,counts=residues_table()
    path=HERE/'five_point_residues.csv'
    if args.write_csv:
        path.write_bytes(table.encode())
    else:
        assert path.read_bytes()==table.encode()
    result={'four_points':four_points(args.demo),'five_points':five_checks(args.notebook),
            'truncation':counts,'ring':ring_control()}
    print(json.dumps(result,indent=2))
