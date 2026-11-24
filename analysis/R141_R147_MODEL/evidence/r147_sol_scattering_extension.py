#!/usr/bin/env python3
import json, math, time
import sympy as s
import mpmath as mp
from sympy.matrices.normalforms import smith_normal_form
start=time.perf_counter()
A=s.Matrix([[2,1],[1,1]]); I=s.eye(2); phi=(1+s.sqrt(5))/2
F=[0,1]; L=[2,1]
for _ in range(2,110): F.append(F[-1]+F[-2]); L.append(L[-1]+L[-2])
rows=[]
for n in range(1,51):
    C=smith_normal_form(A**n-I,domain=s.ZZ); ds=[abs(int(C[i,i])) for i in range(2)]
    expect=[L[n],L[n]] if n%2 else [F[n],5*F[n]]
    assert ds==expect and ds[0]*ds[1]==L[2*n]-2
    rows.append([n,ds,ds[0]*ds[1]])
# Ricci tensor directly from coordinate Christoffel symbols.
x,y,z=s.symbols('x y z',real=True); b=s.symbols('b',positive=True); coords=(x,y,z)
g=s.diag(s.exp(-2*z),s.exp(2*z),b); gi=g.inv()
G=[[[s.simplify(sum(gi[k,l]*(s.diff(g[l,j],coords[i])+s.diff(g[l,i],coords[j])-s.diff(g[i,j],coords[l]))/2 for l in range(3))) for j in range(3)] for i in range(3)] for k in range(3)]
Ric=s.Matrix(3,3,lambda i,j:s.simplify(sum(s.diff(G[k][i][j],coords[k])-s.diff(G[k][i][k],coords[j])+sum(G[k][k][l]*G[l][i][j]-G[k][j][l]*G[l][i][k] for l in range(3)) for k in range(3))))
assert Ric==s.diag(0,0,-2)
assert s.trace(gi*Ric)==-2/b
ell=2*s.log(phi); D=s.diag(phi**2,phi**-2,1)
assert all(s.simplify(v.rewrite(s.exp))==0 for v in D.T*g.subs(z,z+ell)*D-g)
# Independent partial zeta coefficients: norm forms for two ideal classes.
N=5000; B=math.isqrt(N); a0=[0]*(N+1); a1=[0]*(N+1)
for u in range(-B,B+1):
 for v in range(-B,B+1):
    q0=u*u+5*v*v; q1=2*u*u+2*u*v+3*v*v
    if 0<q0<=N: a0[q0]+=1
    if 0<q1<=N: a1[q1]+=1
assert all(n%2==0 for n in a0+a1)
a0=[n//2 for n in a0]; a1=[n//2 for n in a1]
chi5=lambda n: 0 if n%5==0 else (1 if n%5 in (1,4) else -1)
chi4=lambda n: 0 if n%2==0 else (1 if n%4==1 else -1)
d0=[0]*(N+1); d1=[0]*(N+1)
for d in range(1,N+1):
 for k in range(1,N//d+1):
    d0[d*k]+=chi5(d)*chi4(d)
    d1[d*k]+=chi5(d)*chi4(k)
assert all(a0[n]+a1[n]==d0[n] and a0[n]-a1[n]==d1[n] for n in range(1,N+1))
# Numerical control of Efrat-Sarnak channels. Independent norm-form sums in Re w>2.
mp.mp.dps=45
c5=[0,1,-1,-1,1]; c4=[0,1,0,-1]
def zkm(w): return mp.zeta(w)*mp.dirichlet(w,[chi5(n)*chi4(n) for n in range(20)])
def theta(w): return mp.dirichlet(w,c5)*mp.dirichlet(w,c4)
def comp(w): return (mp.sqrt(20)/(2*mp.pi))**w*mp.gamma(w)
def zp(w): return comp(w)*zkm(w)
def zm(w): return comp(w)*theta(w)
def pp(w): return zp(w-1)/zp(w)
def pm(w): return zm(w-1)/zm(w)
def trunc(w,sgn): return comp(w)*mp.fsum((a0[n]+sgn*a1[n])/mp.mpf(n)**w for n in range(1,N+1))
num=[]
for w in [mp.mpf(4),mp.mpf(5)]:
    rp,rm=pp(w),pm(w)
    tp=trunc(w-1,1)/trunc(w,1); tm=trunc(w-1,-1)/trunc(w,-1)
    num.append({'w':str(w),'plus':mp.nstr(rp,30),'minus':mp.nstr(rm,30),'det':mp.nstr(rp*rm,30),'norm_form_plus_absolute_residual':mp.nstr(abs(tp-rp),10),'norm_form_minus_absolute_residual':mp.nstr(abs(tm-rm),10)})
uni=[]
for t in [1,3,7,12]:
    w=1+mp.j*t; rp,rm=pp(w),pm(w)
    uni.append({'t':t,'plus_modulus_error':mp.nstr(abs(abs(rp)-1),5),'minus_modulus_error':mp.nstr(abs(abs(rm)-1),5)})
# One pole of the negative scattering channel from the L5 zero.
root=mp.mpf('6.64845334472771471612327846')
def hardy(t):
    w=mp.mpf('.5')+mp.j*t
    return mp.re((5/mp.pi)**(w/2)*mp.gamma(w/2)*mp.dirichlet(w,c5))
root=mp.findroot(hardy,(root-mp.mpf('.001'),root+mp.mpf('.001')))
rho=mp.mpf('.5')+mp.j*root
res=zm(rho-1)/mp.diff(zm,rho)
poles=[]
for exp in [4,6,8]:
    eps=mp.mpf(10)**(-exp)
    poles.append({'epsilon':str(eps),'relative_residue_error':mp.nstr(abs(eps*pm(rho+eps)/res-1),10)})
result={'sol':{'SNF_cover_range':[1,50],'cover_rows':rows,'ricci_tensor':str(Ric),'scalar_curvature':'-2/b','flow':'b(t)=b(0)+4t','deck_metric_invariance':True},'ideal_classes':{'N':N,'sum_a0':sum(a0),'sum_a1':sum(a1),'sum_difference':sum(a0)-sum(a1),'sum_and_difference_mismatches':0},'scattering':{'numerical_checks':num,'unitarity':uni,'first_L5_pole':mp.nstr(rho,40),'residue':mp.nstr(res,30),'pole_replay':poles,'status':'exploratory numeric; exact factorization from Efrat-Sarnak / Sorensen; no PDE discretization or interval proof'},'seconds':time.perf_counter()-start}
print(json.dumps(result,indent=2))
