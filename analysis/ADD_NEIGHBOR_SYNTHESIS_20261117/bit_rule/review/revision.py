"""Reproduce revised C2, H6 and seam measurements using the repository inputs."""
from collections import Counter, defaultdict
from fractions import Fraction
from itertools import product
from pathlib import Path
import json
from runpy import run_path
from types import SimpleNamespace
import sympy as sp

ROOT = Path(__file__).resolve().parent
ring = SimpleNamespace(**run_path(str(ROOT.parents[1] / "verify.py")))

A = (3,3,3,2,2,2,2,2)
B = (2,2,2,2,3,3,3,2)
EPS = (1,-1)
table = json.loads((ROOT.parents[2] / "R140_HAAR_SORKIN" / "HISTORIES.json").read_text())
def freeze(x):
    return tuple(map(freeze, x)) if isinstance(x, list) else x

def enabled(graph):
    return not ring.equal(graph, ring.interact(graph, EPS))

def length_histories():
    rows = {}
    for particle, position in product((1,8),range(3)):
        start = ring.named(tuple(particle if i == position else 0 for i in range(3)))
        seen = Counter()
        endpoints = set()
        for switches in product((0,1), repeat=8):
            graph = start
            history = []
            for on in switches:
                assert not enabled(graph)
                if on:
                    graph = ring.interact(graph,EPS)
                graph = ring.transport(graph,2)
                history.append(len(graph))
            seen[tuple(history)] += 1
            endpoints.add(ring.cyclic(graph))
        assert seen == {(3,)*8:256} and len(endpoints)==1
        rows[f"{particle}@{position}"] = {"word":"33333333","patterns":256,"ends":1}
    return rows

def read_sectors():
    I = sp.eye(3)
    w = (-1+sp.I*sp.sqrt(3))/2
    relative = sp.diag(1,w,w.conjugate())
    ub = I[:,[0,2,1]]
    ua = ub*relative
    psi = sp.Matrix([1 + h for h in (1,w,w.conjugate())])/sp.sqrt(6)
    a, b = (-1+sp.I)/16,(1-sp.I)/16
    def cross(v,u1,u2,phase,E):
        x,y = phase*a*u1*v, b*u2*v
        def sq(z): return (z.H*E*z)[0]
        return sp.simplify(sp.expand_complex(sq(x+y)-sq(x)-sq(y)))
    result = {}
    for tag,v,phase in [('published_phi0',psi,1),('published_phi_pi2',psi,sp.I),
                        ('asymmetric_phi0',I[:,1],1)]:
        raw, right, unturned = [], [], []
        for i in range(3):
            E = I[:,i]*I[:,i].H
            raw.append(cross(v,ua,ub,phase,E))
            right.append(cross(v,relative,I,phase,ub.H*E*ub))
            unturned.append(cross(v,relative,I,phase,E))
        assert raw==right and sum(raw)==sum(unturned)
        result[tag] = {'physical':raw,'transported_detector':right,'fixed_detector':unturned}
    q=sp.Rational
    assert result['published_phi0']['physical']==[-q(1,96),q(1,768),q(1,768)]
    assert result['published_phi_pi2']['physical']==[0,-sp.sqrt(3)/768,sp.sqrt(3)/768]
    assert result['asymmetric_phi0']['physical']==[0,0,q(1,128)]
    assert result['asymmetric_phi0']['fixed_detector']==[0,q(1,128),0]
    return result

def field(op, length, v):
    if op=='H6' and length==2:return (v[2],v[0],v[1])
    if op=='H6' and length==3:return (v[0],v[2],v[1])
    return v

def sums_from_export(op, rule):
    # The table contains 16 times the physical amplitudes. c is expressed in units 1/sqrt(2).
    ends = [[0j]*3 for _ in table['named_endpoints']]
    for row in table['branches']:
        history = tuple(row['lengths'])
        phase = 1j if (rule=='one_history' and history==A) or (rule=='first_length' and history[0]==3) else 1
        v=(1,1,0)
        for length in history:v=field(op,length,v)
        for end,r,i in row['amplitudes']:
            for k in range(3):
                ends[end][k]+=complex(r,i)*phase*v[k]
    return ends

