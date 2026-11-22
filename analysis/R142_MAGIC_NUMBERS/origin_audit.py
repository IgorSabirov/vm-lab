import math
from itertools import accumulate, product
from collections import Counter

# ---------- 1. their three series + count discipline ----------
def oscillator(d,kmax):
    st=list(product(range(kmax+1),repeat=d))
    return list(accumulate(2*sum(sum(x)==k for x in st) for k in range(kmax+1)))
dot=oscillator(2,5); osc=oscillator(3,6)
atomic=[sum(2*(2*l+1) for l in range(n)) for n in range(1,7)]
assert dot==[2,6,12,20,30,42] and osc==[2,8,20,40,70,112,168] and atomic==[2,8,18,32,50,72]
print("closed forms: osc3 (K+1)(K+2)(K+3)/3 ->",[(k+1)*(k+2)*(k+3)//3 for k in range(7)])
print("dot (K+1)(K+2) ->",[(k+1)*(k+2) for k in range(6)],"; 2n^2 ->",[2*n*n for n in range(1,7)])
groups=[[2,8,20,28,50,82,126],[16,32,34],osc,[2,10,18,36,54,86,118],[2,8,20,40,58,92],
        dot,atomic,[26,10,496],[8,230,12],[136,137,'Wyler'],['Koide'],['phi'],['delta'],
        ['angle'],['Dirac'],['Lambda'],['MOND']]
seen=set(); inc=[]
for g in groups:
    new=[x for x in g if x not in seen]; inc.append(len(new)); seen|=set(new)
print("increments:",inc,"sum:",sum(inc),"; extended:",len(seen|{'Efimov','BKT','Haldane'}))

# ---------- 2. NEW audit artifact: position multiplicity ----------
mult=Counter(x for g in groups for x in set(g))
print("\nmultiplicity (how many mechanisms claim the number):",
      {k:v for k,v in sorted(mult.items(),key=lambda kv:-kv[1]) if isinstance(k,int) and v>=3})
uniq=[k for k,v in mult.items() if v==1]
print("unique-to-one-mechanism positions:",len(uniq),"of",len(mult))

# ---------- 3. NEW audit artifact: prefix degeneracy ----------
S={'classic':[2,8,20,28,50,82,126],'osc3':osc,'noble':[2,10,18,36,54,86,118],
   'Na':[2,8,20,40,58,92],'dot2':dot,'2n2':atomic}
def lcp(a,b):
    n=0
    for x,y in zip(a,b):
        if x==y: n+=1
        else: break
    return n
ks=list(S); print("\nlongest common prefix:")
for i in range(len(ks)):
    for j in range(i+1,len(ks)):
        L=lcp(S[ks[i]],S[ks[j]])
        if L>=2: print(f"  {ks[i]:8s} vs {ks[j]:8s}: {L}  (first difference at #{L+1})")

# ---------- 4. alpha hypotheses, fixed hypotheses against CODATA 2022 ----------
a22=137.035999177; u=0.000000021
pi=math.pi
aw=(9/(8*pi**4))*(pi**5/(2**4*math.factorial(5)))**0.25
wyler=1/aw
print(f"\nWyler alpha^-1 = {wyler:.9f}")
for name,v in [("Eddington136",136.),("Eddington137",137.),("Wyler",wyler)]:
    print(f"  {name}: delta={v-a22:+.9f}  = {(v-a22)/u:+,.0f} u(CODATA2022)")

# ---------- 5. Koide two branches ----------
me,mmu=0.51099895000,105.6583755
s=math.sqrt(me)+math.sqrt(mmu); M=me+mmu
disc=math.sqrt(6*s*s-3*M)
r1,r2=2*s+disc,2*s-disc
print(f"\nKoide roots for m_tau: {r1**2:.4f} MeV and {r2**2:.4f} MeV  (branch choice required)")
mt=1776.86; print("Q at reference mass:",(me+mmu+mt)/(math.sqrt(me)+math.sqrt(mmu)+math.sqrt(mt))**2)

# ---------- 6. Lambda conventions ----------
H0=67.4*1000/3.0856775814913673e22; OL=0.6847; c=299792458.0; lp=1.616255e-35
Lam=3*OL*H0**2/c**2
print(f"\nLambda={Lam:.4e} m^-2 ; Lambda*lp^2={Lam*lp**2:.4e} ; /(8pi)={Lam*lp**2/(8*pi):.4e}")

# ---------- 7. MOND ----------
a0=1.2e-10
for h in (67.4,73.0):
    hh=h*1000/3.0856775814913673e22; scale=c*hh/(2*pi)
    print(f"MOND H0={h}: cH0/2pi={scale:.4e} ; a0/(cH0/2pi)={a0/scale:.4f} ; a0/(cH0)={a0/(c*hh):.4f} vs 1/2pi={1/(2*pi):.4f}")

# ---------- 8. magic angle translation ----------
a_gr=0.246; kD=4*pi/(3*a_gr); w=0.11
for hv in (0.596,0.658):
    kth=w/(0.586*hv); th=2*math.asin(kth/(2*kD))*180/pi
    a_at_11=w/(hv*2*kD*math.sin(math.radians(1.1)/2))
    print(f"hv_F={hv} eV nm, w=110 meV: alpha=0.586 -> theta={th:.3f} deg ; theta=1.1deg -> alpha={a_at_11:.4f}")

# ---------- 9. Efimov, BKT, dims, Titius-Bode ----------
s0=1.00624; print(f"\nEfimov e^(pi/s0)={math.exp(pi/s0):.4f} ; residual={(21.0-math.exp(pi/s0))/1.3:.4f}")
print(f"BKT 2/pi={2/pi:.6f} ; dim so(32)={32*31//2} ; 2*dim(e8)={2*248}")
print("Titius-Bode vs actual:")
for name,n,act in [("Uranus",6,19.19),("Neptune",7,30.07),("Pluto",8,39.48)]:
    pred=0.4+0.3*2**n
    print(f"  {name}: predicted {pred:.1f} AU, actual {act:.2f} AU, error {(pred-act)/act*100:+.1f}%")


import math
from scipy.optimize import brentq
from fractions import Fraction
# ---- R_inf / R_H and Balmer ----
me=9.1093837015e-31;e=1.602176634e-19;h=6.62607015e-34;c=299792458;eps0=8.8541878128e-12;mp=1.67262192369e-27
Rinf=me*e**4/(8*eps0**2*h**3*c); RH=Rinf/(1+me/mp)
print("R_inf=%.6f  R_H=%.2f"%(Rinf,RH))
for n in (3,4): print("  Balmer n=%d: R_H %.2f nm | R_inf %.2f nm"%(n,1/(RH*(1/4-1/(n*n)))*1e9,1/(Rinf*(1/4-1/(n*n)))*1e9))
# ---- magic cumsum + partial sums ----
lv=[("1s1/2",2),("1p3/2",4),("1p1/2",2),("1d5/2",6),("2s1/2",2),("1d3/2",4),("1f7/2",8),
("2p3/2",4),("1f5/2",6),("2p1/2",2),("1g9/2",10),("1g7/2",8),("2d5/2",6),("2d3/2",4),("3s1/2",2),
("1h11/2",12),("1h9/2",10),("2f7/2",8),("2f5/2",6),("3p3/2",4),("3p1/2",2),("1i13/2",14)]
magic={2,8,20,28,50,82,126}; cum=0; parts=[]
for nm,d in lv:
    cum+=d; parts.append((cum,nm,cum in magic))
print("partial sums (cum,level,magic?):",[(p,nm,'M' if m else '-') for p,nm,m in parts])
# ---- decuplet (PDG nominal) ----
D,S,X,O=1232.,1385.,1531.8,1672.45
print("decuplet intervals:",S-D,X-S,O-X," extrapolated M_Omega=",X+(X-S))
# ---- Feigenbaum superstable, period=2^n ----
def iterate(r,p):
    x=0.5
    for _ in range(p): x=r*x*(1-x)
    return x
R=[2.0]
for n in range(1,9):
    p=2**n
    f=lambda r: iterate(r,p)-0.5
    R.append(brentq(f,R[-1]+1e-9,3.5699456718,xtol=1e-13))
print("superstable R:",[round(r,9) for r in R[:5]])
print("delta_n:",[round((R[n-1]-R[n-2])/(R[n]-R[n-1]),7) for n in range(2,9)])
# ---- Wyler ----
W=9/(8*math.pi**4)*(math.pi**5/(2**4*math.factorial(5)))**0.25
a2022=137.035999177; u=0.000000021
print("Wyler alpha^-1=%.9f  delta=%.9f = %.0f u"%(1/W,1/W-a2022,(1/W-a2022)/u))
# ---- Koide ----
me_,mmu=0.51099895000,105.6583755
S_=me_+mmu; T_=math.sqrt(me_)+math.sqrt(mmu)
def Q(mt): return (S_+mt)/(T_+math.sqrt(mt))**2
# roots of (S+x^2)=(2/3)(T+x)^2  -> x^2 -4T x + (3S-2T^2)=0 ... solve
import numpy as np
coef=[1/3, -4*T_/3, S_-2*T_*T_/3]  # (S+x^2)-(2/3)(T+x)^2=0 -> (1/3)x^2-(4T/3)x+(S-2T^2/3)
xs=np.roots([1/3,-4*T_/3,S_-2*T_*T_/3]); roots=sorted(x*x for x in xs if x>0)
print("Koide m_tau roots:",[round(r,4) for r in roots])
for mt,lab in [(1776.86,'PDG'),(1777.09,'BelleII')]:
    print("  Q(%s %.2f)=%.10f  |Q-2/3|=%.3e"%(lab,mt,Q(mt),abs(Q(mt)-2/3)))
dQ=(Q(1777.09)-Q(1776.86))/0.23
sigK=abs(dQ)*0.136
print("  dQ/dm_tau=%.3e/MeV  sigma_K(from 0.136)=%.3e  dev(BelleII)=%.2f sigma"%(dQ,sigK,abs(Q(1777.09)-2/3)/sigK))
print("  reference heavy root 1776.97 vs BelleII: %.2f sigma"%((1776.97-1777.09)/0.136))
# ---- Lambda, MOND, Efimov, 496 ----
H0=67.4/3.0856775814913673e19; OL=0.6847
Lam=3*H0**2*OL/c**2; lp=1.616255e-35
print("Lambda=%.4e m^-2  Lambda*lp^2=%.4e  /8pi=%.4e"%(Lam,Lam*lp*lp,Lam*lp*lp/(8*math.pi)))
a0=1.2e-10
for H in (67.4,73.0):
    Hs=H/3.0856775814913673e19; print("  MOND H0=%.1f: a0/(cH0/2pi)=%.4f  a0/(cH0)=%.4f"%(H,a0/(c*Hs/(2*math.pi)),a0/(c*Hs)))
s0=1.00624; print("Efimov e^(pi/s0)=%.4f  residual(21.0)=%.4f"%(math.exp(math.pi/s0),(21.0-math.exp(math.pi/s0))/1.3))
print("dim so(32)=",32*31//2," 2*dim E8=",2*248)
# ---- null model: Farey fractions in [0.5,0.9] ----
for qmax in (10,20):
    fr=sorted(set(Fraction(p,q) for q in range(1,qmax+1) for p in range(q+1) if 0.5<=p/q<=0.9))
    cover=len(fr)*6*sigK
    print("q<=%d: %d fractions, 3sigma-window coverage=%.2e"%(qmax,len(fr),cover))
# ---- Titius-Bode ----
act={'Uranus':19.19,'Neptune':30.07,'Pluto':39.48}; pred={'Uranus':0.4+0.3*2**6,'Neptune':0.4+0.3*2**7,'Pluto':0.4+0.3*2**8}
for k in act: print("  %s pred %.1f actual %.2f err %+.1f%%"%(k,pred[k],act[k],(pred[k]-act[k])/act[k]*100))


import math
from scipy.optimize import brentq
me=9.1093837015e-31;e=1.602176634e-19;h=6.62607015e-34;c=299792458;eps0=8.8541878128e-12;mp=1.67262192369e-27
Rinf=me*e**4/(8*eps0**2*h**3*c); RH=Rinf/(1+me/mp)
print("Balmer (corrected):")
for n in (3,4,5,6):
    print("  n=%d: R_H %.2f nm | R_inf %.2f nm"%(n,1e9/(RH*(0.25-1/(n*n))),1e9/(Rinf*(0.25-1/(n*n)))))
def iterate(r,p):
    x=0.5
    for _ in range(p): x=r*x*(1-x)
    return x
R=[2.0]
for n in range(1,11):
    R.append(brentq(lambda r: iterate(r,2**n)-0.5, R[-1]+1e-10, 3.56994567187, xtol=1e-14))
print("Feigenbaum delta_n (n=2..10):",[round((R[n-1]-R[n-2])/(R[n]-R[n-1]),8) for n in range(2,11)])
print("reference delta=4.669201609102990...")
# Koide precision-stress: sigma needed to resolve the 6.83e-6 deviation at 5 sigma
dev=6.829e-6; dQ=5.645e-5
print("m_tau precision to resolve dev at 5sigma: %.4f MeV (Belle II uncertainty 0.136)"%(dev/5/dQ))
print("Koide-exact m_tau=1776.969 vs BelleII 1777.09: separation %.2f sigma_now, %.1f sigma_at_0.0136MeV"%((1777.09-1776.969)/0.136,(1777.09-1776.969)/0.0136))

# Exact union of clipped intervals under a uniform control distribution.
farey_results = {}
for qmax in (10, 20):
    targets = sorted({Fraction(p,q) for q in range(1,qmax+1)
                      for p in range(q+1) if 0.5 <= p/q <= 0.9})
    end = 0.5
    length = 0.
    for target in targets:
        lo = max(0.5, float(target)-3*sigK, end)
        hi = min(0.9, float(target)+3*sigK)
        length += max(0., hi-lo)
        end = max(end, hi)
    farey_results[qmax] = dict(prior=[0.5,0.9], clipped_length=length, probability=length/0.4)
    print(f'Farey q<={qmax}: union length {length:.8g}, uniform probability {length/0.4:.8g}')
assert len(seen)==40 and len(uniq)==31
assert {x for x,v in mult.items() if v>1} == {2,8,10,12,18,20,32,40,50}
assert abs(Q(roots[-1])-2/3)<1e-14
from checks_export import export
export(globals())
