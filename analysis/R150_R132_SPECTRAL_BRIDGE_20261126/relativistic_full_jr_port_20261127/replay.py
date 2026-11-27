import json, csv, math
from pathlib import Path
from functools import lru_cache
import numpy as np
from scipy.linalg import eigh, eigh_tridiagonal
from scipy.optimize import brentq

OUT=Path(__file__).resolve().parent
N=6; M0=15.85; L0=19950.; T0=80.; HC=197326.9804
METHODS=('FD','Mathieu','spectral_hard','spectral_folded')
CONTACTS=((0,0,0),(2,1,0),(1.7,.35,.22),(2,1,.5),(-2,-1,.5),(5,5,3),(0,0,4))
BASE=(2,1,.5)
def scales(M=M0,ell=L0):
    J=HC**2/(2*M*ell**2); return J,J/N**2,np.pi**2*J

def band(q,s,pw=18,nlevels=1):
    n=np.arange(-pw,pw+1,dtype=float)
    return eigh_tridiagonal((q+2*n)**2+s/2,np.full(2*pw,-s/4),select='i',select_range=(0,nlevels-1),eigvals_only=True,check_finite=False)

@lru_cache(None)
def jr(s,pw=18,nq=8192,R=40):
    q=-1+2*(np.arange(nq)+.5)/nq
    e=np.array([band(x,s,pw)[0] for x in q])
    return -np.cos(np.pi*np.outer(np.arange(1,R+1),q))@e/nq

S0=brentq(lambda s:jr(s,18,4096,1)[0]-1/np.pi**2,2,5,xtol=2e-13)
J0,E0,ER0=scales()

def ring(m,phi,M,ell,s):
    J,Es,ER=scales(M,ell)
    th=(2*np.pi*np.arange(-3,3)+phi)/N
    U=np.exp(-1j*np.outer(np.arange(N),th))/np.sqrt(N)
    if m=='FD': k=2*J*(1-np.cos(th))
    elif m=='Mathieu': k=2*ER*(jr(s)@(1-np.cos(np.outer(np.arange(1,41),th))))
    elif m=='spectral_hard': k=J*th**2
    elif m=='spectral_folded': k=J*np.angle(np.exp(1j*th))**2
    else: raise ValueError(m)
    return (U*k)@U.conj().T,k

def f(x,M):
    a=1+2*x/M
    if np.min(a)<=0: raise ValueError('outside positive radicand domain')
    return 2*x/(np.sqrt(a)+1)

def fm(K,M):
    e,U=eigh(K); return (U*f(e,M))@U.conj().T

def calc(m,phi,ugh=BASE,M=M0,ell=L0,T=T0,s=S0,d=0.):
    J,Es,ER=scales(M,ell); R,k=ring(m,phi,M,ell,s)
    K=np.zeros((7,7),complex); K[1:,1:]=R+d*np.eye(6)
    u,g,h=ugh; V=np.zeros_like(K); V[0,0]=-u*Es; V[1,1]=-g*N*Es; V[0,1]=V[1,0]=h*np.sqrt(N)*Es
    x,U=eigh(K+V); e=f(x,M); w=np.exp(-(e-e.min())/T); pw=abs(U[0,:])**2
    P=float(pw@w/w.sum()); logZ=float(np.log(w.sum())-e.min()/T)
    H=fm(K+V,M); H0=fm(K,M); a,Q=eigh(K); r=np.sqrt(1+2*a/M)
    D=Q@((2/(r[:,None]+r[None,:]))*(Q.conj().T@V@Q))@Q.conj().T
    transfer=H-H0; norm=np.linalg.norm(transfer)
    if np.linalg.norm(V)==0: errors=[None,None,None]
    else:
        eps=1e-5
        dn=(fm(K+eps*V,M)-fm(K-eps*V,M))/(2*eps)
        errors=[float(np.linalg.norm(transfer-D)/norm),float(np.linalg.norm(transfer-V)/norm),float(np.linalg.norm(dn-D)/np.linalg.norm(D))]
    off=transfer[1:,1:].copy(); np.fill_diagonal(off,0)
    free=np.sort(f(k,M)); assert abs(pw.sum()-1)<1e-12
    return dict(P=P,logZ=logZ,levels=e.tolist(),gaps=np.diff(e).tolist(),port_weights=pw.tolist(),ring_levels=free.tolist(),ring_gaps=np.diff(free).tolist(),errors=errors,ring_offdiag_norm=float(np.linalg.norm(off)),radicand_min=float(np.min(1+2*x/M)),port_boltzmann_numerator=float(P*np.exp(logZ)))