def sums_by_forward(op,rule):
    start=ring.cyclic(ring.named(tuple(table['initial_word'])))
    current={start:(1,1,0)}
    for tick in range(8):
        following=defaultdict(lambda:[0j]*3)
        for graph,v in current.items():
            active=enabled(graph)
            branches=[(graph,(1-1j)/2),(ring.interact(graph,EPS),(1+1j)/2)] if active else [(graph,1)]
            for g,amplitude in branches:
                end=ring.cyclic(ring.transport(g,2))
                phase=1j if rule=='first_length' and tick==0 and len(end)==3 else 1
                updated=field(op,len(end),v)
                for k in range(3):
                    following[end][k]+=amplitude*phase*updated[k]
        current=following
    return [[16*z for z in current[freeze(end)]] for end in table['named_endpoints']]

def norm(v):
    weights = [z.real**2+z.imag**2 for z in v]
    assert all(x==int(x) for x in weights)
    return Fraction(int(sum(weights)),512)

def normalization():
    results={}
    for op in ('flat','H6'):
        readings={}
        for rule in ('baseline','one_history','first_length'):
            vectors=sums_from_export(op,rule)
            if rule!='one_history':assert sums_by_forward(op,rule)==vectors
            p=list(map(norm,vectors))
            if rule=='baseline':baseline=p
            readings[rule]={'sum':sum(p),'P19':p[19],
                            'changed':{i:p[i]-baseline[i] for i in range(len(p)) if p[i]!=baseline[i]},
                            'other_delta':sum(p)-sum(baseline)-p[19]+baseline[19]}
        assert readings['first_length']['sum']==1
        assert readings['one_history']['sum']==(Fraction(65,64) if op=='flat' else Fraction(129,128))
        assert readings['first_length']['P19']==readings['one_history']['P19']==Fraction(1,64)
        results[op]=readings
    return results

def bit_preparations():
    basis=[ring.named(tuple(particle if j==i else 0 for j in range(3))) for particle in (1,8) for i in range(3)]
    def permutation(action):
        indices=[next(j for j,y in enumerate(basis) if ring.equal(action(x),y)) for x in basis]
        return sp.eye(6)[:,indices]
    S=permutation(lambda g:ring.forward(ring.forward(g,EPS),EPS))
    T=permutation(lambda g:ring.interact(ring.r2(g),EPS))
    def path(history):
        u=sp.eye(6)
        for length in history:u=({2:S,3:T}[length])*u
        return u
    ua,ub=path(A),path(B)
    assert ub.H*ua==S and T*S*T==S.H
    c6=sp.Matrix([1,0,1,1,1,0])/2
    pure=c6*c6.H
    diagonal=sp.diag(*pure.diagonal())
    outputs={}
    for name,rho in [('coherent',pure),('dephased_same_populations',diagonal),('fully_mixed',sp.eye(6)/6)]:
        overlap=sp.trace(rho*ub.H*ua)
        contribution=-sp.re(overlap)/64
        outputs[name]={'overlap':overlap,'I2':contribution,'P19':sp.Rational(1,64)+contribution,
                       'arm_density_matrices_equal':ua*rho*ua.H==ub*rho*ub.H}
    assert outputs['coherent']['overlap']==sp.Rational(1,2)
    assert outputs['dephased_same_populations']['overlap']==0
    assert outputs['fully_mixed']['overlap']==0 and outputs['fully_mixed']['arm_density_matrices_equal']
    # Compare amplitudes at every physical endpoint, prior to taking squared norms.
    W = sp.Matrix([[1,0,0,1,0,0], [0,0,1,0,1,0], [0,1,0,0,0,1]]) / sp.sqrt(2)
    c = sp.Matrix([1,1,0]) / sp.sqrt(2)
    M = sp.eye(3)[:, [1,2,0]]
    J = sp.eye(3)[:, [0,2,1]]
    assert W.H*c == c6 and W*S == M*W and W*T == J*W and W*W.H == sp.eye(3)
    ends = table["named_endpoints"]
    bit = [sp.zeros(6,1) for _ in ends]
    h6 = [sp.zeros(3,1) for _ in ends]
    for row in table["branches"]:
        six, three = c6, c
        for length in row["lengths"]:
            if length == 2:
                six, three = S*six, M*three
            elif length == 3:
                six, three = T*six, J*three
        for endpoint, real, imag in row["amplitudes"]:
            amp = (sp.Integer(real) + sp.I*imag) / 16
            bit[endpoint] += amp*six
            h6[endpoint] += amp*three
    assert len(ends) == 40
    assert all((b-W.H*h).applyfunc(sp.simplify)==sp.zeros(6,1) for b,h in zip(bit,h6))
    assert sp.simplify(sum((b.H*b)[0] for b in bit)) == 1
    outputs["all_endpoints"] = {"compared_vectors":len(ends),"mismatches":0,"normalization":"1"}
    return outputs

