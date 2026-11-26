#!/usr/bin/env python3
"""R132-R133-R150 two-contact continuum-limit audit. Requires numpy and scipy."""
from __future__ import annotations
import json
import math
import numpy as np
from scipy.optimize import brentq
from scipy.special import logsumexp

PI = math.pi
SOURCE_GRAPH = "analysis/R150_THREE_GENERATIONS/floquet/phase_bbn/network_bench/graph.py"
SOURCE_BLOB = "579e7ff62318f0e40c0ac707b6790bb7f0208bd6"


def required_levels(y: float, g: float) -> int:
    return max(48, int(math.sqrt(60.0*y)/(2.0*PI))+16, int(abs(g))+16)


def cycle_spectrum(phi: float, g: float, levels: int = 80) -> np.ndarray:
    """Spectrum of -d2/dx2-g*delta_0 on a unit circle with twist phi."""
    anti = abs(phi-PI) < 1e-12
    if abs(g) < 1e-14:
        if anti:
            return np.array([((2*n+1)*PI)**2 for n in range(levels+1) for _ in (0,1)])
        return np.array([0.0]+[(2*PI*n)**2 for n in range(1,levels+1) for _ in (0,1)])
    e = []
    if not anti:
        e.extend((2*PI*n)**2 for n in range(1,levels+1))
        if g > 0:
            k = brentq(lambda x: 2*x*math.tanh(x/2)-g, 1e-12, max(12.0,g+2), xtol=2e-14)
            e.append(-k*k)
            intervals = [((2*n-1)*PI,2*n*PI) for n in range(1,levels+1)]
        else:
            intervals = [(2*n*PI,(2*n+1)*PI) for n in range(levels)]
        for a,b in intervals:
            q = brentq(lambda x: x*math.tan(x/2)+g/2, a+1e-10,b-1e-10,xtol=2e-14)
            e.append(q*q)
    else:
        e.extend(((2*n+1)*PI)**2 for n in range(levels+1))
        if g > 4:
            k = brentq(lambda x: 2*x/math.tanh(x/2)-g,1e-12,max(12.0,g+2),xtol=2e-14)
            e.append(-k*k)
            intervals = [(2*n*PI,(2*n+1)*PI) for n in range(1,levels+1)]
        elif g > 0:
            if abs(g-4)<1e-13:
                e.append(0.0)
                intervals = [(2*n*PI,(2*n+1)*PI) for n in range(1,levels+1)]
            else:
                intervals = [(2*n*PI,(2*n+1)*PI) for n in range(levels)]
        else:
            intervals = [((2*n+1)*PI,(2*n+2)*PI) for n in range(levels)]
        for a,b in intervals:
            q = brentq(lambda x: x/math.tan(x/2)-g/2,a+1e-10,b-1e-10,xtol=2e-14)
            e.append(q*q)
    return np.sort(np.asarray(e,dtype=float))


def log_xi(phi: float,u: float,g: float,y: float,levels: int|None=None)->float:
    if not (y>0 and math.isfinite(y)):
        raise ValueError("y must be finite and positive")
    e=cycle_spectrum(phi,g,required_levels(y,g) if levels is None else levels)
    return float(logsumexp(np.r_[u/y,-e/y]))


def phi_iso(u:float,g:float,y:float)->float:
    return y*(log_xi(0.0,u,g,y)-log_xi(PI,u,g,y))


def finite_cycle(n:int,phi:float,g:float)->np.ndarray:
    if n<3:
        raise ValueError("n must be >=3")
    a=np.zeros((n,n))
    for j in range(n-1):
        a[j,j+1]=a[j+1,j]=1.0
    twist=1.0 if abs(phi)<1e-12 else -1.0
    a[0,n-1]=a[n-1,0]=twist
    a[0,0]+=g/n
    return np.sort(n*n*(2-np.linalg.eigvalsh(a)))


def finite_log_xi(n:int,phi:float,u:float,g:float,y:float)->float:
    return float(logsumexp(np.r_[u/y,-finite_cycle(n,phi,g)/y]))


def passive_log_trace(n:int,y:float)->float:
    k=np.arange(n+1,dtype=float)
    e=4*n*n*np.sin(PI*k/(n+1))**2
    return float(logsumexp(-e/y))


def finite_full(n:int,u:float,g:float,y:float)->tuple[float,float]:
    x0=finite_log_xi(n,0,u,g,y)
    xp=finite_log_xi(n,PI,u,g,y)
    lp=math.log(2*n+1)+passive_log_trace(n,y)
    la=math.log(n-1)
    z0=float(logsumexp([lp,la+x0]))
    za=float(logsumexp([lp,la+xp]))
    zo=float(logsumexp([lp,math.log(n-2)+x0,xp]))
    return y*(z0-za), n*y*(z0-zo)


