"""Analytic mass errors, phase sensitivity and active-gap optimum."""
import math, json
from scipy.optimize import brentq


def mass_checks():
    me,mmu=0.51099895,105.6583755
    out={}
    for tau,err in [(1776.86,.12),(1776.93,.09)]:
        masses=[me,mmu,tau]
        roots=[math.sqrt(m) for m in masses]
        S,M=sum(roots),sum(masses)
        Q=M/S**2
        grad=[(S-M/r)/S**3 for r in roots]
        sigma=abs(grad[-1])*err
        out[tau]=dict(Q=Q,sigma_tau_only=sigma,z=(Q-2/3)/sigma,gradient=grad)
    def ratio(theta):
        M=sorted((1+math.sqrt(2)*math.cos(theta+2*math.pi*k/3))**2 for k in range(3))
        return M[1]/M[0]
    fixed=2/9
    mu_e=206.7682827
    sigma=4.6e-6
    fit=brentq(lambda th:ratio(th)-mu_e,.221,.223,xtol=1e-15)
    return dict(Koide=out,ratio_at_2over9=ratio(fixed),sigma_distance=(ratio(fixed)-mu_e)/sigma,
                theta_fit=fit,theta_minus_fixed=fit-fixed)


def gaps():
    out=[]
    for L in range(5,102,2):
        n=L-1; m=n//2
        g=2*math.sin(2*math.pi/n)
        mu=g/(m+2)
        masses=[((2*u-1+m)%L)-m for u in range(2,L)]
        # Exclude the analytically known exact zeros only; sine at pi is rounded.
        levels=[abs(mu*v+2*math.sin(2*math.pi*j/n)) for v in masses for j in range(n)
                if v!=0 or j not in (0,n//2)]
        measured=min(levels)
        target=2*mu
        assert abs(measured-target)<3e-15
        out.append(dict(L=L,optimum_mu=mu,gap=target,scaled=L**2*target))
    return out


if __name__=='__main__':
    print(json.dumps(dict(masses=mass_checks(),active_gap=gaps()),indent=2))
