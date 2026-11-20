"""P7: coupled Friedmann, phase, heat and relic evolution in physical time.

Homogeneous independent bubbles use the four exact growth moments of the
Avrami integral; this branch allows growing/stalled bubbles, not reversing
phase fractions. A quasistationary wall boundary layer is solved at every RHS
evaluation. The mixture EOS contains latent heat once. Five portal corners
are evolved independently, never made by adding already evolved histories.
"""
from __future__ import annotations

import copy
import math
import re
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq
from scipy.special import kv, kve, zeta

from .collisions import CORNERS, ThermalTransfer, cannibal_rate, decay_table
from .common import (G_NEWTON_MEV_MINUS2, HBAR_MEV_S, HBARC_MEV_CM,
                     InputError, OpenInput, canonical_hash, finite, read_json,
                     require_source, sha256, write_csv, write_json)
from .nucleation import FrictionWall, Kernel
from .thermodynamics import EOSBundle, PhaseEOS

SECTORS = ("X", "gamma", "nu", "free", "relic")
# log(a/a0), T_X, recipient densities, relic number+energy, four bubble moments,
# five comoving source integrals, and five pressure-work integrals.
NSTATE = 31
J = slice(7, 11)
ENERGY = slice(11, 16)
WORK = slice(16, 21)
RADIATION_ENERGY = slice(21, 26)
TRACE_WORK = slice(26, 31)


class BathEOS:
    def __init__(self, spec):
        require_source(spec, "recipient EOS")
        self.spec = spec
        if spec["kind"] == "radiation":
            self.c = finite(spec["rho_over_T4"], "radiation coefficient", positive=True)
            self.phase = None
        else:
            self.phase = PhaseEOS.from_dict(spec)

    def density(self, t):
        return self.c*t**4 if self.phase is None else self.phase.at(t)["rho_MeV4"]

    def at_density(self, rho):
        if not math.isfinite(rho) or rho < -1e-13:
            raise InputError("recipient density became negative")
        rho = max(rho, 0.)
        if self.phase is None:
            return (rho/self.c)**.25, rho/3
        t = self.phase.temperature_for_density(rho)
        return t, self.phase.at(t)["p_MeV4"]


def relic_energy_per_particle(t, m):
    """Classical relativistic gas, including its nonrelativistic limit."""
    if t == 0:
        return m
    x = m/t
    if x > 1e6:
        return m+1.5*t+1.875*t*t/m
    return m*kve(1, x)/kve(2, x)+3*t


def relic_state(n, rho, m, *, dust=False):
    if n <= 0:
        if abs(rho) > 1e-13:
            raise InputError("nonzero relic energy with zero relic number")
        return 0., 0., 1.
    if dust:
        if abs(rho-m*n) > 1e-6*max(rho, m*n, 1e-300):
            raise InputError("pressureless relic violates rho=m*n")
        return 0., 0., 1.
    e = rho/n
    if e < m*(1-1e-9):
        raise InputError("relic mean energy is below its rest mass")
    if e <= m:
        return 0., 0., 1.
    hi = max(e, m)
    t = brentq(lambda temp: relic_energy_per_particle(temp, m)-e, 0, hi,
               xtol=max(1e-14*hi, 1e-300), rtol=1e-12)
    p = n*t
    ratio = 1 if t == 0 else (1-1.5*t/m if m/t > 1e6 else float(kve(1, m/t)/kve(2, m/t)))
    return t, p, ratio


def equilibrium_relic_density(T_MeV,mass_MeV,degeneracy=1.0):
    """Classical n_eq and its time-dilation moment n_eq <m/E>."""
    t=finite(T_MeV,"recipient temperature",nonnegative=True)
    m=finite(mass_MeV,"relic mass",positive=True)
    g=finite(degeneracy,"relic degeneracy",positive=True)
    if t==0:return 0.0,0.0
    norm=g*m*m*t/(2*np.pi**2)
    return float(norm*kv(2,m/t)),float(norm*kv(1,m/t))


def decay_moments(n, relic_dilation, mass, proper_rate_s, bath_temperature, degeneracy=1.):
    """MB decay plus inverse-decay moments for one common thermal daughter bath.

    C[f]=-Gamma*m/E*(f-feq). Thus the number source includes <m/E>,
    whereas its energy moment is m*Gamma*(n-neq). The parent and daughters
    receive reciprocal signs. See doi:10.1140/epjc/s10052-024-13337-w Eq. 8.
    Multi-bath final states require their full collision integral instead.
    """
    neq,neq_dilation=equilibrium_relic_density(bath_temperature,mass,degeneracy)
    return {"number_source_MeV3_s":-proper_rate_s*(n*relic_dilation-neq_dilation),
            "recipient_energy_MeV4_s":mass*proper_rate_s*(n-neq),
            "equilibrium_number_MeV3":neq}


def first_event(time, values, threshold, *, increasing=True):
    y = np.asarray(values, float)-threshold
    direction = y if increasing else -y
    if direction[0] >= 0:
        return {"time_s":None,"censored":True,"censoring":"left","upper_bound_s":float(time[0])}
    indexes = np.flatnonzero((direction[:-1] < 0) & (direction[1:] >= 0))
    if not len(indexes):
        return {"time_s": None, "censored": True, "lower_bound_s": float(time[-1])}
    i = indexes[0]
    return {"time_s": float(np.interp(0., direction[i:i+2], np.asarray(time)[i:i+2])), "censored": False}


def _bound_proof(proof,config,name):
    if not isinstance(proof,dict) or not proof.get("source"):
        raise OpenInput(f"{name} requires a sourced proof artifact")
    artifacts=proof.get("artifacts",[])
    records={x.get("name"):x.get("sha256") for x in config.get("_request",{}).get("inputs",[])}
    if not artifacts or any(not isinstance(x,dict) or not re.fullmatch(r"[0-9a-f]{64}",str(x.get("sha256",""))) or records.get(x.get("name"))!=x.get("sha256") for x in artifacts):
        raise OpenInput(f"{name} is not bound to verified request input hashes")
    return proof


