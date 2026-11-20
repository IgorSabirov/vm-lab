"""P5: O(3) critical profiles, explicit rate prefactors and wall response.

Conventions: canonical field phi in MeV, potential V in MeV^4, radius in
MeV^-1, constant positive gradient coefficient Z, S3 in MeV. The O(3)
shooting/collocation equation is Z(phi''+2 phi'/r)=dV/dphi.
References: https://arxiv.org/abs/1109.4189 (bounce boundary problem),
https://arxiv.org/abs/1004.4187 (ideal-fluid wall flux matching).
The implemented scalar action is a specified effective model; an EOS alone
neither supplies that action nor its dynamical prefactor or wall friction.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from .common import InputError, OpenInput, read_json, write_json

import numpy as np
from numpy.polynomial import Polynomial
from scipy.integrate import simpson, solve_bvp, solve_ivp
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq


class NucleationDomainError(InputError):
    pass


def thin_wall(T_MeV, delta_p_MeV4, sigma_MeV3):
    T,dp,sigma=map(float,(T_MeV,delta_p_MeV4,sigma_MeV3))
    if not all(math.isfinite(x) and x>0 for x in (T,dp,sigma)):
        raise InputError("thin-wall formula requires positive T, driving pressure and surface tension")
    return {"critical_radius_MeV_inv":2*sigma/dp,
            "S3_MeV":16*math.pi*sigma**3/(3*dp**2),
            "S3_over_T":16*math.pi*sigma**3/(3*T*dp**2)}


def bounce_o3(coefficients, phi_false_MeV, phi_true_MeV, phi_barrier_MeV,
              radius_max_MeV_inv, gradient_Z=1.0, mesh_points=801,
              tolerance=1e-6, max_nodes=30000):
    """Solve a nontrivial single-field O(3) bounce with a shooting seed.

    Overshoot/undershoot brackets the central field in logarithmic distance
    from the true vacuum. A singular-term collocation solve then enforces
    phi'(0)=0 and phi(Rmax)=phi_false, avoiding unstable late-time shooting.
    A truncated or unresolved thin-wall solution is rejected. Return raw
    profile and Derrick/virial residual for independent mesh/radius checks.
    """
    coeff=np.asarray(coefficients,float)
    if coeff.ndim!=1 or len(coeff)<4 or not np.all(np.isfinite(coeff)):
        raise InputError("bounce potential needs finite polynomial coefficients")
    pot=Polynomial(coeff); dpot=pot.deriv(); d2pot=pot.deriv(2)
    false,true,barrier,R,Z=map(float,(phi_false_MeV,phi_true_MeV,phi_barrier_MeV,radius_max_MeV_inv,gradient_Z))
    if not all(math.isfinite(v) for v in (false,true,barrier,R,Z)) or true==false or R<=0 or Z<=0:
        raise InputError("invalid bounce domain or gradient coefficient")
    delta=true-false; ub=(barrier-false)/delta
    if not 0<ub<1 or d2pot(false)<=0 or d2pot(true)<=0 or d2pot(barrier)>=0:
        raise InputError("false/true minima and intervening maximum must be explicitly ordered")
    field_scale=max(abs(delta),1)
    potential_scale=max(abs(pot(barrier)-pot(false)),abs(pot(true)-pot(false)),1e-100)
    if max(abs(dpot(false)),abs(dpot(true)),abs(dpot(barrier))) > 1e-6*potential_scale/field_scale:
        raise InputError("specified stationary points do not solve V'=0")
    if pot(true)>=pot(false):
        raise InputError("true vacuum is not below false vacuum")
    if mesh_points<101 or tolerance<=0 or max_nodes<mesh_points:
        raise InputError("invalid bounce numerical resolution")
    mass=math.sqrt(float(d2pot(false))/Z)
    if R*mass<8:
        raise NucleationDomainError("bounce radius domain does not contain a controlled false-vacuum tail")
    r0=min(1e-5/mass,R*1e-7)
    def force(u): return dpot(false+delta*u)/(Z*delta)
    def shoot(logdef):
        u0=1-math.exp(logdef)
        f0=float(force(u0))
        def rhs(r,y): return [y[1],float(force(y[0]))-2*y[1]/r]
        def crossed(r,y): return y[0]
        crossed.terminal=True;crossed.direction=-1
        def turned(r,y): return y[1]
        turned.terminal=True;turned.direction=1
        sol=solve_ivp(rhs,(r0,R),[u0+f0*r0*r0/6,f0*r0/3],method="DOP853",
                      rtol=max(tolerance*.02,2e-12),atol=max(tolerance*1e-5,1e-13),
                      max_step=R/(mesh_points-1),events=(crossed,turned),dense_output=True)
        if not sol.success:
            raise RuntimeError("bounce shooting integration failed: "+sol.message)
        if len(sol.t_events[0]): return -1,sol
        if len(sol.t_events[1]): return 1,sol
        return 0,sol
    lo=math.log(8*np.finfo(float).eps)
    hi=math.log((1-ub)*(1-1e-6))
    signlo,slo=shoot(lo);signhi,shi=shoot(hi)
    if signhi != 1:
        raise NucleationDomainError("cannot find undershoot; enlarge radius domain or check potential")
    if signlo != -1:
        raise NucleationDomainError("thin-wall central deficit/radius unresolved; refine precision or import an independent kernel")
    seed=None
    for _ in range(58):
        mid=(lo+hi)/2; sign,trial=shoot(mid)
        seed=trial
        if sign==0:
            break
        if sign<0: lo=mid
        else: hi=mid
        if abs(hi-lo)<max(tolerance*.001,2e-12):
            break
    radius=np.linspace(0,R,mesh_points)
    initial=np.empty((2,mesh_points))
    end=float(seed.t[-1])
    inside=(radius>=r0)&(radius<=end)
    initial[:,inside]=seed.sol(radius[inside])
    initial[:,radius<r0]=np.asarray(seed.y[:,0])[:,None]
    # Beyond the shooting event the approximate profile is continued to the
    # false vacuum. Collocation replaces this seed; it is not used for action.
    initial[:,radius>end]=0
    initial[1,0]=0
    def fun(r,y): return np.vstack([y[1],force(y[0])])
    def bc(ya,yb): return np.array([ya[1],yb[0]])
    solved=solve_bvp(fun,bc,radius,initial,S=np.array([[0,0],[0,-2.0]]),
                     tol=tolerance,max_nodes=max_nodes)
    if not solved.success:
        raise RuntimeError("O(3) collocation failed: "+solved.message)
    radius=np.linspace(0,R,max(mesh_points,2*len(solved.x)+1))
    u,up=solved.sol(radius)
    if u[0]<=ub or np.min(u)<-10*tolerance or np.max(u)>1+10*tolerance or np.max(np.diff(u))>10*tolerance:
        raise RuntimeError("O(3) solver converged to a trivial or nonmonotone solution")
    phi=false+delta*u; derivative=delta*up
    grad=4*math.pi*simpson(radius**2*(.5*Z*derivative**2),x=radius)
    potential=4*math.pi*simpson(radius**2*(pot(phi)-pot(false)),x=radius)
    action=float(grad+potential)
    virial=abs(grad+3*potential)/max(abs(grad),abs(3*potential),1e-300)
    tail_index=int(.9*len(radius))
    tail_relative=float(abs(u[tail_index])/max(abs(u[0]),1e-300))
    if action<=0 or virial>max(.01,100*tolerance) or tail_relative>max(1e-4,100*tolerance):
        raise NucleationDomainError("O(3) profile fails action/virial/tail checks; increase radius or resolution")
    def crossing(level): return float(np.interp(level,u[::-1],radius[::-1]))
    return {"radius_MeV_inv":radius,"phi_MeV":phi,"dphi_dr_MeV2":derivative,
            "S3_MeV":action,"gradient_action_MeV":float(grad),"potential_action_MeV":float(potential),
            "virial_relative_residual":float(virial),"tail_relative":tail_relative,
            "half_height_radius_MeV_inv":crossing(.5*u[0]),
            "wall_thickness_10_90_MeV_inv":crossing(.1*u[0])-crossing(.9*u[0]),
            "mesh_nodes":len(solved.x),"radius_max_MeV_inv":R}


class Kernel:
    """Positive rate from independent action/prefactor tables, no extrapolation."""
    def __init__(self,spec):
        self.spec=spec.copy()
        if not spec.get("source") or not spec.get("prefactor_source"):
            raise OpenInput("nucleation action and dimensional prefactor need separate sources")
        self.T=np.asarray(spec["T_MeV"],float)
        action=np.asarray(spec["S3_over_T"],float)
        prefactor=np.asarray(spec["prefactor_MeV4"],float)
        if self.T.ndim!=1 or len(self.T)<2 or action.shape!=self.T.shape or prefactor.shape!=self.T.shape:
            raise InputError("nucleation arrays need matching one-dimensional shapes")
        if not all(np.all(np.isfinite(x)) for x in (self.T,action,prefactor)) or np.any(self.T<=0) or np.any(np.diff(self.T)<=0) or np.any(action<0) or np.any(prefactor<=0):
            raise InputError("invalid nucleation table")
        self.action=PchipInterpolator(self.T,action,extrapolate=False)
        self.logprefactor=PchipInterpolator(self.T,np.log(prefactor),extrapolate=False)
        self.minimum=float(self.T[0]);self.maximum=float(self.T[-1])

    @classmethod
    def from_dict(cls,spec): return cls(spec.get("definition",spec))

    def at(self,T_MeV):
        t=float(T_MeV)
        if not math.isfinite(t) or not self.minimum<=t<=self.maximum:
            raise NucleationDomainError("nucleation temperature outside independently supplied kernel")
        action=float(self.action(t));logA=float(self.logprefactor(t));logGamma=logA-action
        return {"S3_over_T":action,"prefactor_MeV4":math.exp(logA),"log_Gamma_MeV4":logGamma,
                "Gamma_MeV4":math.exp(logGamma) if logGamma>-745 else 0.0}


def hydrodynamic_match(e_plus,p_plus,e_minus,p_minus):
    """Stationary planar ideal-fluid jump, in the rest frame of the wall.

    A returned pair conserves energy/momentum flux. This algebra neither
    chooses detonation/deflagration globally nor supplies microscopic friction.
    """
    ep,pp,em,pm=map(float,(e_plus,p_plus,e_minus,p_minus))
    if not all(math.isfinite(x) for x in (ep,pp,em,pm)) or min(ep+pp,em+pm)<=0:
        raise InputError("fluid enthalpies must be positive")
    if ep==em or em+pp==0 or ep+pm==0:
        raise InputError("degenerate hydrodynamic jump")
    product=(pp-pm)/(ep-em); ratio=(em+pp)/(ep+pm)
    vp2=product*ratio;vm2=product/ratio
    if not 0<vp2<1 or not 0<vm2<1:
        raise NucleationDomainError("provided thermodynamic states have no physical stationary subluminal jump")
    vp,vm=math.sqrt(vp2),math.sqrt(vm2)
    energy_plus=(ep+pp)*vp/(1-vp2);energy_minus=(em+pm)*vm/(1-vm2)
    momentum_plus=(ep+pp)*vp2/(1-vp2)+pp;momentum_minus=(em+pm)*vm2/(1-vm2)+pm
    return {"v_plus":vp,"v_minus":vm,
            "energy_flux_residual_MeV4":energy_plus-energy_minus,
            "momentum_flux_residual_MeV4":momentum_plus-momentum_minus}


class FrictionWall:
    """Declared local pressure/friction and heat-conduction constitutive law.

    delta_p is p_cold(T_X)-p_hot(T_X). The first-order local correction is
    delta_p_front=delta_p-L*(T_front-T_X)/T_ref. The pressure balance is
    eta*gamma*v=delta_p_front. q=kappa*(T_front-T_X) is an independent flux
    into the bulk; P7 must evolve its reciprocal energy balance. eta in MeV^4,
    kappa in MeV^3. The allowed v and temperature difference are mandatory
    model-validity inputs. This is not an automatically matched fluid shell.
    """
    def __init__(self,spec):
        self.spec=spec.copy()
        for key in ("friction_source","conductivity_source","domain_source"):
            if not spec.get(key): raise OpenInput(f"wall requires {key}")
        self.eta=float(spec["friction_MeV4"]);self.kappa=float(spec["conductivity_MeV3"])
        self.Tref=float(spec["reference_temperature_MeV"])
        self.max_v=float(spec["max_abs_speed"]);self.max_delta=float(spec["max_relative_temperature_difference"])
        self.minimum,self.maximum=map(float,spec["T_range_MeV"])
        if not all(math.isfinite(x) for x in (self.eta,self.kappa,self.Tref,self.max_v,self.max_delta,self.minimum,self.maximum)) or min(self.eta,self.kappa,self.Tref,self.max_delta,self.minimum)<=0 or not 0<self.max_v<1 or self.maximum<=self.minimum:
            raise InputError("invalid wall coefficients or applicability domain")

    @classmethod
    def from_dict(cls,spec):return cls(spec.get("definition",spec))

    def speed(self,T_X,T_front,delta_p,latent_heat):
        TX,TF,dp,L=map(float,(T_X,T_front,delta_p,latent_heat))
        if not all(math.isfinite(x) for x in (TX,TF,dp,L)) or L<0:
            raise InputError("invalid current wall state")
        if not self.minimum<=TX<=self.maximum or not self.minimum<=TF<=self.maximum or abs(TF-TX)/self.Tref>self.max_delta:
            raise NucleationDomainError("wall response outside declared thermal domain")
        driving=dp-L*(TF-TX)/self.Tref
        v=driving/math.hypot(self.eta,driving)
        if abs(v)>self.max_v:
            raise NucleationDomainError("wall speed outside calibrated constitutive law")
        friction=self.eta*v/math.sqrt(1-v*v)
        return {"v":v,"heat_flux_MeV4":self.kappa*(TF-TX),
                "driving_pressure_MeV4":driving,"friction_pressure_MeV4":friction,
                "pressure_balance_residual_MeV4":driving-friction,
                "latent_flux_MeV4":L*v}

    def steady_speed(self,T_X,delta_p,latent_heat):
        """Quasistationary front: kappa(T_front-T_X)=L*v, solved jointly.

        The interface stores no independent energy in this approximation.
        Its domain and adequacy require independent evidence for a physical
        application; the full released latent heat belongs in the bulk balance.
        """
        TX,dp,L=map(float,(T_X,delta_p,latent_heat))
        if not all(math.isfinite(x) for x in (TX,dp,L)) or L<0:
            raise InputError("invalid steady wall state")
        def residual(v):
            drive=dp-L*L*v/(self.kappa*self.Tref)
            return self.eta*v/math.sqrt(1-v*v)-drive
        bound=1-1e-12
        v=brentq(residual,-bound,bound,xtol=1e-14)
        TF=TX+L*v/self.kappa
        result=self.speed(TX,TF,dp,L)
        result["T_front_MeV"]=TF
        result["heat_balance_residual_MeV4"]=result["heat_flux_MeV4"]-result["latent_flux_MeV4"]
        return result

    def pocket_contraction(self,radius_MeV_inv,sigma_MeV3,T_X,T_front,delta_p,latent_heat):
        R=float(radius_MeV_inv);sigma=float(sigma_MeV3)
        if R<=0 or sigma<0 or not math.isfinite(R+sigma):
            raise InputError("invalid old-phase pocket curvature")
        result=self.speed(T_X,T_front,delta_p+2*sigma/R,latent_heat)
        result["d_radius_dt_natural"]=-result["v"]
        result["curvature_pressure_MeV4"]=2*sigma/R
        return result


def run(config,inputs,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    from .gravitationalwaves import source_artifact
    (out/"gw_source.json").write_text(json.dumps(
        source_artifact(config.get("gw_source"),config.get("_key")),
        indent=2,allow_nan=False)+"\n")
    donor_selected="donor_thin_wall" in config
    if donor_selected and ("nucleation" in inputs or "nucleation" in config):
        raise InputError("choose donor_thin_wall or an independent nucleation definition, not both")
    if not donor_selected and "nucleation" not in inputs and "nucleation" not in config:
        raise OpenInput("P5 requires an action/prefactor kernel or effective scalar action")
    if "wall" not in inputs and "wall" not in config:
        raise OpenInput("P5 requires independently specified wall transport coefficients")
    if donor_selected:
        from .donor_inputs import load_prepared, thin_wall_control
        prepared,binding=load_prepared(inputs)
        spec=thin_wall_control(prepared,config["donor_thin_wall"])
        spec["prepared_input"]=binding
        write_json(out/"donor_thin_wall_control.json",spec)
    else:
        spec=read_json(Path(inputs["nucleation"])) if "nucleation" in inputs else config["nucleation"]
    spec=dict(spec)
    kind=spec.get("kind","table")
    diagnostics=[]
    if kind in ("bounce","thin_wall"):
        actions=[]
        T=np.asarray(spec["T_MeV"],float)
        if kind=="thin_wall":
            if len(spec["delta_p_MeV4"])!=len(T) or len(spec["sigma_MeV3"])!=len(T):
                raise InputError("thin-wall table arrays differ")
            for t,dp,sig in zip(T,spec["delta_p_MeV4"],spec["sigma_MeV3"]):
                result=thin_wall(t,dp,sig);actions.append(result["S3_over_T"]);diagnostics.append(result)
        else:
            if len(spec["potentials"])!=len(T):raise InputError("one bounce potential is required per temperature")
            for i,(t,pot) in enumerate(zip(T,spec["potentials"])):
                result=bounce_o3(**pot)
                actions.append(result["S3_MeV"]/t)
                profile=list(zip(result.pop("radius_MeV_inv"),result.pop("phi_MeV"),result.pop("dphi_dr_MeV2")))
                with (out/f"critical_profile_{i}.csv").open("w",newline="") as f:
                    writer=csv.writer(f);writer.writerow(["r_MeV_inv","phi_MeV","dphi_dr_MeV2"]);writer.writerows(profile)
                diagnostics.append(result)
        spec["S3_over_T"]=actions
    elif kind!="table":
        raise InputError("unsupported nucleation construction")
    kernel=Kernel(spec)
    wall_spec=read_json(Path(inputs["wall"])) if "wall" in inputs else config["wall"]
    wall=FrictionWall(wall_spec)
    with (out/"nucleation_kernel.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["T_MeV","S3_over_T","prefactor_MeV4","log_Gamma_MeV4","Gamma_MeV4"])
        writer.writeheader()
        for t in kernel.T:writer.writerow({"T_MeV":float(t),**kernel.at(t)})
    (out/"nucleation_definition.json").write_text(json.dumps(spec,indent=2,allow_nan=False)+"\n")
    (out/"wall_transport.json").write_text(json.dumps({"definition":wall.spec,"hydrodynamic_matching":config.get("hydrodynamic_states"),
        "closure":"eta gamma v = delta_p(T_X) - L (T_front-T_X)/T_ref; q=kappa (T_front-T_X)",
        "fluid_shell_solution":"required separately when relevant"},indent=2,allow_nan=False)+"\n")
    hydro=[]
    for states in config.get("hydrodynamic_states",[]):hydro.append(hydrodynamic_match(**states))
    pocket={"geometry":"spherical old-phase pocket","curvature_pressure":"2 sigma/R", "radius_equation":"dR/dt_natural=-v + H_natural R",
            "surface_tension_source":config.get("surface_tension_source"),"flux_matching_checks":hydro,
            "nucleation_diagnostics":diagnostics}
    (out/"pocket_model.json").write_text(json.dumps(pocket,indent=2,allow_nan=False)+"\n")
    limitations=["Action, prefactor, wall transport and their domain must be independently calibrated for a physical claim."]
    if donor_selected:
        limitations.append("The matched finite-a donor is a diagnostic thin-wall control, not a continuum metastable EOS or calibrated transition history.")
    return {"software_status":"PASS","evidence_status":"DIAGNOSTIC" if donor_selected else "CONDITIONAL",
            "physical_input_status":"DIAGNOSTIC_ONLY" if donor_selected else "SUPPLIED_MODEL",
            "metrics":{"temperatures":len(kernel.T),"flux_matching_cases":len(hydro)},
            "limitations":limitations}