def pair(m,ugh=BASE,**kw):
    a=calc(m,0,ugh,**kw); b=calc(m,np.pi,ugh,**kw)
    return dict(phi0=a,phipi=b,deltaP=a['P']-b['P'],C_Z=-np.expm1(b['logZ']-a['logZ']),C_port=1-a['P']/b['P'])

def sensitivities(m):
    # d in keV; perturb s=V0/ER at fixed M,ell.
    # Common perturbation: difference; differential (x0+=dx/2, xpi-=dx/2): half sum.
    res={}; eps=1e-4
    for name,base,step in [('d',0.,E0*eps),('s',S0,S0*eps),('T',T0,T0*eps),('M',M0,M0*eps),('ell',L0,L0*eps)]:
        g=[]
        for phi in (0,np.pi):
            p=calc(m,phi,**{name:base+step})['P']; q=calc(m,phi,**{name:base-step})['P']
            g.append((p-q)/(2*step)*(base if name!='d' else 1))
        res[name]=dict(per_phase=g,common=g[0]-g[1],differential=(g[0]+g[1])/2,coordinate=('keV' if name=='d' else 'ln '+name))
    a=pair(m); amp=abs(a['deltaP']); res['single_source_10pct_requirements']={name:{typ:(.1*amp/abs(row[typ]) if row[typ]!=0 else None) for typ in ('common','differential')} for name,row in res.items()}
    dx=1e-3; phase=[]
    for phi in (0,np.pi):
        p=calc(m,phi+dx)['P'];q=calc(m,phi-dx)['P'];o=calc(m,phi)['P']
        phase.append(dict(central_slope=(p-q)/(2*dx),left=(o-q)/dx,right=(p-o)/dx,curvature=(p+q-2*o)/dx**2))
    res['phase']=phase
    return res

