"""JSON-declared kinetic species embedded in the P7 Friedmann/heat state.

This adapter selects explicitly supplied cell collision operators. A supplied
rate is not claimed to be an independently computed X amplitude. The thermal
phase EOS remains the bulk X model; resolved kinetic relics must be excluded
from it. No density is counted both as a thermal bath and a kinetic species.
"""
from __future__ import annotations

import numpy as np

from .common import InputError, OpenInput, finite, require_source
from .kinetics import MomentumGrid, EmissionAbsorption, ConservativeScattering

SECTOR_INDEX = {"X": 0, "gamma": 1, "nu": 2, "free": 3, "relic": 4}


def _coefficient(value):
    """A supplied T-bath table permits feedback without executable input code."""
    if not isinstance(value,dict):return value
    require_source(value,"temperature-dependent kinetic rate")
    if value.get("kind")!="bath_temperature_table":
        raise OpenInput("unknown temperature-dependent kinetic coefficient")
    temperature=np.asarray(value["T_MeV"],float)
    rates=np.asarray(value["values_s_inv"],float)
    if (temperature.ndim!=1 or len(temperature)<2 or not np.isfinite(temperature).all()
            or np.any(temperature<=0) or np.any(np.diff(temperature)<=0)
            or rates.ndim not in (2,3) or rates.shape[0]!=len(temperature)
            or not np.isfinite(rates).all() or np.any(rates<0)):
        raise InputError("invalid bath-temperature collision-rate table")
    def at(time_s,a,bath_T_MeV):
        if not temperature[0]<=bath_T_MeV<=temperature[-1]:
            raise OpenInput("bath left the supplied kinetic rate temperature domain")
        i=min(np.searchsorted(temperature,bath_T_MeV,side='right')-1,len(temperature)-2)
        weight=(bath_T_MeV-temperature[i])/(temperature[i+1]-temperature[i])
        return (1-weight)*rates[i]+weight*rates[i+1]
    return at


class KineticCollection:
    def __init__(self, definitions, *, offset, a0):
        self.species = []
        self.sectors = set()
        self.size = offset
        names, roles = set(), set()
        for definition in definitions:
            require_source(definition, "kinetic species")
            name, sector = definition["name"], definition["sector"]
            if not isinstance(name, str) or not name or name in names or sector not in {"nu", "free", "relic"}:
                raise InputError("kinetic species need unique names and nu/free/relic sectors")
            names.add(name)
            if sector == "relic" and definition.get("excluded_from_phase_eos") is not True:
                raise OpenInput("kinetic relic energy must be excluded from the bulk X phase EOS")
            grid = MomentumGrid(definition["q_edges_MeV"], mass_MeV=definition.get("mass_MeV", 0),
                                degeneracy=definition["degeneracy"], statistics=definition["statistics"])
            initial = grid.occupation(definition["initial_occupation"])
            role = definition.get("role")
            if role in {"nu_e", "antinu_e"}:
                if role in roles or sector != "nu" or grid.mass != 0 or definition["statistics"] != "fermion" or grid.degeneracy != 1:
                    raise InputError("electron (anti)neutrino role requires one massless fermion helicity in nu")
                roles.add(role)
            operator = definition.get("operator", {"kind": "collisionless"})
            kind = operator["kind"]
            kernel = None
            bath = operator.get("bath")
            if kind != "collisionless":
                require_source(operator, "momentum collision operator")
                if bath not in {"X", "gamma"}:
                    raise OpenInput("these collision operators exchange energy with an explicit thermal X or gamma bath")
                if kind == "emission_absorption":
                    kernel = EmissionAbsorption(grid, _coefficient(operator["emission_s_inv"]), _coefficient(operator["absorption_s_inv"]), source=operator["source"])
                elif kind == "scattering":
                    kernel = ConservativeScattering(grid, _coefficient(operator["transition_s_inv"]), source=operator["source"])
                else:
                    raise OpenInput("unimplemented microscopic collision operator: " + str(kind))
            multipliers = operator.get("corner_multipliers", {c: 1. for c in ("00", "10", "01", "11full", "11add")})
            if set(multipliers) != {"00", "10", "01", "11full", "11add"}:
                raise InputError("kinetic corner multipliers must name all five independent histories")
            multipliers = {c: finite(v, "kinetic corner multiplier", nonnegative=True) for c, v in multipliers.items()}
            start = self.size
            self.size += grid.size
            self.species.append({"name": name, "sector": sector, "role": role, "grid": grid,
                                 "slice": slice(start, self.size), "initial": initial,
                                 "kernel": kernel, "bath": bath, "multipliers": multipliers,
                                 "definition": definition})
            self.sectors.add(sector)
        if "nu" in self.sectors and roles != {"nu_e", "antinu_e"}:
            raise OpenInput("kinetic neutrino history requires both resolved electron neutrino and antineutrino species")
        self.a0 = a0

    def initialize(self, state):
        for item in self.species:
            state[item["slice"]] = item["initial"]
        return state

    def moments(self, state, a):
        rho, pressure = np.zeros(5), np.zeros(5)
        records = []
        for item in self.species:
            occupation = np.asarray(state[item["slice"]])
            moments = item["grid"].moments(occupation, a)
            k = SECTOR_INDEX[item["sector"]]
            rho[k] += moments["rho_MeV4"]
            pressure[k] += moments["pressure_MeV4"]
            records.append({"name": item["name"], "sector": item["sector"], "role": item["role"],
                            "statistics": item["definition"]["statistics"],
                            "q_edges_MeV": item["grid"].q_edges.tolist(), "occupation": occupation.tolist(),
                            "mass_MeV": item["grid"].mass, "degeneracy":item["grid"].degeneracy, **moments})
        return rho, pressure, records

    def rhs(self, time_s, state, a, temperatures, corner, *, isolated):
        derivative, sources = np.zeros(self.size), np.zeros(5)
        for item in self.species:
            if item["kernel"] is None:
                continue
            # Isolation concerns the whole X sector, including its resolved
            # relics, and does not switch off SM-to-SM redistribution.
            crosses_x_boundary = ((item["sector"] == "relic") != (item["bath"] == "X"))
            if isolated and crosses_x_boundary:
                continue
            df = item["kernel"].rhs(time_s, state[item["slice"]], a, temperatures[item["bath"]])*item["multipliers"][corner]
            derivative[item["slice"]] = df
            q = item["grid"].source_moments(df, a)["energy_MeV4_s"]
            sources[SECTOR_INDEX[item["sector"]]] += q
            sources[SECTOR_INDEX[item["bath"]]] -= q
        return derivative, sources

    def validate_accepted(self, state):
        for item in self.species:
            item["grid"].occupation(state[item["slice"]])


def spectra_from_records(records):
    """Retain cell edges at every time; no lossy interpolation onto fixed p."""
    spectra = {}
    for role, key in (("nu_e", "f_nu_e"), ("antinu_e", "f_antinu_e")):
        values, edges = [], []
        for row in records:
            species = next((s for s in row.get("kinetic_species", []) if s["role"] == role), None)
            if species is None:
                break
            values.append(species["occupation"])
            edges.append((np.asarray(species["q_edges_MeV"])/row["scale_factor"]).tolist())
        if values:
            if len(values) != len(records):
                raise InputError("kinetic electron-neutrino role disappeared within a history")
            spectra[key] = {"energy_edges_MeV": edges, "values": values}
    return spectra
