"""Eight nuclides with R150 sources. All energies in MeV and frequencies in s^-1."""
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
from scipy.integrate import solve_ivp, cumulative_trapezoid
from scipy.special import expit
from graph import contacts, relic, TREF, HBAR, MPL

ROOT=Path(__file__).resolve().parent
A=np.array([1,1,2,3,3,4,7,7])
OBS=('Yp','D_H','He3_H_late','Li7_H_late')
KB9=0.08617333262145
BD=2.224566
# Basis forms a partition of unity in log T. Order: cold to hot.
KNOTS=np.array([.005,.025,.045,.06,.07,.08,.10,.16,.50,8.7])


@dataclass(frozen=True)
class Config:
    layer: str='B'
    mode: str='off'         # off, direct, mediator, algebraic, imposed
    L: int=3
    comoving_J: bool=False  # internal R proportional to a with J=j/R
    J: float=.08233
    lam: float=-.00725131
    tau: float=50.          # mediator relaxation time in reference seconds
    S: float=50.            # constant barrier; optionally S=c*J/T
    thermal_c: float=0.
    reverse: bool=False    # n_D drives mediator
    forward: bool=True     # mediator shifts network rates
    full_contact: bool=False  # include diagonal shift; default relative to pinned pi
    Ec: float=.10          # curvature energy per domain
    domains_per_baryon: float=1.
    p_initial: float=.5
    filling: float=1.
    forward_np_power: float=0.  # diagnostic multiplier (B_D/B_D0)^power
    clock: float=1.        # dt' = clock dt, all rates / clock
    graph_clock: float=1.   # extra multiplier for graph rates only
    relic_background: bool=False
    gdec: float=202.
    gx: float=1.
    # Optional branch free energy difference F_1-F_0 per domain (MeV), table vs T.
    profile_file: str=''    # imposed two-column T_MeV,deltaBD_MeV table
    branch_file: str=''
    window_H: str=''       # independent H-basis control
    basis: int=-1
    pulse_MeV: float=0.
    rtol: float=2.e-8


class History:
    def __init__(self):
        common=ROOT/'data'/'common'
        record=json.loads((common/'canonical.json').read_text())
        h=record['history']
        self.t=np.array(h['time_s'])
        self.a=np.array(h['scale_factor'])
        self.T=np.array(h['T_gamma_MeV'])
        self.Tnu=np.array(h['T_nu_MeV'])
        self.H=np.array(h['H_s_inv'])
        self.logt=np.log(self.t)
        self.logT=np.log(self.T)
        plasma=np.load(common/'plasma.npz')
        self.logrho=np.log(plasma['rho_b_g_cm3'])
        self.tw=plasma['weak_T_MeV']
        self.wp=plasma['n_to_p_s_inv']
        self.wn=plasma['p_to_n_s_inv']
        self.alpha,self.beta,self.gamma=np.load(common/'rate_parameters.npz')['reverse_alpha_beta_gamma']
        rs=record['rates']['reactions']
        self.names=[r['id'] for r in rs]
        assert self.names[0]=='npdg'
        species=record['rates']['species']
        self.axis=np.unique(np.concatenate([r['T9'] for r in rs]))
        assert all(r['T9'][0] == self.axis[0] and r['T9'][-1] == self.axis[-1] for r in rs)
        self.table=np.array([np.interp(self.axis,r['T9'],r['values']) for r in rs]).T
        def tokens(side):
            return [[species.index(k) for k,n in r[side].items() for _ in range(n)] for r in rs]
        lhs,rhs=tokens('reactants'),tokens('products')
        self.sto=np.array([np.bincount(v,minlength=8)-np.bincount(u,minlength=8) for u,v in zip(lhs,rhs)]).T
        assert np.all(A@self.sto==0)
        self.li,self.lj=np.array(lhs).T
        self.ri=np.array([v[0] for v in rhs])
        self.rj=np.array([v[-1] if len(v)==2 else 8 for v in rhs])
        self.two=self.rj!=8
        self.lsym=np.where(self.li==self.lj,.5,1.)
        self.rsym=np.where(self.ri==self.rj,.5,1.)
        reference=np.load(common/'linx.npz')
        self.times=reference['time_s']
        self.initial=reference['Y'][0]
        self.reference=json.loads((common/'observables.json').read_text())

    def forward_rates(self,T):
        t9=T/KB9
        if not self.axis[0]<=t9<=self.axis[-1]:
            return np.zeros(len(self.names))
        i=min(max(1,np.searchsorted(self.axis,t9)),len(self.axis)-1)
        a=(t9-self.axis[i-1])/(self.axis[i]-self.axis[i-1])
        return self.table[i-1]*(1-a)+self.table[i]*a


