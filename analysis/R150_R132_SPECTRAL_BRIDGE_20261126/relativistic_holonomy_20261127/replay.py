"""Replay conditional R150 free/port/ensemble and contact relativistic contrasts.
numpy, mpmath; stdout JSON. No fitting or BBN input.
"""
import json, numpy as np, mpmath as m
m.mp.dps=70
M,l,hc,T=map(m.mpf,['15.85','19950','197326.9804','80'])
N=6; J=hc**2/(2*M*l*l); E=J/N**2
f=lambda x:m.sqrt(M*M+2*M*x)-M
def ev(n,p,j,rel):
    a=[4*j*m.sin((2*m.pi*k+p)/(2*n))**2 for k in range(n)]
    return list(map(f,a)) if rel else a
def stats(a,t):
    w=[m.exp(-x/t) for x in a];z=sum(w)
    return z,sum(x*y for x,y in zip(a,w))/z
def obs(a,b,t=T):
    z,u=stats(a,t);y,v=stats(b,t)
    return (z-y)/z,t*m.log(z/y),v-u
s=lambda x:m.nstr(x,24)
def trip(a,b,t=T):return list(map(s,obs(a,b,t)))
r={'M_keV':s(M),'ell_fm':s(l),'J_keV':s(J),'Estar_keV':s(E),'T_keV':s(T),'precision_dps':70,'units':['contrast','deltaF_keV','deltaU_keV']}
for rel in (False,True):
    a,b=[ev(N,p,J,rel) for p in (0,m.pi)];p=ev(N+1,0,J,rel);a0=[0]+a;b0=[0]+b
    aa=sorted(set(round(float(x),12) for x in a));bb=sorted(set(round(float(x),12) for x in b))
    r['rel' if rel else 'nr']={'free':trip(a,b),'iso':trip(a0,b0),'all':trip(p*13+a0*5,p*13+b0*5),'one':trip(p*13+a0*5,p*13+a0*4+b0),'moments_pi_minus_0':[s(sum(x**k for x in b)-sum(x**k for x in a)) for k in range(1,7)],'T_scan':[[t,s(obs(a,b,m.mpf(t))[0]),s(obs(a0,b0,m.mpf(t))[0])] for t in (20,40,60,80,100,160,320)],'ratios':[(bb[2]-bb[1])/(bb[1]-bb[0]),(aa[3]-aa[2])/(aa[2]-aa[1])],'fixed_C':[[n,*trip([0]+ev(n,0,E*n*n,rel),[0]+ev(n,m.pi,E*n*n,rel))] for n in (6,12,24,48,96,192,384,768)]}
for cut in (1024,2048,4096):
    r['continuum_rel_'+str(cut)]=trip([0]+[f(E*(2*m.pi*k)**2) for k in range(-cut,cut+1)],[0]+[f(E*(2*m.pi*(k+m.mpf('.5')))**2) for k in range(-cut,cut)])
def za(p,cut=1024):
    q=[2*m.pi*k+p for k in range(-cut,cut+1)]
    x=[E*y*y for y in q]; w=[m.exp(-f(t)/T) for t in x]
    return 1+sum(w),sum(v*E*y**4*M/(12*T*m.sqrt(M*M+2*M*t)) for y,t,v in zip(q,x,w))