class CoupledModel:
    def __init__(self, config, eos_definition, kernel_definition, wall_definition,
                 collision_definition, initial):
        self.config = config
        self.eos = EOSBundle.from_dict(eos_definition)
        self.kernel = Kernel.from_dict(kernel_definition)
        self.wall = FrictionWall.from_dict(wall_definition.get("definition", wall_definition))
        collision_data=collision_definition.get("definition", collision_definition)
        self.collision = ThermalTransfer(collision_data)
        if collision_data.get("reactions") and not collision_data.get("thermal_channels"):
            _bound_proof(collision_data.get("independent_zero_transfer_proof"),config,"zero thermal transfer despite known reactions")
        self.thermal_proof=None
        if config.get("_mode","conditional")!="validation":
            self.thermal_proof=_bound_proof(config.get("thermalization_proof"),config,"thermal recipient closure")
            if self.thermal_proof.get("status") in {"OPEN_INPUT","UNSUPPORTED","UNKNOWN"}:
                raise OpenInput("physical thermalization input is still open")
            minimum=finite(self.thermal_proof["minimum_thermalization_rate_over_H"],"thermalization lower bound",positive=True)
            required=finite(self.thermal_proof["required_minimum_rate_over_H"],"thermal closure criterion",positive=True)
            if minimum<required:
                raise OpenInput("thermalization rate is too slow for the declared thermal closure")
            lo,hi=self.thermal_proof["T_range_MeV"]
            if not 0<lo<hi:
                raise InputError("invalid thermalization domain")
        self.initial = copy.deepcopy(initial.get("definition", initial))
        require_source(self.initial,"initial history")
        for canonical,alias in (("scale_factor","a0"),("eta_b_gamma","eta_b")):
            if canonical in self.initial and alias in self.initial and self.initial[canonical]!=self.initial[alias]:
                raise InputError(f"inconsistent initial-surface aliases: {canonical}/{alias}")
            if canonical not in self.initial and alias in self.initial:
                self.initial[canonical]=self.initial[alias]
        kinetic_definitions=config.get("kinetic_species",[])
        kinetic_nu=any(s.get("sector")=="nu" for s in kinetic_definitions)
        nu=self.initial.get("neutrinos",{})
        if nu:
            if kinetic_nu:
                if nu.get("kind")!="momentum_grid" or set(nu)-{"kind","source"}:
                    raise InputError("kinetic neutrino occupations are specified in kinetic_species; conflicting initial spectra/temperatures are forbidden")
            elif nu.get("kind")!="thermal":
                raise OpenInput("thermal P7 closure cannot replace a supplied nonthermal initial spectrum")
            if nu.get("kind")=="thermal" and "T_nu_MeV" in self.initial and self.initial["T_nu_MeV"]!=nu["T_MeV"]:
                raise InputError("conflicting initial neutrino temperatures")
            if nu.get("kind")=="thermal":self.initial["T_nu_MeV"]=nu["T_MeV"]
        if kinetic_nu and "T_nu_MeV" in self.initial:
            raise InputError("a resolved neutrino sector must not also prescribe a thermal T_nu initial condition")
        if "phase_fraction" not in self.initial and self.initial.get("phase") in {"hot","cold"}:
            self.initial["phase_fraction"]=float(self.initial["phase"]=="cold")
        self.tc = self.eos.Tc_MeV
        self.path = config.get("thermal_path", config.get("_key", {}).get("thermal_path"))
        if self.path not in {"isolated_during_transition", "exchange_during_transition"}:
            raise InputError("P7 requires a named thermal path")
        if config.get("phase_model") != "homogeneous_growth":
            raise OpenInput("P7 requires a validated phase kernel; implemented branch is homogeneous_growth")
        if config.get("neutrino_closure") not in {"thermal","momentum_grid"}:
            raise OpenInput("a nonthermal neutrino closure requires a supplied kinetic solver, not Tnu alone")
        if not config.get("thermal_closure_source"):
            raise OpenInput("remaining thermal reservoirs need an applicability source")
        self.baths = {s: BathEOS(config["recipient_eos"][s]) for s in SECTORS[1:4]}
        self.relic = config.get("relic")
        from .kinetic_history import KineticCollection
        self.kinetic=KineticCollection(kinetic_definitions,offset=NSTATE,a0=self.initial.get("scale_factor",1))
        from .gravitationalwaves import GWSource
        self.gw=GWSource(config.get("gw_source"),offset=self.kinetic.size)
        self.nstate=self.gw.size
        if ("nu" in self.kinetic.sectors)!=(config.get("neutrino_closure")=="momentum_grid"):
            raise InputError("momentum_grid closure and resolved nu species must be selected together")
        if self.relic and "relic" in self.kinetic.sectors:
            raise InputError("a relic cannot be represented by both MB moments and momentum cells")
        if any(c["recipient"] in self.kinetic.sectors for c in self.collision.channels):
            raise OpenInput("thermal transfer cannot heat a kinetic species; supply its momentum collision operator")
        if self.relic:
            require_source(self.relic, "relic evolution")
            if self.relic.get("excluded_from_phase_eos") is not True:
                raise OpenInput("separate relic energy must be explicitly excluded from phase EOS")
            self.mass = finite(self.relic["mass_MeV"], "relic mass", positive=True)
            self.degeneracy=finite(self.relic.get("degeneracy",1),"relic degeneracy",positive=True)
            self.dust = self.relic.get("kinetic_model") == "pressureless"
            if self.relic.get("kinetic_model") not in {"pressureless", "relativistic_MB"}:
                raise OpenInput("relic kinetic EOS must be specified")
            if self.dust and self.relic.get("cannibal_MeV_minus5", 0) != 0:
                raise InputError("3<->2 releases kinetic energy and cannot use a dust EOS")
            number_model = self.relic.get("number_changing_model")
            if number_model is not None:
                validate_number_changing_binding(self.relic, number_model)
            table = decay_table([self.relic])
            self.decay_rate = table[0]["total_width_MeV"]/HBAR_MEV_S
            self.branches = {s: sum(x["branching_fraction"] for x in table if x["recipient"] == s)
                             for s in SECTORS[1:4]}
            if any(self.branches.get(s,0)>0 for s in self.kinetic.sectors):
                raise OpenInput("thermal relic decay moments cannot replace kinetic daughter source spectra")
            if self.decay_rate and abs(sum(self.branches.values())-1) > 1e-12:
                raise OpenInput("all open relic decay channels must have supported recipients")
            if self.decay_rate and self.relic.get("instant_thermalization") is not True:
                raise OpenInput("decay products require explicit cascades or a validated instantaneous-thermalization limit")
            if self.decay_rate and self.dust:
                approximation=self.relic.get("inverse_decay_approximation")
                if not isinstance(approximation,dict) or approximation.get("kind")!="negligible_MB" or not approximation.get("source"):
                    raise OpenInput("pressureless decay requires a sourced exponentially suppressed inverse-decay bound")
                self.inverse_bound_temperature=finite(approximation["max_recipient_temperature_MeV"],"inverse decay temperature bound",positive=True)
                self.inverse_tolerance=finite(approximation["relative_energy_tolerance"],"inverse decay tolerance",positive=True)
                if self.inverse_tolerance>=1:
                    raise InputError("inverse-decay error tolerance must be below unity")
            elif self.decay_rate and self.relic.get("inverse_decay_model","single_bath_MB")!="single_bath_MB":
                raise OpenInput("multi-bath inverse decays need a supplied collision integral")
        self.f0 = finite(self.initial.get("phase_fraction", 0), "initial phase fraction")
        if not 0 <= self.f0 <= 1:
            raise InputError("initial phase fraction outside [0,1]")
        self.a0 = finite(self.initial.get("scale_factor", 1), "initial scale factor", positive=True)
        self.t0 = finite(self.initial.get("time_s", 0), "initial time")
        if "transition_relic_threshold" in config:
            raise InputError("phase-fraction numerical thresholds cannot activate physical portals")
        self.isolation_end_s=None
        self.decay_activation_s=self.t0
        if self.path=="isolated_during_transition":
            isolation=config.get("isolation")
            if isolation is not None:
                require_source(isolation,"physical isolation interval")
                if isolation.get("activation_model")!="supplied_time_gate":
                    raise OpenInput("finite isolation interval needs a declared physical time-gate model")
                self.isolation_end_s=finite(isolation["end_time_s"],"isolation endpoint")
                if self.isolation_end_s<self.t0:
                    raise InputError("isolation interval ends before the initial surface")
        if self.relic and self.decay_rate:
            activation=self.relic.get("activation")
            if activation is not None:
                require_source(activation,"relic decay activation")
                if activation.get("kind")!="supplied_time_gate":
                    raise OpenInput("unsupported time-dependent relic width; supply a physical kernel")
                self.decay_activation_s=finite(activation["time_s"],"decay activation time")
                if self.decay_activation_s<self.t0:
                    raise InputError("decay activation precedes the declared initial history")
            if self.path=="isolated_during_transition" and (activation is None or self.isolation_end_s is None or self.decay_activation_s<self.isolation_end_s):
                raise OpenInput("nonzero relic decay is incompatible with exact isolation; specify a sourced late activation after the isolation interval")
        self.eta = finite(self.initial["eta_b_gamma"], "initial baryon photon ratio", positive=True)
        self.y0 = self.kinetic.initialize(np.zeros(self.nstate))
        self.gw.initialize(self.y0)
        self.y0[1] = finite(self.initial["T_X_MeV"], "initial X temperature", positive=True)
        for i, s in enumerate(SECTORS[1:4], start=2):
            if s not in self.kinetic.sectors:
                self.y0[i] = self.baths[s].density(finite(self.initial["T_"+s+"_MeV"], s+" temperature", nonnegative=True))
        self.surface = self.initial.get("surface")
        if self.surface not in {"first_cooling_Tc", "postconfinement"}:
            raise OpenInput("initial history must identify a first-cooling or postconfinement surface")
        if abs(self.y0[1]/self.tc-1) > 1e-10:
            raise InputError("initial surface is not at the registered Tc")
        if self.surface == "first_cooling_Tc" and self.f0 != 0:
            raise InputError("first-cooling onset must start in the old phase")
        if self.surface == "postconfinement" and self.f0 != 1:
            raise InputError("postconfinement initial surface must be in the cold phase")
        if self.relic:
            self.y0[5] = finite(self.initial.get("relic_n_MeV3", 0), "initial relic number", nonnegative=True)
            tr = finite(self.initial.get("relic_T_MeV", 0), "initial relic temperature", nonnegative=True)
            self.y0[6] = self.y0[5]*(self.mass if self.dust else relic_energy_per_particle(tr, self.mass))
        rho_x = self.eos.mixture(self.y0[1], self.f0)["rho_MeV4"]
        kinetic_rho,_,_=self.kinetic.moments(self.y0,self.a0)
        gw_rho,_=self.gw.moments(self.y0)
        total = rho_x+sum(self.y0[2:5])+self.y0[6]+kinetic_rho.sum()+gw_rho
        if total <= 0:
            raise InputError("nonpositive total initial energy density")
        self.H0 = math.sqrt(8*np.pi*G_NEWTON_MEV_MINUS2*total/3)/HBAR_MEV_S
        self.L = self.eos.at(self.tc, "hot")["rho_MeV4"]-self.eos.at(self.tc, "cold")["rho_MeV4"]
        if self.L <= 0:
            raise InputError("positive hot-to-cold latent heat required")
        self.initial_energy = (np.array([rho_x, *self.y0[2:5], self.y0[6]])+kinetic_rho)*self.a0**3
        self.initial_energy[SECTORS.index("free")]+=gw_rho*self.a0**3
        self.initial_density=self.initial_energy/self.a0**3
        self.n_b0 = self.eta*2*zeta(3)/np.pi**2*self.initial["T_gamma_MeV"]**3/HBARC_MEV_CM**3

    def evaluate(self, tau, y, corner):
        y=np.asarray(y,float)
        if y.shape!=(self.nstate,) or not np.all(np.isfinite(y)):
            raise InputError("nonfinite or malformed coupled state")
        if np.any(y[2:7]<0):
            raise InputError("recipient/relic state became negative; refine the solver or input model")
        a = self.a0*math.exp(y[0])
        tx = y[1]
        intensity = max(4*np.pi*y[10]/3, 0.)
        old = (1-self.f0)*math.exp(-intensity)
        f = self.f0+(1-self.f0)*(-math.expm1(-intensity))
        x = self.eos.mixture(tx, f)
        ts, ps = {}, {}
        for i, s in enumerate(SECTORS[1:4], 2):
            ts[s], ps[s] = self.baths[s].at_density(y[i])
        if self.thermal_proof:
            lo,hi=self.thermal_proof["T_range_MeV"]
            active={c["recipient"] for c in self.collision.channels}
            if self.relic:
                active|={s for s in SECTORS[1:4] if self.branches[s]>0}
            if any(not lo<=ts[s]<=hi for s in active):
                raise OpenInput("recipient temperature left the verified thermalization domain")
        tr, pr, dilation = relic_state(max(y[5], 0), max(y[6], 0), self.mass, dust=self.dust) if self.relic else (0., 0., 1.)
        rho = np.array([x["rho_MeV4"], *y[2:5], y[6]])
        pressure = np.array([x["p_MeV4"], *[ps[s] for s in SECTORS[1:4]], pr])
        kinetic_rho,kinetic_pressure,kinetic_records=self.kinetic.moments(y,a)
        rho+=kinetic_rho;pressure+=kinetic_pressure
        gw_rho,gw_pressure=self.gw.moments(y)
        rho[SECTORS.index("free")]+=gw_rho
        pressure[SECTORS.index("free")]+=gw_pressure
        # These temperatures are energy-equivalent diagnostics only. Thermal
        # transfer to these sectors was rejected above; weak rates use f(q).
        for s in self.kinetic.sectors & {"nu","free"}:
            ts[s]=self.baths[s].at_density(rho[SECTORS.index(s)])[0]
        if rho.sum() <= 0:
            raise InputError("nonpositive total density")
        hubble = math.sqrt(8*np.pi*G_NEWTON_MEV_MINUS2*rho.sum()/3)/HBAR_MEV_S
        state = {"T_X_MeV": tx, **{"T_"+s+"_MeV": ts[s] for s in ts}, "phase_fraction": f}
        physical_time=self.t0+tau/self.H0
        isolated=(self.path=="isolated_during_transition" and
                  (self.isolation_end_s is None or physical_time<=self.isolation_end_s))
        # Exact isolation is a physical branch condition. It never ends merely
        # because a numerical phase fraction approaches one.
        q={s:0. for s in SECTORS[:4]} if isolated else self.collision.at(state,corner)
        v = 0.
        front = tx
        gamma_bar = 0.
        wall = {"heat_balance_residual_MeV4": 0.}
        if tx <= self.tc and self.f0 < 1:
            hot, cold = self.eos.at(tx, "hot"), self.eos.at(tx, "cold")
            dp = cold["p_MeV4"]-hot["p_MeV4"]
            local_latent = hot["rho_MeV4"]-cold["rho_MeV4"]
            if dp < -1e-12*max(abs(hot["p_MeV4"]),abs(cold["p_MeV4"]),1e-300):
                raise OpenInput("the declared cold phase is not favored below Tc; a reversing/reentrant phase kernel is required")
            wall = self.wall.steady_speed(tx, max(dp,0), local_latent)
            v = wall["v"]
            front = wall["T_front_MeV"]
            kernel = self.kernel.at(tx)
            logg = kernel["log_Gamma_MeV4"]-4*math.log(self.H0*HBAR_MEV_S)
            if logg > 700:
                raise InputError("nucleation rate exceeds numerically resolvable domain")
            gamma_bar = math.exp(logg) if logg > -745 else 0.
        fdot_tau = old*4*np.pi*max(y[9], 0)*v/(a/self.a0)
        fdot = fdot_tau*self.H0
        qarray = np.array([q[s] for s in SECTORS[:4]]+[0.])
        kinetic_derivative,kinetic_q=self.kinetic.rhs(physical_time,y,a,{"X":tx,"gamma":ts["gamma"]},corner,isolated=isolated)
        qarray+=kinetic_q
        gw_derivative,gw_power,gw_record=self.gw.rhs(physical_time,y,a,hubble,corner)
        qarray[0]-=gw_power
        qarray[SECTORS.index("free")]+=gw_power
        ndot = 0.
        inverse_neglected_bound_fraction=0.
        if self.relic:
            formation_fraction = finite(self.relic.get("latent_energy_fraction", 0), "relic production fraction", nonnegative=True)
            if formation_fraction > 1:
                raise InputError("relic latent energy fraction exceeds one")
            produce_energy = formation_fraction*self.L*fdot
            mean_produced = finite(self.relic.get("production_energy_per_particle_MeV", self.mass), "production energy", positive=True)
            if mean_produced < self.mass:
                raise InputError("relic production energy below rest mass")
            if self.dust and mean_produced != self.mass:
                raise InputError("kinetic production energy is incompatible with dust")
            n = max(y[5], 0.)
            ndot = -3*hubble*n+produce_energy/mean_produced
            decay_energy_by_bath={s:0. for s in SECTORS[1:4]}
            for sector in SECTORS[1:4]:
                partial=self.decay_rate*self.branches[sector] if physical_time>=self.decay_activation_s else 0.
                if partial==0:continue
                if self.dust:
                    if ts[sector]>self.inverse_bound_temperature:
                        raise InputError("recipient exceeds the declared inverse-decay suppression domain")
                    neq,_=equilibrium_relic_density(self.inverse_bound_temperature,self.mass,self.degeneracy)
                    duration=max(10.,float(self.config.get("duration_H0",10.)))/self.H0
                    duration=max(duration,float(self.config.get("duration_s",0)))
                    # A conservative bound over the full declared horizon,
                    # including the largest comoving weighting encountered.
                    neglected=a**3*self.mass*self.decay_rate*neq*duration
                    inverse_neglected_bound_fraction=max(inverse_neglected_bound_fraction,neglected/float(self.initial_energy.sum()))
                    if neglected>self.inverse_tolerance*float(self.initial_energy.sum()):
                        raise OpenInput("inverse-decay upper bound exceeds the declared energy-error tolerance; use MB kinetic relics")
                    ndot-=partial*n
                    decay_energy_by_bath[sector]=self.mass*partial*n
                else:
                    moments=decay_moments(n,dilation,self.mass,partial,ts[sector],self.degeneracy)
                    ndot+=moments["number_source_MeV3_s"]
                    decay_energy_by_bath[sector]=moments["recipient_energy_MeV4_s"]
            decay_energy=sum(decay_energy_by_bath.values())
            c32 = self.relic.get("cannibal_MeV_minus5", 0.)
            if c32 and n > 0:
                if tr <= 0:
                    raise OpenInput("3<->2 requires a positive kinetic temperature in its sourced MB domain")
                domain = self.relic.get("number_changing_model", {}).get("T_X_range_MeV")
                if domain is not None and not domain[0] <= tr <= domain[1]:
                    raise OpenInput("relic temperature left the sourced low-momentum 3<->2 domain")
                ndot -= cannibal_rate(n, tr, self.mass, c32, self.relic.get("degeneracy", 1.))
            elastic = finite(self.relic.get("elastic_coefficient_MeV3_s", 0.), "relic elastic coefficient", nonnegative=True)*(tx-tr) if n > 0 else 0.
            qarray[0] -= produce_energy+elastic
            qarray[4] += produce_energy+elastic-decay_energy
            for i, s in enumerate(SECTORS[1:4], 1):
                qarray[i] += decay_energy_by_bath[s]
        if abs(float(qarray.sum()))>1e-12*max(float(np.abs(qarray).sum()),1e-300):
            raise RuntimeError("coupled sources violate sum Q=0")
        if not x.get("phase_derivative_available",True) and fdot!=0:
            raise OpenInput("phase conversion requires both EOS branches at the current temperature")
        derivative = np.zeros(self.nstate)
        derivative[:self.kinetic.size]=kinetic_derivative
        derivative[self.gw.slice]=gw_derivative
        derivative[0] = hubble/self.H0
        derivative[1] = (-3*hubble*(rho[0]+pressure[0])+qarray[0]-x["drho_df_MeV4"]*fdot)/x["cv_MeV3"]/self.H0
        derivative[2:5] = (-3*hubble*(rho[1:4]+pressure[1:4])+qarray[1:4])/self.H0
        # The appended GW cells carry their own -4H rho + Q. The original
        # free-radiation coordinate carries only its remaining thermal part.
        derivative[4]-=(-4*hubble*gw_rho+gw_power)/self.H0
        for s in self.kinetic.sectors & {"nu","free"}:
            derivative[SECTORS.index(s)+1]=0.
        derivative[5] = ndot/self.H0
        derivative[6] = (-3*hubble*(rho[4]+pressure[4])+qarray[4])/self.H0
        if "relic" in self.kinetic.sectors:derivative[6]=0.
        derivative[NSTATE:]/=self.H0
        derivative[7] = gamma_bar*(a/self.a0)**3
        derivative[8] = v/(a/self.a0)*y[7]
        derivative[9] = 2*v/(a/self.a0)*y[8]
        derivative[10] = 3*v/(a/self.a0)*y[9]
        derivative[ENERGY] = a**3*qarray/self.H0
        derivative[WORK] = 3*hubble*a**3*pressure/self.H0
        derivative[RADIATION_ENERGY] = a**4*qarray/self.H0
        derivative[TRACE_WORK] = hubble*a**4*(rho-3*pressure)/self.H0
        return derivative, {"scale_factor": a, "H_s_inv": hubble, "T_X_MeV": tx,
            **{"T_"+s+"_MeV": ts[s] for s in ts}, "phase_fraction": f, "I": intensity,
            "old_physical_volume": a**3*old, "old_fraction":old,
            "nucleation_rate_MeV4":gamma_bar*(self.H0*HBAR_MEV_S)**4,
            "wall_temperature_MeV": front,
            "wall_speed": v, "rho": rho, "pressure": pressure, "Q": qarray,
            "kinetic_species":kinetic_records,
            "gw":gw_record,
            "f_dot_s_inv": fdot, "relic_T_MeV": tr,
            "old_volume_log_growth_s_inv":(3*hubble-4*np.pi*max(y[9],0)*v/(a/self.a0)*self.H0) if self.f0<1 else None,
            "isolation_active":isolated,
            "inverse_decay_neglected_energy_bound_fraction":inverse_neglected_bound_fraction,
            "wall_heat_residual_MeV4": wall["heat_balance_residual_MeV4"],
            "n_b_cm3": self.n_b0*(self.a0/a)**3}

    def solve(self, corner, *, checkpoint=None, resume=None):
        end = max(10., finite(self.config.get("duration_H0", 10.), "duration", positive=True))
        if "duration_s" in self.config:
            end = max(end, finite(self.config["duration_s"], "duration_s", positive=True)*self.H0)
        samples = int(self.config.get("samples", 1025))
        if samples < 33:
            raise InputError("at least 33 history samples are required")
        # Include science landmarks exactly; solve on time, never temperature.
        gw_knots=[(t-self.t0)*self.H0 for t in self.gw.time_knots_s
                  if self.t0<=t<=self.t0+end/self.H0]
        sample_grid = np.unique(np.r_[np.linspace(0, end, samples), 1., 10., gw_knots])
        interval_size=finite(self.config.get("checkpoint_interval_H0",1.),"checkpoint interval",positive=True)
        boundaries=[(x-self.t0)*self.H0 for x in (self.isolation_end_s,self.decay_activation_s) if x is not None and self.t0<x<self.t0+end/self.H0]
        boundaries+=gw_knots
        intervals = np.unique(np.r_[np.arange(0, end, interval_size),boundaries,end])
        digest = canonical_hash({"config": {k: v for k, v in self.config.items() if not k.startswith("_")},
                                 "corner": corner, "initial": self.initial,
                                 "eos": self.eos.definition if hasattr(self.eos, "definition") else self.eos.spec,
                                 "collisions": self.collision.definition,
                                 "nucleation":self.kernel.spec,"wall":self.wall.spec,
                                 "request_key":self.config.get("_key")})
        last_tau, y, saved_t, saved_y = 0., self.y0.copy(), [0.], [self.y0.tolist()]
        crossings=[]
        if resume is not None:
            cp = read_json(resume)
            if cp.get("input_sha256") != digest or cp.get("corner") != corner:
                raise InputError("history checkpoint input binding mismatch")
            last_tau, y = cp["tau"], np.asarray(cp["state"], float)
            saved_t, saved_y = cp["sample_tau"], cp["sample_states"]
            crossings=cp.get("Tc_crossings",[])
            if cp.get("schema")!="R135-history-checkpoint-v2" or len(saved_t)!=len(saved_y) or not saved_t or saved_t[0]!=0 or np.any(np.diff(saved_t)<=0) or saved_t[-1]>last_tau or np.asarray(saved_y).shape!=(len(saved_t),self.nstate) or not np.all(np.isfinite(saved_y)):
                raise InputError("invalid checkpoint trajectory")
            if y.shape != (self.nstate,) or not np.isfinite(y).all() or last_tau not in intervals:
                raise InputError("invalid history checkpoint state/boundary")
        if self.surface == "first_cooling_Tc" and self.evaluate(0., self.y0, corner)[0][1] >= 0:
            raise InputError("registered initial surface is not a cooling crossing of Tc")
        scale = np.maximum(np.abs(self.y0), 1.)
        scale[ENERGY] = max(self.initial_energy.sum(), self.L*self.a0**3)
        scale[WORK] = scale[ENERGY]
        scale[RADIATION_ENERGY] = scale[ENERGY]*self.a0
        scale[TRACE_WORK] = scale[RADIATION_ENERGY]
        atol = finite(self.config.get("atol_relative", 1e-10), "absolute relative tolerance", positive=True)*scale
        if "atol_state" in self.config:
            atol=np.asarray(self.config["atol_state"],float)
            if atol.shape!=(self.nstate,) or not np.all(np.isfinite(atol)) or np.any(atol<=0):
                raise InputError("atol_state must give a positive finite tolerance per coupled coordinate")
        rtol = finite(self.config.get("rtol", 1e-7), "relative tolerance", positive=True)
        def crossing(t,state): return state[1]-self.tc
        crossing.terminal=False;crossing.direction=0
        nfev = 0
        for right in intervals[intervals > last_tau]:
            solution = solve_ivp(lambda t, state: self.evaluate(t, state, corner)[0],
                (last_tau, right), y, method=self.config.get("method", "DOP853"),
                rtol=rtol, atol=atol, dense_output=True,events=crossing,
                max_step=self.config.get("max_step_H0", np.inf))
            nfev += solution.nfev
            if not solution.success:
                raise RuntimeError("coupled integration failed: " + solution.message)
            for event_tau in solution.t_events[0]:
                if event_tau>1e-12 and not any(abs(event_tau-v["tau_H0"])<1e-10 for v in crossings):
                    event_state=solution.sol(event_tau)
                    direction="heating" if self.evaluate(event_tau,event_state,corner)[0][1]>0 else "cooling"
                    crossings.append({"tau_H0":float(event_tau),"time_s":self.t0+float(event_tau)/self.H0,"direction":direction})
            chosen = sample_grid[(sample_grid > last_tau) & (sample_grid <= right)]
            saved_t.extend(chosen.tolist())
            saved_y.extend(solution.sol(chosen).T.tolist())
            y, last_tau = solution.y[:, -1], float(right)
            if checkpoint:
                write_json(checkpoint, {"schema": "R135-history-checkpoint-v2", "corner": corner,
                    "input_sha256": digest, "tau": last_tau, "state": y.tolist(),
                    "sample_tau": saved_t, "sample_states": saved_y,"Tc_crossings":crossings,
                    "resume_semantics": "exact restart at deterministic interval boundaries; adaptive state resets at every boundary"})
        records = []
        for tau, state in zip(saved_t, saved_y):
            state = np.asarray(state)
            self.kinetic.validate_accepted(state)
            self.gw.validate_accepted(state)
            _, row = self.evaluate(tau, state, corner)
            row.update(time_s=self.t0+tau/self.H0, tau_H0=tau, corner=corner,
                       comoving_energy_sources_MeV4=state[ENERGY].tolist(),
                       comoving_pressure_work_MeV4=state[WORK].tolist(),
                       radiation_weighted_sources_MeV4=state[RADIATION_ENERGY].tolist(),
                       radiation_trace_work_MeV4=state[TRACE_WORK].tolist(),
                       relic_n_MeV3=state[5], bubble_moments=state[J].tolist())
            row["balance_MeV4"] = (row["scale_factor"]**3*row["rho"]-self.initial_energy-
                                      state[ENERGY]+state[WORK]).tolist()
            row["radiation_balance_MeV4"]=(row["scale_factor"]**4*row["rho"]-self.initial_energy*self.a0-state[RADIATION_ENERGY]-state[TRACE_WORK]).tolist()
            records.append(row)
        return records, {"nfev": nfev, "H0_s_inv": self.H0, "t0_s": self.t0,
            "a0": self.a0,"initial_phase_fraction":self.f0, "latent_heat_MeV4": self.L, "initial_energy_MeV4": self.initial_energy.tolist(),
            "onset_definition": self.surface, "input_sha256": digest,"Tc_crossings":crossings,
            "solver": {"method":self.config.get("method","DOP853"),"rtol":rtol,"atol_state":atol.tolist()},
            "pocket_geometry_status":"SELECTED_GEOMETRY_PENDING" if self.config.get("pocket_geometry") else "OPEN_INPUT",
            "kinetic_species_count":len(self.kinetic.species),
            "nonthermal_sectors":sorted(self.kinetic.sectors),
            "gw_energy_in_friedmann":self.gw.enabled,
            "isolation_model":{"path":self.path,"end_time_s":self.isolation_end_s,"decay_activation_s":self.decay_activation_s,
                               "continuous_portals_disabled_for_full_history":self.path=="isolated_during_transition" and self.isolation_end_s is None}}