def output(y):
    return dict(zip(OBS,map(float,[4*y[5],y[2]/y[1],(y[3]+y[4])/y[1],(y[6]+y[7])/y[1]])))


def solve(h,c,save=None):
    if c.mode not in ('off','direct','mediator','algebraic','imposed') or c.window_H not in ('','early','late'):
        raise ValueError('Unknown mode or H window')
    if min(c.tau,c.domains_per_baryon,c.Ec,c.clock,c.graph_clock,c.rtol,c.gdec,c.gx)<=0:
        raise ValueError('Time scales, positive physical inputs and tolerances must be positive')
    if not 0<=c.filling<=1 or not 0<=c.p_initial<=1 or c.basis not in range(-1,len(KNOTS)):
        raise ValueError('Population, filling or basis out of range')
    if c.reverse and c.mode not in ('mediator','algebraic'):
        raise ValueError('Backreaction requires dynamical or algebraically eliminated medium')
    T_limits=np.exp(np.interp(np.log(h.times[[0,-1]]),h.logt,h.logT))
    profile=None
    if c.profile_file:
        profile=np.loadtxt(c.profile_file,delimiter=',',skiprows=1,ndmin=2)
        if (c.mode!='imposed' or profile.shape[1]!=2 or np.any(np.diff(profile[:,0])<=0)
                or profile[0,0]>T_limits[-1]*(1+1e-12) or profile[-1,0]<T_limits[0]*(1-1e-12)):
            raise ValueError('Imposed profile must cover all T and be strictly ascending')
    start,end=h.times[[0,-1]]
    # Graph in contact with photon bath in all coupled network runs.
    tref_a=np.exp(np.interp(np.log(TREF),h.logT[::-1],np.log(h.a[::-1])))
    J_series=c.J*tref_a/h.a if c.comoving_J else np.full_like(h.T,c.J)
    if c.comoving_J:
        if c.relic_background: raise ValueError("A varying internal J requires an independent relic mass history")
        graph_table=np.column_stack([contacts(c.L,j,c.lam,[T],c.layer)[:,0] for T,j in zip(h.T,J_series)])
    else:
        graph_table=contacts(c.L,c.J,c.lam,h.T,c.layer)
    bias,diag,mix,c0,cpi=graph_table
    if c.branch_file:
        data=np.loadtxt(c.branch_file,delimiter=',',skiprows=1,ndmin=2)
        if data.shape[1]!=2 or np.any(np.diff(data[:,0])<=0) or data[0,0]>h.T[-1] or data[-1,0]<h.T[0]:
            raise ValueError('Branch table needs ascending T_MeV and complete range')
        bias-=np.interp(h.T,data[:,0],data[:,1])/h.T
    diag=c.filling*diag if c.full_contact else diag*0
    mix=c.filling*mix
    tn_ref=np.interp(np.log(TREF),h.logT[::-1],h.Tnu[::-1])
    tx=(10.75/c.gdec)**(1/3)*tn_ref*tref_a/h.a
    if c.relic_background:
        rx,px=relic(tx,2*c.J,c.gx)
    else:
        rx,px=np.zeros_like(tx),np.zeros_like(tx)
    baseline_rho=3*(HBAR*h.H*MPL)**2/(8*np.pi)
    speed=np.sqrt(1+rx/baseline_rho)
    grid=np.column_stack([h.logT,h.logrho,bias,diag,mix,speed,J_series])
    def state(t):
        u=np.log(t)
        i=np.clip(np.searchsorted(h.logt,u),1,len(h.logt)-1)
        w=(u-h.logt[i-1])/(h.logt[i]-h.logt[i-1])
        return grid[i-1]*(1-w)+grid[i]*w
    basis_weights=np.eye(len(KNOTS))[c.basis]
    def evaluate(t,y,details=False,jac=False):
        lt,lr,b,d,m,sp,J_local=state(t)
        T=np.exp(lt)
        rho=np.exp(lr)
        p,z=y[8:10]
        drive=d+p*m
        target=drive
        if c.reverse:
            target+=c.Ec*y[2]/c.domains_per_baryon
        if c.mode=='algebraic':
            z=target
        if c.mode in ('algebraic','mediator'):
            # Partial derivative of the per-domain quadratic potential at fixed z.
            b+=(z-drive)*m/(c.Ec*T)
        delta=0.
        if c.mode=='direct' and c.forward:
            delta=drive
        if c.mode in ('algebraic','mediator') and c.forward:
            delta=z
        if c.mode=='imposed':
            shape=1. if c.basis<0 else np.interp(lt,np.log(KNOTS),basis_weights)
            delta=c.pulse_MeV*shape if profile is None else np.interp(lt,np.log(profile[:,0]),profile[:,1])
        if c.window_H=='early' and .2<=T<=2.:
            sp*=1.003
        if c.window_H=='late' and .02<=T<=.2:
            sp*=1.0055
        action=c.thermal_c*J_local/T if c.thermal_c else c.S
        wr=c.graph_clock*J_local/HBAR*np.exp(-action)
        # Stable direct calculation of each direction. dQ = net_D * deltaB.
        f=h.forward_rates(min(T,h.axis[-1]*KB9*(1-1e-15))) if rates_on else np.zeros(len(h.names))
        if c.forward_np_power:
            if delta<=-BD: raise ValueError('unbound deuteron outside portal')
            f[0]*=(1+delta/BD)**c.forward_np_power
        t9=T/KB9
        rev=f*h.alpha*t9**h.beta*np.exp(h.gamma/t9-h.sto[2]*delta/T)
        if details:
            C=(1-p)*np.interp(lt,h.logT[::-1],cpi[::-1])+p*np.interp(lt,h.logT[::-1],c0[::-1])
            return [T,p,z,drive,delta,C,wr,sp,rho*f[0]*y[1]/c.clock,rev[0]/c.clock]
        aux=np.r_[y[:8],1.]
        if jac:
            ff=rho*h.lsym*f
            bb=np.where(h.two,rho,1.)*h.rsym*rev
            dnet=np.zeros((len(f),9))
            indices=np.arange(len(f))
            dnet[indices,h.li]+=ff*y[h.lj]
            dnet[indices,h.lj]+=ff*y[h.li]
            dnet[indices,h.ri]-=bb*aux[h.rj]
            dnet[indices,h.rj]-=bb*aux[h.ri]
            M=np.zeros((10,10))
            M[:8,:8]=h.sto@dnet[:,:8]
            wn,wp=np.interp(T,h.tw,h.wn),np.interp(T,h.tw,h.wp)
            M[:2,:2]+=np.array([[-wp,wn],[wp,-wn]])
            flux_B=bb*aux[h.ri]*aux[h.rj]*h.sto[2]/T
            if c.forward_np_power:
                flux_B[0]+=c.forward_np_power/(BD+delta)*(ff[0]*y[0]*y[1]-bb[0]*y[2])
            if c.mode in ('direct','algebraic') and c.forward:
                M[:8,8]=h.sto@flux_B*m
                if c.mode=='algebraic' and c.reverse:
                    M[:8,2]+=h.sto@flux_B*c.Ec/c.domains_per_baryon
            if c.mode=='mediator' and c.forward:
                M[:8,9]=h.sto@flux_B
            if c.mode in ('direct','algebraic','mediator'):
                M[8,8]=-wr
            if c.mode=='algebraic' and c.reverse:
                M[8,2]=wr*expit(b)*expit(-b)*m/(c.domains_per_baryon*T)
            if c.mode=='mediator':
                susceptibility=wr*expit(b)*expit(-b)*m/(c.Ec*T)
                M[8,8]-=susceptibility*m
                M[8,9]=susceptibility
                M[9,8]=m/c.tau
                M[9,9]=-1/c.tau
                if c.reverse: M[9,2]=c.Ec/(c.domains_per_baryon*c.tau)
            return M/(sp*c.clock)
        net=(rho*h.lsym*f*y[h.li]*y[h.lj] -
             np.where(h.two,rho,1.)*h.rsym*rev*aux[h.ri]*aux[h.rj])
        dy=h.sto@net
        weak=np.interp(T,h.tw,h.wp)*y[0]-np.interp(T,h.tw,h.wn)*y[1]
        dy[0]-=weak
        dy[1]+=weak
        dp=wr*(expit(b)-p) if c.mode in ('direct','algebraic','mediator') else 0.
        dz=(target-z)/c.tau if c.mode=='mediator' else 0.
        # Independent variable equals reported physical time in a common-clock run.
        return np.r_[dy,dp,dz]/(sp*c.clock)
    y0=np.r_[h.initial,c.p_initial,diag[0]+c.p_initial*mix[0]]
    times=h.times*c.clock
    # The tabulated nuclear rates switch on discontinuously at T9=10.
    # Integrate each smooth segment from zero elapsed time to resolve that stiff layer.
    cuts=[h.axis[-1]*KB9]
    if c.window_H=='early': cuts += [.2,2.]
    if c.window_H=='late': cuts += [.02,.2]
    cut_times=np.exp(np.interp(np.log(cuts),h.logT[::-1],h.logt[::-1]))
    edges=sorted([start,*cut_times,end])
    pieces=[]
    evaluations=0
    for i,(left,right) in enumerate(zip(edges,edges[1:])):
        rates_on=state((left+right)/2)[0] <= np.log(h.axis[-1]*KB9)
        span=(right-left)*c.clock
        selected=h.times[(h.times>=left if i==0 else h.times>left)&(h.times<=right)]
        requested=(selected-left)*c.clock
        sample=np.unique(np.r_[requested,span])
        sol=solve_ivp(lambda u,y:evaluate(left+u/c.clock,y),(0.,span),y0,method='BDF',
                      jac=lambda u,y:evaluate(left+u/c.clock,y,jac=True),
                      t_eval=sample,rtol=c.rtol,atol=np.r_[np.full(8,c.rtol*1e-7),c.rtol*.01,c.rtol*1e-4])
        if not sol.success or sol.t[-1]!=span or not np.isfinite(sol.y).all():
            raise RuntimeError(f'{sol.message}, segment {left} to {right} s')
        evaluations+=sol.nfev
        pieces.append(sol.y[:,:len(selected)].T)
        y0=sol.y[:,-1]
    y=np.concatenate(pieces)
    err=np.max(np.abs(y[:,:8]@A-1))
    if err>1e-7 or np.min(y[:,:8])<-1e-11 or y[:,8].min()<-1e-7 or y[:,8].max()>1+1e-7:
        raise ArithmeticError('Population invariant failed')
    diagnostics=[]
    for t,row in zip(h.times,y):
        rates_on=state(t)[0]<=np.log(h.axis[-1]*KB9)
        diagnostics.append(evaluate(t,row,True))
    diagrow=np.array(diagnostics)
    T=diagrow[:,0]
    actual_time=np.r_[start,start+cumulative_trapezoid(1/diagrow[:,7],h.times)]*c.clock
    report=dict(**output(y[-1]),max_baryon_error=err,nfev=evaluations,
                peak_YD=float(max(y[:,2])),peak_YD_T_MeV=float(T[y[:,2].argmax()]))
    if save:
        logt=np.log(h.times)
        bg=lambda v:np.interp(logt,h.logt,v)
        # Radioactive T and Be7 are included in late He3/H and Li7/H.
        matrix=np.column_stack([h.times,actual_time,diagrow,y[:,:8],bg(h.Tnu),bg(h.H)*diagrow[:,7]/c.clock,
                                bg(rx),bg(px),np.zeros((len(y),2))])
        header='background_t_s,elapsed_clock_s,Tgamma_MeV,p_periodic,z_MeV,drive_MeV,deltaBD_MeV,C_mean,Gamma_r_reference_s_inv,H_ratio,capture_per_n_s_inv,photo_per_D_s_inv,n,p,D,t,He3,He4,Li7,Be7,Tnu_MeV,H_s_inv,rhoX_MeV4,pX_MeV4,Qgamma_MeV4_per_s,Qnu_MeV4_per_s'
        np.savetxt(save,matrix,delimiter=',',header=header,comments='')
    return report
