#!/usr/bin/env python3
import json, math, time
from functools import lru_cache
from itertools import product
import sympy as s
from sympy.polys.numberfields import round_two
start=time.perf_counter(); checks={}; report={}
def ck(name, condition):
    checks[name]=bool(condition)
    assert condition,name
def mat(A): return [[str(a) for a in row] for row in A.tolist()]
M=s.Matrix([[1,1],[1,0]]); A=M**2; S=s.Matrix([[-2,1],[1,2]])
Q=s.diag(S,1,1); gamma=s.diag(A,1,1); phi=(1+s.sqrt(5))/2
x=s.symbols('x'); ell=2*s.log(phi)
ck('A preserves S',A.T*S*A==S); ck('M reverses S',M.T*S*M==-S)
ck('gamma preserves Q',gamma.T*Q*gamma==Q and gamma.det()==1)
ck('Q signature',sum(m for e,m in Q.eigenvals().items() if e>0)==3 and sum(m for e,m in Q.eigenvals().items() if e<0)==1)
e1=s.eye(4)[:,0]; v=s.Matrix([1,-1,1,1])
ck('gamma preserves time cone',(e1.T*Q*gamma*e1)[0]<0)
ck('isotropic witness',(v.T*Q*v)[0]==0)
ck('eigenvalues',s.expand(gamma.charpoly(x).as_expr()-(x-1)**2*(x*x-3*x+1))==0)
ck('phi^4 minpoly',s.minimal_polynomial(phi**4,x)==x*x-7*x+1)
ck('cosh length',s.simplify((phi+1/phi)/2-s.sqrt(5)/2)==0)
a,b,c=s.symbols('a b c'); R=s.Matrix([[a,b],[b,c]])
sol=s.linsolve(list(A.T*R*A-R),(a,b,c))
ck('invariant binary forms one-dimensional',sol==s.FiniteSet((-c,c/2,c)))
L=[2,1]
for k in range(2,100): L.append(L[-1]+L[-2])
family=[]
for k in range(1,21):
    q=(A**k).charpoly(x).as_expr(); p=x*x-L[4*k]*x+1
    ck(f'Salem identity k={k}',s.expand(q*q.subs(x,-x)-p.subs(x,x*x))==0)
    family.append([k,L[2*k],L[4*k]])
report['lorentz']={'A':mat(A),'S':mat(S),'Q':mat(Q),'det_Q':str(Q.det()),'signature':[3,1], 'gamma_eigenvalues':{str(k):m for k,m in gamma.eigenvals().items()},'isotropic_v':list(map(int,v)), 'ell':str(s.N(ell,40)), 'minpoly_exp_2ell':str(s.minimal_polynomial(phi**4,x)), 'invariant_forms':str(sol),'powers':family}
# Ordered PBW monomials indexed by bit masks. Nonorthogonal Gram matrix.
Qm=[[int(a) for a in row] for row in Q.tolist()]
def add(out,key,c):
    if c: out[key]=out.get(key,0)+c
    if out.get(key)==0: out.pop(key,None)
@lru_cache(None)
def left(i,blade):
    if not blade: return {1<<i:1}
    j=(blade & -blade).bit_length()-1; rest=blade^(1<<j)
    if i<j: return {blade|(1<<i):1}
    if i==j: return {rest:Qm[i][i]}
    out={}; add(out,rest,2*Qm[i][j])
    for k,c in left(i,rest).items():
        for k2,c2 in left(j,k).items(): add(out,k2,-c*c2)
    return out
@lru_cache(None)
def blade_mul(a,b):
    out={b:1}
    for i in reversed(range(4)):
        if a>>i&1:
            nxt={}
            for k,c in out.items():
                for k2,c2 in left(i,k).items(): add(nxt,k2,c*c2)
            out=nxt
    return out
def mul(A,B):
    out={}
    for a,c in A.items():
        for b,d in B.items():
            for k,e in blade_mul(a,b).items(): add(out,k,c*d*e)
    return out