def summarize(records, meta):
    time = np.array([r["time_s"] for r in records])
    fraction = np.array([r["phase_fraction"] for r in records])
    intensity = np.array([r["I"] for r in records])
    energy = np.array([r["comoving_energy_sources_MeV4"] for r in records])
    result = {"events": {str(x): first_event(time, fraction, x) for x in (.5, .9, .99)},
        "percolation_I034": first_event(time, intensity, .34), "landmarks": {},
        "confidence_interval": None, "completion_classification": "UNRESOLVED_UNCERTAINTY"}
    normalization = meta["a0"]**3*meta["latent_heat_MeV4"]
    for nh in (1, 10):
        t = meta["t0_s"]+nh/meta["H0_s_inv"]
        result["landmarks"][str(nh)] = {"time_s": t, "phase_fraction": float(np.interp(t, time, fraction)),
            "old_physical_volume": float(np.interp(t, time, [r["old_physical_volume"] for r in records])),
            "delivered_energy_over_a0cubed_L": {s: float(np.interp(t, time, energy[:, i])/normalization)
                                                for i, s in enumerate(SECTORS)},
            "radiation_weighted_energy_over_a0fourth_L": {s:float(np.interp(t,time,[r["radiation_weighted_sources_MeV4"][i] for r in records])/(normalization*meta["a0"])) for i,s in enumerate(SECTORS)}}
    result["max_absolute_balance_MeV4"] = float(np.max(np.abs([r["balance_MeV4"] for r in records])))
    result["max_relative_total_balance"] = float(np.max(np.abs(np.sum([r["balance_MeV4"] for r in records], axis=1)))/max(sum(meta["initial_energy_MeV4"]), normalization))
    result["max_relative_sector_balance"] = float(np.max(np.abs([r["balance_MeV4"] for r in records]))/max(sum(meta["initial_energy_MeV4"]), normalization))
    result["max_relative_radiation_balance"]=float(np.max(np.abs([r["radiation_balance_MeV4"] for r in records]))/max(sum(meta["initial_energy_MeV4"])*meta["a0"],normalization*meta["a0"]))
    result["recrossings_Tc"] = meta.get("Tc_crossings",[])
    result["maximum_neglected_inverse_decay_energy_bound_fraction"]=max(r["inverse_decay_neglected_energy_bound_fraction"] for r in records)
    viable=[r for r in records if r["I"]>=.34 and r["old_volume_log_growth_s_inv"] is not None and r["old_volume_log_growth_s_inv"]<0]
    result["percolation_with_shrinking_old_volume"]={"time_s":viable[0]["time_s"] if viable else None,"censored":not bool(viable),"time_resolution":"first retained sample satisfying both conditions"}
    if meta.get("initial_phase_fraction")==1:
        left={"time_s":None,"censored":True,"censoring":"left","upper_bound_s":float(time[0]),"reason":"postconfinement preparation does not contain transition kinetics"}
        result["percolation_I034"]=left.copy();result["percolation_with_shrinking_old_volume"]=left.copy()
        result["completion_classification"]="INITIAL_CONFINED_PREPARATION"
    return result


