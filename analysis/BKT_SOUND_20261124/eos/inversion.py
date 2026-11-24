"""Infer superfluid phase-space density from the two measured sound speeds."""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq, minimize_scalar
from scipy.special import spence
from scipy.constants import hbar, k as kB, atomic_mass

HERE = Path(__file__).resolve().parent
MASS = 38.9637064864 * atomic_mass
D0 = 2*np.pi*hbar**2*3e12/(MASS*kB*42e-9)
CUT = 3.841458820694124

class DomainError(ValueError):
    """The density table or the thermodynamic stability conditions do not apply."""

def hf_pressure(x, g):
    # x(D) = gD/pi + log(1-exp(-D)); P tends to zero with D.
    density = brentq(lambda d:g*d/np.pi+np.log(-np.expm1(-d))-x, 1e-12, 80)
    return spence(np.exp(-density)) + g*density**2/(2*np.pi)

class EquationOfState:
    def __init__(self, g=.64, anchor=0., theta=None, omit_inner=False):
        X, tab, _ = np.loadtxt(HERE/'theta.csv',delimiter=',',skiprows=1).T
        tab = tab if theta is None else theta
        if omit_inner:
            keep = abs(X) >= .06
            X,tab = X[keep],tab[keep]
        self.g = g
        self.X = X
        self.dc = np.log(380/g)
        self.xc = g/np.pi*np.log(13.2/g)
        self.anchor = anchor
        self.curve = PchipInterpolator(X,X+tab,extrapolate=False)
        self.offset = self.dc - np.pi*self.curve(0.)
        self.integral = self.curve.antiderivative()
        self.slope = self.curve.derivative()
        self.pref = hf_pressure(self.xc+g*anchor,g)

    def density(self,X):
        return self.offset + np.pi*self.curve(X)

    def pressure(self,X):
        return self.pref + self.g*(self.offset*(X-self.anchor)
                    +np.pi*(self.integral(X)-self.integral(self.anchor)))

    def state(self,D):
        if not self.density(self.X[0]) <= D <= self.density(self.X[-1]):
            raise DomainError('density outside theta table')
        X=brentq(lambda z:self.density(z)-D,self.X[0],self.X[-1])
        return self.at_X(X)

    def at_X(self,X):
        D=self.density(X)
        x=self.xc+self.g*X
        P=self.pressure(X)
        deriv=np.pi*self.slope(X)/self.g
        entropy=2*P/D-x
        cv=2*P/D-D/deriv
        if np.any(np.minimum.reduce([P,deriv,cv,entropy])<=0):
            raise DomainError('pressure, compressibility, heat capacity or entropy nonpositive')
        # kBT/(m cB²) = 2pi/(gD). A and B are the adiabatic and
        # isothermal squared speeds; H multiplies ns/(n-ns) in the quartic.
        unit=2*np.pi/(self.g*D)
        return State(D,X,x,P,deriv,entropy,cv,unit*2*P/D,unit*D/deriv,unit*entropy**2/cv)

@dataclass(frozen=True)
class State:
    D:float
    X:float
    x:float
    pressure:float
    D_prime:float
    entropy:float
    cv:float
    A:float
    B:float
    H:float

    def speeds(self,z):
        # z = c20/cB. Stable evaluation for small second roots.
        z=np.asarray(z)
        total=self.A+z*z
        splitting=np.sqrt((self.A-z*z)**2 + 4*z*z*(self.A-self.B))
        fast=np.sqrt((total+splitting)/2)
        slow=z*np.sqrt(self.B)/fast
        return fast,slow

    def Ds(self,z):
        return float(self.D*z*z/(self.H+z*z))

def components(state, measured, sigma, rho=0., profile=True):
    u,v=measured; su,sv=sigma
    def objective(z):
        fast,slow=state.speeds(z)
        a=(fast-u)/su; b=(slow-v)/sv
        return a*a + (b-rho*a)**2/(1-rho*rho)
    # fastest hydrodynamic root >= z; outside this domain even the
    # marginal fast-mode residual exceeds the loss at zero plus CUT.
    upper=max(u+su*np.sqrt(objective(0.)+CUT)+.01,1.)
    mesh=np.linspace(0.,upper,161)
    scores=objective(mesh)
    candidates=[(scores[0],0.),(scores[-1],upper)]
    for idx in np.flatnonzero((scores[1:-1]<=scores[:-2]) & (scores[1:-1]<=scores[2:]))+1:
        fit=minimize_scalar(objective,bounds=(mesh[idx-1],mesh[idx+1]),method='bounded',
                            options={'xatol':2e-11})
        candidates.append((float(fit.fun),float(fit.x)))
    chi,z=min(candidates)
    if not profile: return state.Ds(z)
    grid=np.unique(np.r_[mesh,[q for _,q in candidates]])
    mask=objective(grid)<=chi+CUT
    ends=[0.] if mask[0] else []
    for i in np.flatnonzero(mask[:-1]!=mask[1:]):
        ends.append(brentq(lambda zz: objective(zz)-chi-CUT,grid[i],grid[i+1]))
    if mask[-1]: ends.append(upper)
    ds_intervals=[[state.Ds(a),state.Ds(b)] for a,b in np.reshape(ends,(-1,2))]
    fast,slow=state.speeds(z)
    via_sum=u*u+v*v-state.A
    via_prod=(u*v)**2/state.B
    return dict(Ds=state.Ds(z),ns_over_n=state.Ds(z)/state.D,interval95=ds_intervals,
                chi2=chi,fit_speeds=[fast,slow],residual_sigma=[(fast-u)/su,(slow-v)/sv],
                Ds_sum=state.Ds(np.sqrt(via_sum)) if via_sum>=0 else None,
                Ds_product=state.Ds(np.sqrt(via_prod)),c20sq_sum=via_sum,c20sq_product=via_prod)

def evaluate(row, *, scales=(1.,1.,1.,1.), temperature=None,rho=0., relative_axis=False,
             eos=None, profile=False):
    n,T,q,g_scale=scales
    temp=row['T_over_Tc'] if temperature is None else temperature
    g=.64*g_scale
    eos=EquationOfState(g) if eos is None else eos
    if not np.isclose(eos.g,g): raise ValueError('inconsistent coupling')
    D=(eos.dc if relative_axis else D0*n/T)/temp
    state=eos.state(D)
    # Hold observed lab frequencies fixed for shared calibration changes.
    factor=1/(q*np.sqrt(n*g_scale))
    y=factor*np.array([row['c1'],row['c2']])
    sigma=factor*np.array([row['err_c1'],row['err_c2']])
    result=components(state,y,sigma,rho,profile)
    return (result,state) if profile else result