def c0(y:float)->float:
    n=np.arange(-100,101,dtype=float)
    return float(np.exp(-4*PI*PI*n*n/y).sum())


def full_limit(u:float,g:float,y:float)->tuple[float,float]:
    x0=log_xi(0,u,g,y); xp=log_xi(PI,u,g,y); c=c0(y)
    all_value=y*(float(logsumexp([math.log(2*c),x0]))-float(logsumexp([math.log(2*c),xp])))
    one_value=y*(math.exp(x0)-math.exp(xp))/(2*c+math.exp(x0))
    return all_value,one_value


def ground(g:float)->tuple[float,float]:
    return float(cycle_spectrum(0,g,8)[0]),float(cycle_spectrum(PI,g,8)[0])


def audit()->dict:
    cases=[(0.,0.,3.),(1.,2.,3.),(5.,5.,3.),(-10.,-2.,4.),(0.,4.,2.)]
    isolated=[]
    for u,g,y in cases:
        target=phi_iso(u,g,y); rows=[]
        for n in (32,64,128,256):
            v=y*(finite_log_xi(n,0,u,g,y)-finite_log_xi(n,PI,u,g,y))
            rows.append({"N":n,"Phi_N":v,"abs_error":abs(v-target)})
        e0,ep=ground(g)
        isolated.append({"u_p":u,"g_c":g,"y":y,"Phi_continuum":target,"e0":e0,"e_pi":ep,"finite_N":rows})
    full=[]
    for u,g,y in ((1.,2.,3.),(5.,5.,3.),(-10.,-2.,4.)):
        al,one=full_limit(u,g,y); rows=[]
        for n in (32,64,128,256):
            an,on=finite_full(n,u,g,y)
            rows.append({"N":n,"N2_M_all_over_J":an,"N3_M_one_over_J":on,
                         "all_abs_error":abs(an-al),"one_abs_error":abs(on-one)})
        full.append({"u_p":u,"g_c":g,"y":y,"Phi_all":al,"Psi_one":one,"finite_N":rows})
    regime=[]
    for gt in (-2.,0.,2.,4.,5.,10.):
        e0,ep=ground(gt)
        regime.append({"g_c":gt,"e0":e0,"e_pi":ep,"mixed_u_interval":[-ep,-e0]})
    grid=[{"g_c":gt,"values":[{"u_p":u,"y":3.,"Phi":phi_iso(u,gt,3.)}
          for u in (-8.,-4.,-2.,0.,2.,4.,8.)]} for gt in (-2.,0.,2.,4.,5.)]
    u,g,y=1.,2.,3.; h=1e-4; p=phi_iso(u,g,y)
    py=(phi_iso(u,g,y+h)-phi_iso(u,g,y-h))/(2*h)
    pu=(phi_iso(u+h,g,y)-phi_iso(u-h,g,y))/(2*h)
    pg=(phi_iso(u,g+h,y)-phi_iso(u,g-h,y))/(2*h)
    threshold=[]
    for n in (8,16,32,64):
        threshold.append({"N":n,"Emin_g4":float(finite_cycle(n,PI,4.)[0]),
                          "Emin_g3p99":float(finite_cycle(n,PI,3.99)[0]),
                          "Emin_g4p01":float(finite_cycle(n,PI,4.01)[0])})
    residuals=[]
    for gt in (-2.,0.,2.,4.,5.):
        for ph in (0.,PI):
            vals=cycle_spectrum(ph,gt,24); rr=[]
            for en in vals[vals>1e-12]:
                q=math.sqrt(float(en)); rr.append(abs(math.cos(ph)-math.cos(q)+gt*math.sin(q)/(2*q)))
            for en in vals[vals<-1e-12]:
                k=math.sqrt(float(-en)); rr.append(abs(math.cos(ph)-math.cosh(k)+gt*math.sinh(k)/(2*k)))
            residuals.append({"g_c":gt,"phi":ph,"max_residual":max(rr,default=0.)})
    iso_err=max(x["abs_error"] for r in isolated for x in r["finite_N"])
    all_err=max(x["all_abs_error"] for r in full for x in r["finite_N"])
    one_err=max(x["one_abs_error"] for r in full for x in r["finite_N"])
    assert all(all(r["finite_N"][i+1]["abs_error"]<r["finite_N"][i]["abs_error"] for i in range(3)) for r in isolated)
    assert all(all(r["finite_N"][i+1]["all_abs_error"]<r["finite_N"][i]["all_abs_error"] and
                   r["finite_N"][i+1]["one_abs_error"]<r["finite_N"][i]["one_abs_error"] for i in range(3)) for r in full)
    assert max(r["max_residual"] for r in residuals)<1e-9
    return {
      "schema":"r132-r133-r150-two-contact-continuum-v1",
      "status":"ANALYTICAL_LIMIT_DERIVED; FINITE_N_HEAT_TRACE_CONVERGENCE_NUMERICALLY_CHECKED; PHYSICAL_EMBEDDING_CONDITIONAL",
      "source_definition":{"source":SOURCE_GRAPH,"source_blob":SOURCE_BLOB,
       "finite_operator":"A_phi,N=(2+u_p/N^2) direct_sum (S_phi,N+S_phi,N^dagger+(g_c/N)|0><0|)",
       "relative_operator":"K_phi,N=N^2(2I-A_phi,N)=(-u_p) direct_sum (N^2(2I-S-S^dagger)-g_c*N*P0)",
       "observable":"M=F_pi-F_0=T*ln(Z_0/Z_pi); Phi=N^2*M/J; y=N^2*T/J"},
      "continuum":{"operator":"K_phi,g=(-d^2/dx^2)-g_c*delta_0 on unit circle with twist phi",
       "spectrum_equation":"cos(phi)=cos(q)-(g_c/(2*q))*sin(q)",
       "bound_state_equation":"cos(phi)=cosh(kappa)-(g_c/(2*kappa))*sinh(kappa); E=-kappa^2",
       "bound_states":{"phi_0":"one iff g_c>0; g_c=2*kappa*tanh(kappa/2)",
        "phi_pi":"one iff g_c>4; g_c=2*kappa*coth(kappa/2); g_c=4 threshold",
        "g_c<0":"no bound state"},
       "thermodynamic_trace":"Xi_phi=exp(u_p/y)+sum_E exp(-E/y)",
       "universal_function":"Phi_iso=y*ln(Xi_0/Xi_pi)",
       "full_carrier":{"all":"Phi_all=y*ln[(2*C0+Xi_0)/(2*C0+Xi_pi)]",
        "one":"Psi_one=lim N^3*M_one/J=y*(Xi_0-Xi_pi)/(2*C0+Xi_0)",
        "C0":"sum_n exp(-4*pi^2*n^2/y)","ensemble":"R150 direct sum, not tensor product"}},
      "isolated_convergence":isolated,"full_carrier_convergence":full,
      "ground_state_regime_map":regime,"phi_grid_y3":grid,
      "thermodynamic_witness":{"point":{"u_p":u,"g_c":g,"y":y},"Phi":p,"dPhi_dy":py,
        "DeltaS_over_kB":-py,"DeltaU_over_Estar":p-y*py,"dPhi_dup":pu,"dPhi_dg":pg,
        "identity":"DeltaU/E*=Phi-y*partial_y Phi; DeltaS/kB=-partial_y Phi"},
      "finite_N_threshold_check":threshold,"continuum_secular_equation_checks":residuals,
      "checks":{"isolated_heat_trace_max_abs_error_N32_to_256":iso_err,
       "full_all_max_abs_error_N32_to_256":all_err,"full_one_max_abs_error_N32_to_256":one_err,
       "antiperiodic_bound_threshold_exact_g":4.,"port_eigenvalue_exact":"-u_p",
       "finite_operator_hermitian":True,
       "continuum_secular_max_abs_residual":max(r["max_residual"] for r in residuals),
       "selected_refinement_errors_decrease_monotonically":True},
      "physical_scaling":{"fixed_circumference":"ell_X=N*a_N",
       "J_N_over_N2":"E_star=hbar^2/(2*m_X*ell_X^2)","T_N":"y*E_star",
       "lambda_p_N":"u_p*E_star (finite)",
       "lambda_c_N":"g_c*E_star*N; Gamma=lambda_c*a_N=g_c*E_star*ell_X (finite)",
       "renormalized_energy":"H_ren=H+2*J_N*I; absolute band edge diverges without anchor",
       "response":"dM/dlambda_p=dPhi/du_p; dM/dGamma=(1/ell_X)*dPhi/dg_c"},
      "provenance":{"method":"independent NumPy/SciPy finite matrices and continuum roots",
       "tested_N":[8,16,32,64,128,256],"no_BBN":True,"no_abundance_fit":True,
       "no_physical_calibration":True,"no_PRIMAT_LINX_run":True}
    }


if __name__=="__main__":
    print(json.dumps(audit(),ensure_ascii=False,indent=2,sort_keys=True))