def _payload(records):
    direct = ("time_s", "scale_factor", "H_s_inv", "T_X_MeV", "T_gamma_MeV", "T_nu_MeV", "T_free_MeV",
              "phase_fraction", "n_b_cm3", "wall_temperature_MeV", "wall_speed", "I", "old_physical_volume")
    hist = {k: [float(r[k]) for r in records] for k in direct}
    for i, sector in enumerate(SECTORS):
        hist["rho_"+sector+"_MeV4"] = [float(r["rho"][i]) for r in records]
        hist["p_"+sector+"_MeV4"] = [float(r["pressure"][i]) for r in records]
    hist["rho_extra_MeV4"] = [float(r["rho"][[0, 3, 4]].sum()) for r in records]
    hist["p_extra_MeV4"] = [float(r["pressure"][[0, 3, 4]].sum()) for r in records]
    hist["Q_MeV4_s"] = {s: [float(r["Q"][i]) for r in records] for i, s in enumerate(SECTORS)}
    from .kinetic_history import spectra_from_records
    spectra=spectra_from_records(records)
    hist.update(spectra)
    hist["neutrino_closure"] = "momentum_grid" if spectra else "thermal"
    if spectra:
        hist["T_nu_energy_equivalent_MeV"]=hist.pop("T_nu_MeV")
    if any(r.get("kinetic_species") for r in records):
        hist["kinetic_species"]=[r["kinetic_species"] for r in records]
        hist["kinetic_temperature_interpretation"]="energy-equivalent diagnostics; use the saved occupations"
    from .gravitationalwaves import payload_from_records
    gw=payload_from_records(records)
    if gw is not None:
        hist["gw"]=gw
    return hist