def main():
    inputs=dict(N=N,M_keV=M0,ell_fm=L0,T_keV=T0,J_keV=J0,E_star_keV=E0,ER_keV=ER0,s=S0,V0_keV=S0*ER0,Jr_over_J1=(jr(S0)/jr(S0)[0]).tolist(),contact=BASE,reference='common band minimum relative to port; assumed')
    conv=[dict(pw=p,nq=q,J1_ER=jr(S0,p,q)[0],J6_J1=jr(S0,p,q)[5]/jr(S0,p,q)[0]) for p,q in [(12,4096),(16,4096),(18,8192),(22,8192)]]
    err=[]
    for ph in np.linspace(0,2*np.pi,33):
        k=ring('Mathieu',ph,M0,L0,S0)[1]; q=(2*np.arange(-3,3)/N+ph/(np.pi*N)+1)%2-1
        b=ER0*np.array([band(x,S0)[0]-band(0,S0)[0] for x in q]);err.append(float(np.max(abs(k-b))))
    cases={m:[dict(ugh=c,**pair(m,c)) for c in CONTACTS] for m in METHODS}
    phase_rows=[]; checks={}
    for m in METHODS:
        per=[]; tr=[]
        for ph in np.linspace(.07,2*np.pi-.07,65):
            p=calc(m,ph)['P']; per.append(abs(calc(m,ph+2*np.pi)['P']-p)); tr.append(abs(calc(m,-ph)['P']-p))
        checks[m]=dict(periodicity_max=max(per),time_reversal_max=max(tr))
        for ph in np.linspace(0,2*np.pi,129):
            q=calc(m,ph);phase_rows.append([m,ph,q['P'],q['logZ'],*q['levels'],*q['port_weights']])
    for m in ('FD','Mathieu','spectral_folded'):
        assert checks[m]['periodicity_max']<1e-12 and checks[m]['time_reversal_max']<1e-12
    assert checks['spectral_hard']['periodicity_max']>1e-4
    for ph in (0,np.pi):
        assert abs(calc('spectral_hard',ph)['P']-calc('spectral_folded',ph)['P'])<1e-12
    moments={m:[float(np.sum(ring(m,np.pi,M0,L0,S0)[1]**p)-np.sum(ring(m,0,M0,L0,S0)[1]**p)) for p in range(1,7)] for m in METHODS}
    sscan=[]
    for m in METHODS:
        for T in [40,60,80,100,120,.137*J0,.3*J0,.5*J0]:
            x=pair(m,T=T);sscan.append([m,'T_keV',T,x['deltaP'],x['C_Z'],x['C_port']])
        for d in np.array([-2,-1,-.5,0,.5,1,2])*E0:
            x=pair(m,d=d);sscan.append([m,'d_keV',d,x['deltaP'],x['C_Z'],x['C_port']])
        if m=='Mathieu':
            for fac in [.99,1,1.01]:
                x=pair(m,s=S0*fac);sscan.append([m,'s/s0',fac,x['deltaP'],x['C_Z'],x['C_port']])
    # Scalar Mathieu multiband f thermal diagnostic: free ring, no physical interband contact map.
    mb=[]
    for nb in (1,2,4,8,16,32,64,96,128):
        z=[]
        for phi in (0,np.pi):
            q=(2*np.arange(-3,3)/N+phi/(np.pi*N)+1)%2-1
            en=ER0*(np.concatenate([band(x,S0,72,nb) for x in q])-band(0,S0)[0]);z.append(float(np.exp(-f(en,M0)/T0).sum()))
        mb.append(dict(bands=nb,free_ring_C=1-z[1]/z[0],reference_port_iso_C=1-(1+z[1])/(1+z[0]),Z0=z[0],Zpi=z[1]))
    cutoff=[]
    for n in (6,12,24,48,96,192,384,768):
        z=[]
        for phi in (0,np.pi):
            a=(2*np.pi*np.arange(-n//2,n//2)+phi)/n
            en=f(E0*n*n*np.angle(np.exp(1j*a))**2,M0);z.append(1+np.exp(-en/T0).sum())
        cutoff.append([n,float(1-z[1]/z[0])])
    sens={m:sensitivities(m) for m in METHODS}
    data=dict(inputs=inputs,convergence=conv,band_matrix_error_max_keV=max(err),cases=cases,symmetry=checks,moments=moments,parameter_sweeps=sscan,sensitivities=sens,multiband_free_diagnostic=mb,spectral_fixed_C_free_port_cutoff=cutoff,physical_covariance=None,physical_anchor='OPEN',scientific_acceptance=False)
    (OUT/'RESULTS.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    for fn,head,rows in [('PHASE_SWEEP.csv',['method','phi','P','logZ']+[f'E{i}' for i in range(7)]+[f'port_w{i}' for i in range(7)],phase_rows),('PARAMETER_SWEEPS.csv',['method','parameter','value','deltaP','C_Z','C_port'],sscan)]:
        with (OUT/fn).open('w',newline='') as f_: w=csv.writer(f_);w.writerow(head);w.writerows(rows)
    for m in METHODS:
        x=cases[m][3]; print(m, 'P0/Ppi',x['phi0']['P'],x['phipi']['P'],'dP',x['deltaP'],'CZ/Cp',x['C_Z'],x['C_port'],'symmetry',checks[m], 'errors phi0',x['phi0']['errors'])
        print('  gaps pi',x['phipi']['gaps']);print('  10pct requirements',sens[m]['single_source_10pct_requirements']);print('  phase',sens[m]['phase'])
    print('s',S0,'band error',max(err),'multiband',mb);print('spectral fixed C',cutoff)
if __name__=='__main__': main()
