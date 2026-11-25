"""Exact eight-step ADD/H6 readout test and a separate numerical PDG comparison."""
import json
import math
from collections import Counter
from itertools import product
from pathlib import Path
from runpy import run_path
import sympy as s

root = Path(__file__).resolve().parent
data = json.loads((root/'inputs/HISTORIES.json').read_text())
ref = run_path(str(root/'inputs/graph_engine.py'))
I = s.eye(3)
M, J = I[:,[1,2,0]], I[:,[0,2,1]]
P = s.ones(3)/3
omega = (-1+s.sqrt(3)*s.I)/2
F = s.Matrix(3,3,lambda j,k:(1,omega,omega.conjugate())[j*k%3])/s.sqrt(3)
c = s.Matrix([1,1,0])/s.sqrt(2)

def clean(mat):
    return mat.applyfunc(lambda v:s.simplify(s.expand_complex(v)))

def freeze(v):
    return tuple(map(freeze,v)) if isinstance(v,list) else v

def operators():
    ends = [freeze(row) for row in data['named_endpoints']]
    rows = [s.zeros(3) for _ in ends]
    parity = [set() for _ in ends]
    for path in data['branches']:
        u = I
        for n in path['lengths']:
            u = {2:M,3:J}.get(n,I)*u
        for i,a,b in path['amplitudes']:
            rows[i] += (a+s.I*b)*u/16
            parity[i].add(path['lengths'].count(3)%2)
    assert all(len(entry)==1 for entry in parity)
    # Rebuild all three columns together from named graphs, without the serialized amplitudes.
    start = ref['cyclic'](ref['named']((1,2,0)))
    current = {start:I}
    for tick in range(8):
        following = {}
        for graph,op in current.items():
            idle = ref['cyclic'](ref['transport'](graph,2))
            flip = ref['cyclic'](ref['forward'](graph,(1,-1)))
            moves = [(idle,1)] if idle==flip else [(idle,(1-s.I)/2),(flip,(1+s.I)/2)]
            for end,weight in moves:
                next_op={2:M,3:J}.get(len(end),I)*op
                following[end] = following.get(end,s.zeros(3)) + weight*next_op
        current = {end:clean(op) for end,op in following.items()}
    assert set(current)==set(ends)
    assert all(clean(current[end]-op)==s.zeros(3) for end,op in zip(ends,rows))
    return list(map(clean,rows)), [next(iter(x)) for x in parity]

def ranks(effects):
    table=s.Matrix([list(effect) for effect in effects])
    return [table.rank(),table.applyfunc(s.re).rank()]

def koide_input(b):
    z=2*(1+b)+s.sqrt(3*(1+4*b+b*b))
    a=s.Matrix([1,b,z])
    assert s.simplify(3*a.dot(a)-2*sum(a)**2)==0
    return a