def equilibrium_mixed_phase(s_hot, s_cold, fraction):
    """Reversible isolated coexistence in an externally radiation-dominated H.

    T_X=Tc, s_X*a^3=constant and H=H0*(a0/a)^2. This analytic limiting
    history is distinct from finite-rate bubble dynamics and neglects the
    contribution of X to the Hubble rate. It never calibrates a kinetic clock.
    """
    sh=finite(s_hot,"hot entropy",positive=True)
    sc=finite(s_cold,"cold entropy",positive=True)
    f=np.asarray(fraction,float)
    if sh<=sc or not np.all(np.isfinite(f)) or np.any((f<0)|(f>1)):
        raise InputError("invalid equilibrium coexistence entropy/fraction")
    ratio=(1-f*(1-sc/sh))**(-1/3)
    dt=(ratio**2-1)/2
    return {"a_over_a0":ratio.tolist(),"H0_delta_t":dt.tolist(),
            "assumptions":"reversible isolated X; externally dominant constant-g radiation"}


def _merge_mapping(base,patch):
    result=copy.deepcopy(base)
    if not isinstance(patch,dict):
        raise InputError("uncertainty overrides must be mappings")
    for k,v in patch.items():
        result[k]=_merge_mapping(result[k],v) if isinstance(v,dict) and isinstance(result.get(k),dict) else copy.deepcopy(v)
    return result