def lin(A,B,sign=1):
    out=A.copy()
    for b,c in B.items(): add(out,b,sign*c)
    return out
E=[{1<<i:1} for i in range(4)]
for i,j in product(range(4),repeat=2):
    z=2*Qm[i][j]
    ck(f'Clifford relation {i},{j}',lin(mul(E[i],E[j]),mul(E[j],E[i]))==({0:z} if z else {}))
for a,b,c in product(range(16),repeat=3):
    assert mul(blade_mul(a,b),{c:1})==mul({a:1},blade_mul(b,c)),(a,b,c)
ck('4096 associative basis triples',True)
raw={15:1}; omega={15:1,12:-1}; even=[k for k in range(16) if k.bit_count()%2==0]
ck('raw volume square',mul(raw,raw)=={0:-4,3:-2})
ck('raw volume not central',mul(raw,{5:1})!=mul({5:1},raw))
ck('correct volume square',mul(omega,omega)=={0:-5})
ck('correct volume central',all(mul(omega,{k:1})==mul({k:1},omega) for k in even))
cols=[]
for k in even:
    col=[]
    for j in even:
        comm=lin(mul({k:1},{j:1}),mul({j:1},{k:1}),-1)
        col.extend(comm.get(i,0) for i in even)
    cols.append(s.Matrix(col))
ns=s.Matrix.hstack(*cols).nullspace(); ck('center dimension exactly 2',len(ns)==2)
P0=s.eye(4); P0[0,1]=s.Rational(1,2); D=P0.T*Q*P0
ck('diagonal Gram',D==s.diag(-2,s.Rational(5,2),1,1)); ck('orthogonal volume square',D.det()==-5)
comps=[]
for a,b in [(1,1),(1,2),(2,1),(1,3),(1,5)]:
    Qp=s.diag(S,a,b); gp=s.diag(A,1,1)
    ck(f'complement {a},{b} invariant',gp.T*Qp*gp==Qp)
    comps.append({'complement':[a,b],'det':int(Qp.det())})
Qalt=s.diag(S,1,2); va=s.Matrix([1,0,0,1]); ck('alternate isotropic form',(va.T*Qalt*va)[0]==0)
report['clifford']={'gram_diagonal':mat(D),'raw_square':mul(raw,raw),'raw_commutator_with_e1e3':lin(mul(raw,{5:1}),mul({5:1},raw),-1),'correct_volume':omega,'correct_square':mul(omega,omega),'even_center_dimension':len(ns),'center_basis_coordinates':[[str(a) for a in z] for z in ns],'even_blade_masks':even,'associativity_checks':4096,'complements':comps}
# Hermitian determinant model over the imaginary quadratic field.
w=s.eye(4)[:,2]-v/2; r=s.Matrix([1,-1,0,2]); t=s.Matrix([-1,3,0,0])
P=s.Matrix.hstack(v,w,r,t); gram=P.T*Q*P
ck('Hermitian coordinates Gram',gram==s.Matrix([[0,1,0,0],[1,0,0,0],[0,0,2,0],[0,0,0,10]]))
u=s.I*s.sqrt(5)
def X(a,b,c,d): return s.Matrix([[a,c+u*d],[c-u*d,-b]])
B=s.Matrix([[-1+u,-1],[2,1+u]]); C=s.simplify(-B**2/4); gP=P.inv()*gamma*P
for i in range(4):
    ck(f'projective Hermitian action basis {i}',s.simplify(B*X(*s.eye(4)[:,i])*B.conjugate().T/4-X(*gP[:,i]))==s.zeros(2))