def su3_phase():
    H=sp.diag(sp.I,sp.I,-1);I=sp.eye(3);hc=H.H;d=2*I-H-hc
    result=[]
    for h in [H,hc]:
        assert h.det()==1 and 2*I-h-h.H==d
        result.append({'I2_zero':-sp.re(h.trace())/192,'I2_pi2':sp.im(h.trace())/192,
                       'Z6':(320*I+d).det()})
    assert result[0]['I2_pi2']==-result[1]['I2_pi2']==sp.Rational(1,96)
    return result
def trace_polynomial():
    u,z,x,y=sp.symbols("u z x y", real=True)
    char=u**3-(x+sp.I*y)*u**2+(x-sp.I*y)*u-1
    expected=z*(z+3-x)**2+(z+4)*y**2
    assert sp.expand(sp.resultant(char,u**2-(z+2)*u+1,u)+expected)==0
    ident=sp.eye(3)
    rows=[]
    for H in (sp.diag(-1,-1,1),sp.diag(sp.I,sp.I,-1)):
        # The same seam acts from vertex 5 to 0. All five other links are trivial.
        shift=sp.zeros(18,18)
        for i in range(6):
            j=(i+1)%6
            shift[3*j:3*j+3,3*i:3*i+3]=H if j==0 else ident
        diff=shift-sp.eye(18)
        det=(sp.eye(18)+diff*diff.H).det()
        re,im=H.trace().as_real_imag()
        assert det==expected.subs({z:320,x:re,y:im})
        rows.append({"I2_at_zero":-re/192,"I2_at_pi_2":im/192,"Z6":int(det)})
    return {"symbolic_identity":True,"seams":rows}

def experiment_summary(native, preparations):
    # A and B are events in the length record of the selected geometry.
    histories = {row["word"] for row in native.values()}
    assert histories == {"33333333"}
    assert all("".join(map(str,path)) not in histories for path in (A,B))
    amps = {}
    for row in table["branches"]:
        if tuple(row["lengths"]) in (A,B):
            (end,real,imag), = row["amplitudes"]
            assert end == 19
            amps[tuple(row["lengths"])] = (sp.Integer(real)+sp.I*imag)/16
    a,b=amps[A],amps[B]
    single=sp.simplify(abs(a)**2 + abs(b)**2)
    flat=sp.simplify(2*sp.re(sp.conjugate(b)*a))
    assert flat == -sp.Rational(1,64) and single+flat==0
    return {"native_absent_length_events":{"mu_A":0,"mu_B":0,"mu_union":0,"I2":0},
            "R140_geometry_native_spectator":{"overlap":1,"I2":flat,"P19":single+flat},
            "R140_geometry_controlled_coherent":{"overlap":preparations["coherent"]["overlap"],
                                                "I2":preparations["coherent"]["I2"],
                                                "P19":preparations["coherent"]["P19"]}}


if __name__ == "__main__":
    native = length_histories()
    preparations = bit_preparations()
    results = {
        "experiment_summary": experiment_summary(native, preparations),
        "lengths_native": native,
        "sectors": read_sectors(),
        "phase_runs": normalization(),
        "controlled_bit_preparations": preparations,
        "same_Dop_adjoint_seams": su3_phase(),
        "SU3_trace_polynomial": trace_polynomial(),
    }
    print(json.dumps(results, default=str, indent=2))