def propagate_uncertainty(config,definitions,out):
    """Integrate every supplied correlated parameter draw through all corners.

    Draws, their source and interpretation are inputs. A sensitivity set is
    never called a probability interval. Failed draws remain in the record;
    they cannot be silently dropped to make an interval narrower. Empirical
    percentile bands retain finite-sampling limitations and owner review.
    """
    ensemble=config.get("uncertainty_ensemble")
    if ensemble is None:
        return {"status":"NOT_SUPPLIED","reason":"independent physical parameter uncertainty samples are absent"}
    if not isinstance(ensemble,dict):
        raise InputError("uncertainty_ensemble must be an object with sourced draws")
    require_source(ensemble,"uncertainty ensemble")
    interpretation=ensemble.get("interpretation")
    if interpretation not in {"probability_samples","sensitivity_set"}:
        raise InputError("uncertainty interpretation must distinguish probability samples from sensitivity sets")
    draws=ensemble.get("draws",[])
    ids=[d.get("id") for d in draws]
    if not ids or any(not isinstance(x,str) or not re.fullmatch(r"[A-Za-z0-9_-]+",x) for x in ids) or len(set(ids))!=len(ids):
        raise InputError("uncertainty draws need unique safe nonempty IDs")
    allowed=set(definitions)|{"config"}
    baseline_config={k:v for k,v in config.items() if k!="uncertainty_ensemble"}
    outputs=[]
    for draw in draws:
        overrides=draw.get("overrides",{})
        if not isinstance(overrides,dict) or set(overrides)-allowed:
            raise InputError("unknown uncertainty override input")
        if any(str(k).startswith("_") for k in overrides.get("config",{})):
            raise InputError("uncertainty draws cannot change execution mode, request or claim identity")
        changed={k:_merge_mapping(value,overrides.get(k,{})) for k,value in definitions.items()}
        changed_config=_merge_mapping(baseline_config,overrides.get("config",{}))
        if "uncertainty_ensemble" in changed_config:
            raise InputError("nested uncertainty ensembles are not supported")
        target=Path(out)/draw["id"];target.mkdir(parents=True,exist_ok=True)
        write_json(target/"parameters.json",{"id":draw["id"],"inputs":changed,"config":changed_config})
        item={"id":draw["id"],"parameters_sha256":canonical_hash({"inputs":changed,"config":changed_config}),"corners":{},"status":"COMPLETE"}
        try:
            model=CoupledModel(changed_config,*[changed[n] for n in ("eos_bundle","nucleation_definition","wall_transport","collision_model","initial_history")])
            for corner in CORNERS:
                records,meta=model.solve(corner)
                summary=summarize(records,meta);summary.update(meta)
                if max(summary["max_relative_sector_balance"],summary["max_relative_radiation_balance"])>float(changed_config.get("balance_rtol",1e-5)):
                    raise RuntimeError("uncertainty draw fails energy-balance tolerance")
                item["corners"][corner]=summary
                write_json(target/f"raw_history_{corner}.json",{"records":records,"summary":summary})
        except (InputError,ValueError,RuntimeError) as exc:
            item["status"]="FAILED";item["reason"]=str(exc)
        outputs.append(item)
        write_json(target/"result.json",item)
    complete=all(x["status"]=="COMPLETE" for x in outputs)
    result={"status":"INCOMPLETE_UNCERTAINTY" if not complete else "SENSITIVITY_SET",
            "source":ensemble["source"],"interpretation":interpretation,
            "draw_count":len(draws),"draws":outputs,"corners":{},
            "sampling_uncertainty":"finite Monte Carlo sampling error is not included in percentile endpoints"}
    if complete:
        quantiles=[.025,.5,.975] if interpretation=="probability_samples" else [0,.5,1]
        for corner in CORNERS:
            result["corners"][corner]={}
            for n in ("1","10"):
                landmarks=[x["corners"][corner]["landmarks"][n] for x in outputs]
                interval={"phase_fraction":np.quantile([x["phase_fraction"] for x in landmarks],quantiles).tolist(),
                          "old_physical_volume":np.quantile([x["old_physical_volume"] for x in landmarks],quantiles).tolist(),
                          "delivered_energy_over_a0cubed_L":{s:np.quantile([x["delivered_energy_over_a0cubed_L"][s] for x in landmarks],quantiles).tolist() for s in SECTORS}}
                result["corners"][corner][n]=interval
        result["quantile_probabilities"]=quantiles
        if interpretation=="probability_samples":
            result["status"]="EMPIRICAL_PARAMETER_INTERVAL" if len(draws)>=40 else "INSUFFICIENT_PROBABILITY_SAMPLES"
            result["minimum_samples_for_reporting"]=40
    write_json(Path(out)/"summary.json",result)
    return result