z,a=za(0);y,b=za(m.pi);c=1-y/z;A=y*a/z**2-b/z
r['fixed_C_thermal_A']=s(A)
r['fixed_C_thermal_check']=[[n,s(n*n*(obs([0]+ev(n,0,E*n*n,True),[0]+ev(n,m.pi,E*n*n,True))[0]-c))] for n in (192,384,768,1536,3072)]
q=m.exp(-T/(4*E));r['continuum_nr_iso']=s(4*q*m.sqrt(T/(4*m.pi*E))/(1+m.sqrt(T/(4*m.pi*E))))
M0,E0,J0,T0=map(float,(M,E,J,T))
ff=lambda x:np.sqrt(M0*M0+2*M0*x)-M0
r['contacts']=[]
for u,g,h in ((0,0,0),(1.7,.35,.22),(2,1,.5),(-2,-1,.5),(5,5,3),(0,0,4)):
    zs=[]
    for phi in (0,np.pi):
        S=np.roll(np.eye(N,dtype=complex),1,axis=0);S[0,-1]=np.exp(1j*phi)
        K=np.zeros((N+1,N+1),complex);K[1:,1:]=J0*(2*np.eye(N)-S-S.conj().T)
        V=np.zeros_like(K);V[0,0]=-u*E0;V[1,1]=-g*N*E0;V[0,1]=V[1,0]=h*np.sqrt(N)*E0
        a,Q=np.linalg.eigh(K);b=np.linalg.eigvalsh(K+V);assert min(M0*M0+2*M0*b)>0
        H=(Q*ff(a))@Q.conj().T+V
        zs.append([np.exp(-x/T0).sum() for x in (b,np.linalg.eigvalsh(H),ff(b))])
    r['contacts'].append([u,g,h,*list(1-np.array(zs[1])/np.array(zs[0]))])
r['shifts']=[[i,*trip([f(E*i)]+[f(x+E*i) for x in ev(N,0,J,False)],[f(E*i)]+[f(x+E*i) for x in ev(N,m.pi,J,False)])] for i in (-5,0,5,10,20)]
def logC(lm,ll,lt):
    mass,ell,t=map(m.exp,(lm,ll,lt));j=hc**2/(2*mass*ell*ell)
    def en(p):return [0]+[m.sqrt(mass*mass+2*mass*x)-mass for x in ev(N,p,j,False)]
    return m.log(obs(en(0),en(m.pi),t)[0])
r['log_derivatives']=[s(m.diff(logC,(m.log(M),m.log(l),m.log(T)),tuple(int(i==k) for i in range(3)))) for k in range(3)]
a,b=ev(N,0,J,False),ev(N,m.pi,J,False)
def D(t):
    if t<m.mpf('.01'):
        return 4*N*m.exp(-2*J*t)*sum(m.besseli(k*N,2*J*t) for k in (1,3,5,7,9))
    return sum(m.exp(-t*x) for x in a)-sum(m.exp(-t*x) for x in b)
integ=m.sqrt(M/(2*m.pi))*m.quad(lambda t:m.exp(-M*t/2)*D(t)/t**m.mpf('1.5'),[0,m.mpf('.01'),m.mpf('.1'),1,m.inf])
assert abs(integ-(sum(map(f,b))-sum(map(f,a))))<m.mpf('1e-45')
assert abs(sum(x**N for x in b)-sum(x**N for x in a)+4*N*J**N)<m.mpf('1e-55')
r['subordination_integral']=s(integ)
hp=6.62607015e-34;charge=1.602176634e-19;me=9.1093837015e-31;amu=1.66053906660e-27;hb=hp/(2*np.pi);phi0=hp/charge
r['donors']={'AB':[[b,float(np.sqrt(phi0/(np.pi*b))*1e9)] for b in (.075,.074,.061)],'Fuhrer_Estar_microeV':hb**2/(2*.067*me*(832.429e-9)**2)/charge*1e6,'sigma_Estar':np.sqrt(.01**2+4*.005**2+4*.45*.01*.005),'Kriisa_conditional_sigma':np.sqrt((.0003/.067)**2+4*.005**2),'Debbarma_mass_conditional':12/290,'atomic_Er_h':[[name,rad,hp/(8*np.pi**2*mass*amu*(rad*1e-6)**2)] for name,mass,rad in [('Na23',22.989769282,19.5),('Rb87',86.909180531,12),('Rb87',86.909180531,19.5)]],'PST_MHz':[np.sqrt(k*(6-k))/(4*640e-9)/1e6 for k in range(1,6)]}
print(json.dumps(r,indent=2,ensure_ascii=False))
