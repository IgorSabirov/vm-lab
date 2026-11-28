from itertools import product

# Движок восстановлен по включённому в подборку исходнику
# analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py (R130).
def left(u):  return u[1] if u[0]=='v' else ('l',u)
def right(u): return u[2] if u[0]=='v' else ('r',u)
def join(x,y):
    if x[0]=='l' and y[0]=='r' and x[1]==y[1]: return x[1]
    return ('v',x,y)
def mirror_name(u):
    if u[0]=='atom': return u
    if u[0]=='l': return right(mirror_name(u[1]))
    if u[0]=='r': return left(mirror_name(u[1]))
    return join(mirror_name(u[2]),mirror_name(u[1]))
def named(w): return tuple((('atom',i),s) for i,s in enumerate(w))
def canonical(x):
    return (frozenset(x), frozenset((x[i][0],x[(i+1)%len(x)][0]) for i in range(len(x))))
def equal(x,y): return canonical(x)==canonical(y)
def word(x): return tuple(s for u,s in x)
def cyclic(w): return min(w[i:]+w[:i] for i in range(len(w)))
def transport(x,channels=1,inverse=False):
    a=sum(1<<(2*c) for c in range(channels)); b=2*a
    return tuple((join(right(u),left(x[(i+1)%len(x)][0])),
                  ((s&a)|(x[(i+1)%len(x)][1]&b)) if inverse else ((s&b)|(x[(i+1)%len(x)][1]&a)))
                 for i,(u,s) in enumerate(x))
def interact(x,eps=(1,)):
    split={3<<(2*c):((1<<(2*c),2<<(2*c)) if e==1 else (2<<(2*c),1<<(2*c))) for c,e in enumerate(eps)}
    merge={v:k for k,v in split.items()}
    n=len(x)
    starts={i for i in range(n) if n>1 and (x[i][1],x[(i+1)%n][1]) in merge}
    ends={(i+1)%n for i in starts}
    start=next(i for i in range(n) if i not in ends)
    out,k=[],0
    while k<n:
        i=(start+k)%n; u,s=x[i]
        if i in starts:
            v,t=x[(i+1)%n]; out.append((join(u,v),merge[s,t])); k+=2
        elif s in split:
            a,b=split[s]; out.extend(((left(u),a),(right(u),b))); k+=1
        else: out.append((u,s)); k+=1
    return tuple(out)
def forward(x,eps=(1,)):  return transport(interact(x,eps),len(eps))
def backward(x,eps=(1,)): return interact(transport(x,len(eps),True),eps)
def swap_bits(x): return tuple((u,((s&1)<<1)|((s&2)>>1)) for u,s in x)
def reflected_swap(x): return tuple((mirror_name(u),s) for u,s in reversed(swap_bits(x)))
def r2(x): return tuple((u,((s&1)<<3)|((s&2)<<1)|((s&4)>>1)|((s&8)>>3)) for u,s in x)

import json
import numpy as np
import sympy as sp

def swap_bits2(x):
    return tuple((u,((s&1)<<1)|((s&2)>>1)|((s&4)<<1)|((s&8)>>1)) for u,s in x)
def Cp(x):
    return tuple((mirror_name(u),s) for u,s in reversed(swap_bits2(x)))
def densities(s):
    a,b,c,d=((s>>k)&1 for k in range(4))
    return (a,b,c,d,a*c,b*d)
def charges(x):
    return np.array([densities(s) for _,s in x], dtype=int).sum(axis=0)
def chi(x):
    c=charges(x); return int(c[4]-c[5])
def imbalance2(x):
    c=charges(x); return int(c[0]-c[1]+c[2]-c[3])
res={}
for eps in product((1,-1),repeat=2):
    cnt=dict(states=0,all_six_conserved_fail=0,chi_odd_Cp_fail=0,chi_odd_T_fail=0,q_odd_Cp_fail=0,q_odd_T_fail=0,CpT_charges_q_chi_preserved_fail=0)
    def T(x): return interact(r2(x),eps)
    for n in range(1,4):
        for w in product(range(16),repeat=n):
            x=named(w); cnt['states']+=1
            cnt['all_six_conserved_fail']+=int(not np.array_equal(charges(x),charges(forward(x,eps))))
            cnt['chi_odd_Cp_fail']+=int(chi(Cp(x))!=-chi(x))
            cnt['chi_odd_T_fail']+=int(chi(T(x))!=-chi(x))
            cnt['q_odd_Cp_fail']+=int(imbalance2(Cp(x))!=-imbalance2(x))
            cnt['q_odd_T_fail']+=int(imbalance2(T(x))!=-imbalance2(x))
            cnt['CpT_charges_q_chi_preserved_fail']+=int((chi(Cp(T(x))),imbalance2(Cp(T(x))))!=(chi(x),imbalance2(x)))
    res[str(eps)]=cnt