def validate_number_changing_binding(relic, model):
    """A P6 NDA artifact may parameterize the declared scalar MB gas, not its lifetime."""
    if model.get("schema") != "R135-FMS-NDA-3to2-v1" or model.get("N") != 3:
        raise InputError("unsupported number-changing model; expected the sourced SU(3) scalar NDA artifact")
    require_source(model, "number-changing model")
    mass = finite(model.get("m0_MeV"), "NDA scalar mass", positive=True)
    if not math.isclose(mass, relic.get("mass_MeV", 0), rel_tol=1e-12):
        raise InputError("P6 3<->2 mass differs from the P7 relic")
    if relic.get("kinetic_model") != "relativistic_MB" or relic.get("degeneracy", 1) != 1:
        raise OpenInput("FMS scalar 3<->2 requires a single g=1 relativistic MB species")
    coefficient = finite(model.get("coefficient_MeV_minus5"), "3<->2 coefficient", positive=True)
    expected = finite(model.get("B"), "NDA multiplier", positive=True) * (4 * math.pi / 3) ** 6 / ((4 * math.pi) ** 3 * mass ** 5)
    if not math.isclose(coefficient, expected, rel_tol=1e-12) or not math.isclose(
            coefficient, relic.get("cannibal_MeV_minus5", 0), rel_tol=1e-12):
        raise InputError("P7 number-changing coefficient or MeV^-5 normalization differs from P6")
    closure = model.get("kinetic_equilibrium", {})
    require_source(closure, "kinetic equilibrium")
    threshold = finite(closure.get("required_ratio"), "relaxation margin", positive=True)
    if (closure.get("rate_kind") != "momentum_relaxation" or threshold <= 1
            or min(closure.get("minimum_rate_over_H", 0), closure.get("minimum_rate_over_chemical_rate", 0)) < threshold):
        raise OpenInput("P6 momentum-relaxation hierarchy does not justify the MB closure")
    domain = model.get("low_momentum_applicability", {})
    require_source(domain, "3<->2 applicability")
    limits = model.get("T_X_range_MeV", [])
    maximum = finite(domain.get("maximum_T_X_over_m0"), "low-momentum ratio", positive=True)
    if (len(limits) != 2 or not 0 < limits[0] < limits[1]
            or maximum >= 1 or limits[1] / mass > maximum
            or limits != domain.get("T_X_range_MeV")):
        raise InputError("inconsistent P6 low-momentum temperature domain")