def run():
    ks,parities = operators()
    input_cases=[koide_input(2),koide_input(3)]
    record={}
    effects_by_basis={}
    for name,projectors in {
        'geometry':[I],
        'geometry_and_holonomy':[F.H[:,i]*F[i,:] for i in range(3)],
        'geometry_and_character':[I[:,i]*I[i,:] for i in range(3)]
    }.items():
        effects=[clean(k.H*e*k) for k in ks for e in projectors]
        effects_by_basis[name]=effects
        assert clean(sum(effects,s.zeros(3)))==I
        cyclic=all(clean(e*M-M*e)==s.zeros(3) for e in effects)
        rank=ranks(effects)
        assert (cyclic,rank)==((False,[9,6]) if name.endswith('_character') else (True,[3,2]))
        # For any real input only the real symmetric part of a Hermitian effect enters.
        # Test two different exact points on the Koide cone without fitting any masses.
        if cyclic:
            for e in effects:
                real=e.applyfunc(s.re)
                a,b=real[0,0],real[0,1]
                assert real==(a-b)*I+3*b*P
            assert all(s.simplify((v.T*P*v)[0]/v.dot(v))==s.Rational(1,2) for v in input_cases)
        record[name]={'effects':len(effects),'dimension_Hermitian_span':rank[0],
                      'dimension_for_real_inputs':rank[1],'all_commute_with_M':cyclic}
    assert clean(sum((k.H*P*k for k in ks),s.zeros(3)))==P
    sum_p=s.S.Zero
    post=Counter();pop=Counter();endpoints=[]
    hol_positive=[];char_positive=[]
    for g,k in enumerate(ks):
        v=clean(k*c);prob=s.simplify((v.H*v)[0])
        if prob==0:
            endpoints.append({'g':g,'weight':'0'})
            continue
        sing=s.simplify((v.H*P*v)[0]/prob);post[sing]+=1
        masses=tuple(sorted(s.simplify(s.Abs(el)**2/prob) for el in v))
        pop[masses]+=1;sum_p+=sing*prob
        if masses[0]>0:char_positive.append(masses[-1]/masses[0])
        vh=clean(F*v)
        hol=sorted([s.simplify((z*s.conjugate(z)).expand(complex=True)/prob) for z in vh],key=float)
        if hol[0]>0:hol_positive.append(s.simplify(hol[-1]/hol[0]))
        endpoints.append({'g':g,'weight':str(prob),'singlet':str(sing),'sorted_populations':list(map(str,masses))})
    assert s.simplify(sum_p)==s.Rational(2,3) and s.Rational(1,2) not in post
    assert len(char_positive)==12 and max(char_positive)==16
    assert len(hol_positive)==36 and max(hol_positive,key=float)==16
    assert len(endpoints)==40 and sum(post.values())==38 and len(pop)==6
    # Witness with an explicitly specified new detector.
    for index,effect in enumerate(effects_by_basis['geometry_and_character']):
        if all(effect[i,j]==0 for i,j in product(range(3),repeat=2) if i!=j) and len(set(effect.diagonal()))>1:
            vals=[s.radsimp(s.simplify((v.T*effect*v)[0]/v.dot(v))) for v in input_cases]
            if s.simplify(vals[0]-vals[1])!=0:
                witness={'g':index//3,'character':index%3,'diagonal':list(map(str,effect.diagonal())),
                         'probabilities':list(map(str,vals)),'numerical':[float(v) for v in vals]}
                break
    else: raise AssertionError('No character witness')
    assert clean(effects_by_basis['geometry'][19]-s.Rational(3,128)*(I-P))==s.zeros(3)
    val=clean(F*c)
    assert clean(F*P*F.H)==s.diag(1,0,0)
    assert clean(val.H*P*val)[0]==s.Rational(1,2)
    mod=s.Matrix([s.simplify(s.Abs(t)) for t in val])
    assert s.simplify(mod.dot(mod)/sum(mod)**2)==s.Rational(3,8)
    # Dimension of exact commutant on the specified three-dimensional representation.
    a=s.Matrix(3,3,s.symbols('x:9'))
    comm=s.linear_eq_to_matrix(list(a*M-M*a)+list(a*J-J*a),list(a))[0]
    assert 9-comm.rank()==2 and P.rank()==1 and (I-P).rank()==2
    assert all((sum(i*i for i in bits)%4!=0) for bits in product((0,1),repeat=3) if any(bits))
    return {'parity_blocks_even_odd':[parities.count(0),parities.count(1)],'cross_checked_endpoint_matrices':len(ks),
            'readouts':record,'new_detector_witness':witness,'two_ratio_examples':[[str(vj**2) for vj in v] for v in input_cases],
            'unconditional_singlet':str(s.simplify(sum_p)),'conditional_singlets':{str(k):n for k,n in post.items()},
             'direct_populations_positive':{
                'character_count':len(char_positive),'character_max_ratio':str(max(char_positive)),
                'holonomy_count':len(hol_positive),'holonomy_max_ratio':str(max(hol_positive,key=float)),
                'holonomy_max_ratio_numeric':float(max(hol_positive,key=float))},
            'population_patterns':{','.join(map(str,k)):n for k,n in pop.items()},'endpoints':endpoints}

def measurements():
    m=[0.51099895069,105.6583755,1776.93];err=[.00000000016,.0000023,.09]
    def params(m):
        a,b,c=map(math.sqrt,m);total=sum(m);ss=a+b+c;Q=total/ss**2
        phase=math.atan2(math.sqrt(3)*(b-a),2*c-a-b)
        return {'Q':Q,'p1':1/(3*Q),'angle_deg':math.degrees(math.acos(1/math.sqrt(3*Q))),
                'theta':phase,'cos3theta':math.cos(3*phase),'k':math.sqrt(3*Q-1)}
    d=params(m)
    grad=[1/sum(map(math.sqrt,m))**2-sum(m)/(math.sqrt(x)*sum(map(math.sqrt,m))**3) for x in m]
    sigma=math.hypot(*(g*de for g,de in zip(grad,err)))
    a,b=map(math.sqrt,m[:2]);D=math.sqrt(3*(a*a+4*a*b+b*b))
    roots=[(2*(a+b)+t*D)**2 for t in (-1,1)]
    def shape(theta):
        v=[1+math.sqrt(2)*math.cos(theta+k) for k in (2*math.pi/3,-2*math.pi/3,0)]
        return [(x/v[0])**2 for x in v]
    ratios=shape(2/9)
    return {'PDG2026_MeV':m,'errors_MeV':err,'ratios':[x/m[0] for x in m],**d,'sigma_Q_diagonal':sigma,
            'pull_Q':(d['Q']-2/3)/sigma,'sigma_Q_contributions':[g*de for g,de in zip(grad,err)],
            'old_inputs':params([.51099895,105.6583755,1776.86]),'two_tau_branches_MeV':roots,
            'theta_error_tau':(params([m[0],m[1],m[2]-.09])['theta']-params([m[0],m[1],m[2]+.09])['theta'])/2,
            'exact_K_and_2_over_9_ratios':ratios,'mu_residual_MeV_for_both':ratios[1]*m[0]-m[1]}
if __name__=='__main__':
    print(json.dumps({'data':measurements(),'model':run()},indent=2,ensure_ascii=False))