print('C2 exact finite checks:',json.dumps(res,ensure_ascii=False))
Q=sp.Matrix([densities(s) for s in range(16)])
bp=[((s&1)<<1)|((s&2)>>1)|((s&4)<<1)|((s&8)>>1) for s in range(16)]
rp=[int(f'{s:04b}'[::-1],2) for s in range(16)]
QB=sp.Matrix([densities(s) for s in bp]); QR=sp.Matrix([densities(s) for s in rp])
oddB=(QB+Q).nullspace(); oddR=(QR+Q).nullspace(); both=(QB+Q).col_join(QR+Q).nullspace()
print('Exact rational oddB basis:',[list(v) for v in oddB])
print('Exact rational oddR basis:',[list(v) for v in oddR])
print('Exact rational common basis:',[list(v) for v in both])
print('Q rank',Q.rank())

def N(w,a,b): return sum(w[i]==a and w[(i+1)%len(w)]==b for i in range(len(w)))
def J(w): return N(w,1,2)-N(w,2,1)
def Mm(w):
    return sum(tuple(w[(i+j)%len(w)] for j in range(4))==(0,1,0,1) for i in range(len(w)))-sum(tuple(w[(i+j)%len(w)] for j in range(4))==(1,0,1,0) for i in range(len(w)))
initial=dict(words=0,J_nonzero=0,Mm_nonzero=0,imbalance_fail=0,length_fail=0)
for n in range(3,9):
    for w in product(range(2),repeat=n):
        s=tuple(1+b for b in w); initial['words']+=1
        initial['J_nonzero']+=J(s)!=0;initial['Mm_nonzero']+=Mm(s)!=0
        x=named(s);y=forward(x)
        imb=lambda v:v.count(1)-v.count(2)
        initial['imbalance_fail']+=imb(word(y))!=imb(s)
        cx=named(tuple(3-v for v in reversed(s)))
        for t in range(4):
            x=forward(x);cx=forward(cx);initial['length_fail']+=len(x)!=len(cx)
print('Initial orientation block:',initial)
mask=dict(words=0,nonzero=0,M_odd_fail=0,B_odd_fail=0,C_even_fail=0)
for n in range(4,10):
    for w in product(range(2),repeat=n):
        Mw=tuple(reversed(w)); Bw=tuple(1-b for b in w); Cw=tuple(reversed(Bw));v=Mm(w)
        mask['words']+=1;mask['nonzero']+=v!=0
        mask['M_odd_fail']+=Mm(Mw)!=-v;mask['B_odd_fail']+=Mm(Bw)!=-v;mask['C_even_fail']+=Mm(Cw)!=v
print('Corrected mask:',mask)
# Nonvacuous C1 J checks including 0 and 3.
cj=dict(words=0,nonzero=0,M_odd_fail=0,B_odd_fail=0,C_even_fail=0,imbalance_conserved_fail=0)
for n in range(1,5):
    for w in product(range(4),repeat=n):
        Mw=tuple(reversed(w));Bw=tuple((0,2,1,3)[s] for s in w);Cw=tuple(reversed(Bw));v=J(w)
        cj['words']+=1;cj['nonzero']+=v!=0
        cj['M_odd_fail']+=J(Mw)!=-v;cj['B_odd_fail']+=J(Bw)!=-v;cj['C_even_fail']+=J(Cw)!=v
        y=word(forward(named(w)))
        cj['imbalance_conserved_fail']+=(y.count(1)-y.count(2))!=(w.count(1)-w.count(2))
print('Nonvacuous full C1 alphabet:',cj)
print('J witness:',(1,2,0),J((1,2,0)))
# Replay shape failure exactly.
arr=np.array(Q,dtype=float)
try:
    u,s,vh=np.linalg.svd((arr[bp]+arr).T)
    print('Failed block shapes:',(arr[bp]+arr).T.shape,'s',s.shape,'vh',vh.shape)
    z=vh[s<1e-10].conj().T
except Exception as e:
    print('Original error:',type(e).__name__,str(e))
res['orientation_initial']=initial;res['mask']=mask;res['nonvacuous_C1']=cj
res['exact_bases']={'oddB':[[int(i) for i in v] for v in oddB], 'oddR':[[int(i) for i in v] for v in oddR], 'common':[[int(i) for i in v] for v in both]}
from pathlib import Path
Path(__file__).with_name('results.json').write_text(json.dumps(res,ensure_ascii=False,indent=2))