ck('projective determinant and trace',s.simplify(B.det())==-4 and s.simplify(B.trace()**2/B.det())==5)
ck('gamma squared lift SL2',s.simplify(C.det())==1 and s.simplify(C.trace())==3)
Bscaled=s.simplify(-u*B/2); e=s.Matrix([1,0]); T=s.Matrix.hstack(e,Bscaled*e)
J=s.Matrix([[0,-5],[1,5]]); J2=J-s.eye(2)
ck('companion lift',s.simplify(Bscaled*T-T*J)==s.zeros(2))
ck('square companion lies in SL2Z',J**2/5==J2 and J2.det()==1 and J2.trace()==3)
report['bianchi']={'P':mat(P),'Pdet':str(P.det()),'Gram':mat(gram),'gamma_coordinates':mat(gP),'B':mat(B),'det_B':str(B.det()),'trace_squared_over_det':str(s.simplify(B.trace()**2/B.det())),'gamma_squared_lift':mat(C),'projective_companion':mat(J),'companion_squared_SL2Z':mat(J2),'spin_obstruction':'det B=-4 not square in Q(sqrt(-5))'}
mod3=[[[int(a)%3 for a in row] for row in (gamma**k).tolist()] for k in range(1,5)]
I4mod=[[int(a) for a in row] for row in s.eye(4).tolist()]
ck('gamma order modulo 3 = 4',mod3[-1]==I4mod and all(k!=I4mod for k in mod3[:-1]))
report['congruence']={'mod3_order':4,'gamma4':mat(gamma**4),'lifted_length':str(s.N(4*ell,40)),'mod3_powers':mod3}
# Class field and its local L-factors, including ramified places.
def hneg(D):
    out=[]
    for a in range(1,math.isqrt(abs(D)//3)+1):
        for b in range(-a,a+1):
            if (b*b-D)%(4*a): continue
            c=(b*b-D)//(4*a)
            if c>=a and math.gcd(math.gcd(a,b),c)==1 and not((a==c or abs(b)==a) and b<0): out.append((a,b,c))
    return out
forms=hneg(-20)
ck('class number -20',forms==[(1,0,5),(2,2,3)])
ck('class number -4',hneg(-4)==[(1,0,1)])
f=s.Poly(x**4-2*x**3+x**2+5,x)
order,disc=round_two(f)
ck('biquadratic field discriminant',int(disc)==400)
ck('relative discriminant norm one',int(disc)==(-20)**2)
z=s.symbols('z'); rows=[]; primes=list(s.primerange(2,600))
for p in primes:
    c5=int(s.kronecker_symbol(5,p)); c4=int(s.kronecker_symbol(-4,p)); c20=int(s.kronecker_symbol(-20,p))
    ck(f'character twist p={p}',c20==c5*c4)
    if p==2: den=1+z; theta=[-1]
    elif p==5: den=1-z; theta=[1]
    elif c20==1: den=(1-c5*z)**2; theta=[c5,c5]
    else: den=1-z*z; theta=[1]
    ck(f'base-change Euler factor p={p}',s.expand(den-(1-c5*z)*(1-c4*z))==0)
    if c20==1:
        rep=any((p-5*b*b)>=0 and math.isqrt(p-5*b*b)**2==p-5*b*b for b in range(math.isqrt(p//5)+1))
        ck(f'class character norm form p={p}',rep==(c5==1))
    rows.append({'p':p,'chi5':c5,'chi_minus4':c4,'chi_minus20':c20,'theta_at_ideals':theta,'local_denominator':str(s.expand(den))})
report['class_field']={'forms_minus20':forms,'h_minus20':len(forms),'forms_minus4':hneg(-4),'primitive_element_polynomial':str(f.as_expr()),'polynomial_discriminant':str(f.discriminant()),'maximal_order_discriminant':int(disc),'relative_discriminant_norm':1,'prime_count':len(primes),'local_factors':rows,'L1_theta':str(s.N(s.pi*s.log(phi)/(2*s.sqrt(5)),40)),'zeta_E_residue':str(s.N(s.pi**2*s.log(phi)/10,40))}
report['checks']={'count':len(checks),'passed':sum(checks.values()),'failed':[k for k,v in checks.items() if not v]}
report['seconds']=time.perf_counter()-start
print(json.dumps(report,ensure_ascii=False,indent=2))