def run(config, inputs, out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    def get(name):
        if name in inputs:
            return read_json(inputs[name])
        if name in config:
            return config[name]
        raise OpenInput(f"P7 missing {name}")
    eos, kernel, wall, collisions, initial = [get(n) for n in ("eos_bundle", "nucleation_definition", "wall_transport", "collision_model", "initial_history")]
    config=dict(config)
    if "number_changing_model" in inputs:
        number_model = read_json(inputs["number_changing_model"])
        if not isinstance(config.get("relic"), dict):
            raise OpenInput("a P6 3<->2 coefficient needs a separately specified P7 relic state, EOS and decay channels")
        config["relic"] = copy.deepcopy(config["relic"])
        if "cannibal_MeV_minus5" in config["relic"] or "number_changing_model" in config["relic"]:
            raise InputError("P7 cannot independently override a bound P6 number-changing coefficient")
        config["relic"]["cannibal_MeV_minus5"] = number_model.get("coefficient_MeV_minus5")
        config["relic"]["number_changing_model"] = number_model
        config["relic"]["number_changing_model_sha256"] = sha256(inputs["number_changing_model"])
        validate_number_changing_binding(config["relic"], number_model)
    source_binding=None
    if "gw_source" in inputs:
        if "gw_source" in config:
            raise InputError("select the P5 GW source artifact or an explicit source, not both")
        declared=read_json(inputs["gw_source"])
        if declared.get("schema")!="R135-GW-source-v1":
            raise InputError("P7 GW source must be a P5 source artifact")
        for field in ("point_id","model_id","thermal_path"):
            if config.get("_key") and declared.get(field)!=config["_key"][field]:
                raise InputError("P5 GW source belongs to another "+field)
        if declared.get("status")!="OPEN_INPUT":
            definition=declared.get("definition")
            if canonical_hash(definition)!=declared.get("source_sha256"):
                raise InputError("P5 GW source definition checksum differs")
            config["gw_source"]=definition
        source_binding=sha256(inputs["gw_source"])
    from .gravitationalwaves import source_artifact
    write_json(out/"gw_source.json",{**source_artifact(config.get("gw_source"),config.get("_key")),
                                     "source_P5_file_sha256":source_binding})
    if "thermalization_model" in inputs:
        thermalization=read_json(inputs["thermalization_model"])
        if config.get("_mode","conditional")!="validation" and thermalization.get("status")=="OPEN_INPUT":
            raise OpenInput("P6 thermalization_model is OPEN_INPUT")
        config.setdefault("thermalization_proof",thermalization)
    model = CoupledModel(config, eos, kernel, wall, collisions, initial)
    requested_corners = config.get("corners", list(CORNERS))
    if tuple(requested_corners) != CORNERS:
        raise InputError("P7 requires all five independent histories in the registered order")
    definitions={"eos_bundle":eos,"nucleation_definition":kernel,"wall_transport":wall,
                 "collision_model":collisions,"initial_history":initial}
    write_json(out/"history_definition.json",{"config":config,"inputs":definitions})
    all_rows, all_pockets, payload, balances = [], [], {}, {}
    for corner in CORNERS:
        checkpoint = out / f"checkpoint_{corner}.json"
        records, meta = model.solve(corner, checkpoint=checkpoint, resume=inputs.get(f"checkpoint_{corner}"))
        if config.get("pocket_geometry"):
            from .pockets import geometry_from_p7
            geometry=geometry_from_p7(records,config["pocket_geometry"])
            write_json(out/f"pocket_geometry_{corner}.json",geometry)
            meta["pocket_geometry_status"]="CONDITIONAL_GEOMETRY_COMPUTED_SURFACE_FEEDBACK_OPEN"
        payload[corner] = _payload(records)
        if config.get("_key"):
            payload[corner].update({field:config["_key"][field] for field in
                                   ("point_id","model_id","thermal_path")})
        summary = summarize(records, meta)
        summary.update(meta)
        balances[corner] = summary
        for row in records:
            flat = {k: row[k] for k in ("corner", "time_s", "tau_H0", "scale_factor", "H_s_inv", "T_X_MeV", "T_gamma_MeV", "T_nu_MeV", "T_free_MeV", "phase_fraction", "wall_temperature_MeV", "wall_speed", "f_dot_s_inv", "I", "old_physical_volume","old_fraction","nucleation_rate_MeV4","old_volume_log_growth_s_inv")}
            for i, s in enumerate(SECTORS):
                flat.update({f"rho_{s}_MeV4": row["rho"][i], f"p_{s}_MeV4": row["pressure"][i],
                             f"Q_{s}_MeV4_s": row["Q"][i], f"E_{s}_comoving_MeV4": row["comoving_energy_sources_MeV4"][i],
                             f"work_{s}_comoving_MeV4": row["comoving_pressure_work_MeV4"][i],
                             f"E4_{s}_MeV4":row["radiation_weighted_sources_MeV4"][i],
                             f"trace4_{s}_MeV4":row["radiation_trace_work_MeV4"][i]})
            all_rows.append(flat)
            all_pockets.append({"corner": corner, "time_s": row["time_s"], "I": row["I"],
                "old_volume": row["old_physical_volume"], "old_fraction": row["old_fraction"],
                "bubble_J0": row["bubble_moments"][0], "bubble_J1": row["bubble_moments"][1],
                "bubble_J2": row["bubble_moments"][2], "bubble_J3": row["bubble_moments"][3],
                "pocket_size_distribution": "NOT_DETERMINED_BY_HOMOGENEOUS_SURVIVAL"})
    limit = finite(config.get("balance_rtol", 1e-5), "balance tolerance", positive=True)
    failed = [k for k, v in balances.items() if max(v["max_relative_sector_balance"],v["max_relative_radiation_balance"]) > limit]
    write_csv(out / "phase_history.csv", all_rows)
    write_csv(out / "pocket_history.csv", all_pockets)
    write_json(out / "channel_history.json", {"schema": "R135-channel-history-v1",
        "units": {"time": "s", "temperature": "MeV", "density": "MeV^4", "rate": "s^-1"},
        "histories": payload, "initial_history": initial,
        "key":config.get("_key"), "source_GW_P5_file_sha256":source_binding,
        "history_model": "homogeneous_growth_with_quasistationary_boundary_layer",
        "thermalization_source": config["thermal_closure_source"],
        "physical_input_status": "CONDITIONAL", "scientific_acceptance": "owner_review"})
    propagated=propagate_uncertainty(config,definitions,out/"uncertainty")
    if propagated["status"]=="EMPIRICAL_PARAMETER_INTERVAL":
        for corner in CORNERS:
            if model.f0==1:
                continue
            interval=propagated["corners"][corner]
            balances[corner]["confidence_interval"]=interval
            lo1=interval["1"]["phase_fraction"][0]
            hi10=interval["10"]["phase_fraction"][2]
            balances[corner]["completion_classification"]=("CONDITIONAL_COMPLETION" if lo1>=.99 else
                "CONDITIONAL_PERSISTENCE" if hi10<.90 else "CONDITIONAL_UNRESOLVED")
    if propagated["status"]=="INCOMPLETE_UNCERTAINTY":
        failed.append("uncertainty_ensemble")
    write_json(out / "balance.json", {"sectors": list(SECTORS), "corners": balances,
        "balance_rtol": limit, "failed_corners": failed, "signed_energy_not_clipped": True,
        "uncertainty_ensemble": propagated})
    return {"software_status": "FAIL" if failed else "PASS", "evidence_status": "CONDITIONAL",
        "metrics": {"independent_histories": len(payload), "H0_s_inv": model.H0,
                    "max_sector_balance": max(b["max_relative_sector_balance"] for b in balances.values())},
        "limitations": ["Selected pocket geometry uses the actual nucleation/growth history; trapped-particle dynamics needs its own physical closure",
            "Bulk X uses a thermal phase EOS; selected kinetic nu/free/relic species use explicit momentum operators and reciprocal bath sources",
            "Completion confidence requires physical input uncertainty propagation",
            "BBN/CMB adapters separately require adequate temperature and late-time coverage"]}
