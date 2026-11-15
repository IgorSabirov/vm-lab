"""Host-validated D+D draws on pinned LINX nodes; no GP inference or science policy."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

import jax
import jax.numpy as jnp
import numpy as np

CHANNELS = ('ddHe3n', 'ddtp')
UNITS = 'cm^3 s^-1 g^-1'

@dataclass(frozen=True)
class DDTable:
    t9: object
    values: object
    encoding: str
    units: str

@dataclass(frozen=True)
class PreparedTables:
    tables: tuple
    effective_q: object
    network_fingerprint: str
    bounds_K: tuple[float, float]
    boundary_policy: str

def _host_array(value, label):
    try:
        a = np.asarray(value)
    except Exception as exc:
        raise ValueError(label + ': host validation must precede JIT/vmap') from exc
    if a.dtype.kind != 'f' or a.dtype.itemsize != 8:
        raise ValueError(label + ': float64 required; no silent precision conversion')
    if not np.all(np.isfinite(a)):
        raise ValueError(label + ': nonfinite value')
    return a

def network_fingerprint(net):
    rows = []
    for rxn in net.reactions:
        nodes = None if rxn.T9_vec is None else np.asarray(rxn.T9_vec, dtype='<f8').tolist()
        rows.append([rxn.name, list(rxn.in_states), list(rxn.out_states),
                     float(rxn.alpha), float(rxn.beta), float(rxn.gamma),
                     rxn.interp_type, nodes])
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()

def prepare_dd_tables(net, replacements: Mapping[str, DDTable], nuclear_rates_q=None,
                      *, temperature_bounds_K, boundary_policy='reject'):
    """Build native tables, zero the two native q's, replace only D+D.

    Each payload uses the reaction's existing encoding and exact nodes. The only
    accepted outside-grid alternative is explicit upstream-zero-linear, which
    preserves the pinned linear interpolator. Log extrapolation is forbidden.
    """
    if not jax.config.x64_enabled:
        raise ValueError('Enable JAX float64 before constructing LINX objects')
    if set(replacements) != set(CHANNELS):
        raise ValueError('Exactly the two named D+D channels must be supplied')
    names = tuple(r.name for r in net.reactions)
    if len(set(names)) != len(names) or tuple(net.reactions_names) != names:
        raise ValueError('Network reaction order/uniqueness mismatch')
    if any(names.count(n) != 1 for n in CHANNELS):
        raise ValueError('Missing or duplicated D+D channel')
    bounds = np.asarray(temperature_bounds_K, dtype=float)
    if bounds.shape != (2,) or not np.all(np.isfinite(bounds)) or not 0 < bounds[0] <= bounds[1]:
        raise ValueError('Invalid temperature bounds in K')
    if boundary_policy not in ('reject', 'upstream-zero-linear'):
        raise ValueError('Unknown boundary policy')
    q = np.zeros(len(names), dtype=np.float64) if nuclear_rates_q is None else _host_array(nuclear_rates_q, 'q').copy()
    if q.shape != (len(names),):
        raise ValueError('q shape differs from reaction list')
    encoded = {}
    for name in CHANNELS:
        i = names.index(name)
        q[i] = 0.0
        rxn, payload = net.reactions[i], replacements[name]
        if rxn.T9_vec is None or rxn.interp_type not in ('linear', 'log'):
            raise ValueError(name + ': a tabulated reaction is required')
        nodes = _host_array(payload.t9, name + ' nodes')
        expected = _host_array(rxn.T9_vec, name + ' upstream nodes')
        values = _host_array(payload.values, name + ' values')
        if nodes.ndim != 1 or nodes.size < 2 or np.any(np.diff(nodes) <= 0) or np.any(nodes <= 0):
            raise ValueError(name + ': invalid nodes')
        if not np.array_equal(nodes, expected) or values.shape != nodes.shape:
            raise ValueError(name + ': grid/value shape mismatch')
        if payload.units != UNITS or payload.encoding != rxn.interp_type:
            raise ValueError(name + ': units/encoding mismatch')
        if payload.encoding == 'linear':
            if np.any(values <= 0):
                raise ValueError(name + ': rates must be positive')
        else:
            # Zero/negative logarithms are valid. Unrepresentable rates are not.
            if np.any(values > np.log(np.finfo(np.float64).max)) or np.any(values < np.log(np.finfo(np.float64).tiny)):
                raise ValueError(name + ': log rate outside representable positive range')
        outside = bounds[0] < nodes[0] * 1e9 or bounds[1] > nodes[-1] * 1e9
        if outside and not (boundary_policy == 'upstream-zero-linear' and rxn.interp_type == 'linear'):
            raise ValueError(name + ': requested temperature range leaves the table')
        encoded[i] = jnp.asarray(values.copy())
    effective_q = jnp.asarray(q)
    tables = list(net.precompute_rate_tables(effective_q))
    for i, values in encoded.items():
        tables[i] = values
    return PreparedTables(tuple(tables), effective_q, network_fingerprint(net),
                          tuple(float(x) for x in bounds), boundary_policy)

def solve_with_dd(model, rho_g, rho_nu, rho_extra, p_extra, *, replacements,
                  nuclear_rates_q=None, boundary_policy='reject', **kwargs):
    """Validated non-jitted entry point for monotone standard-background solves.

    A future batch driver must validate every draw before a traced solve. This
    host wrapper intentionally does not pretend to be a traced GP-inference API.
    """
    from linx import const, thermo
    if 'rate_tables_override' in kwargs:
        raise ValueError('Pass the two named replacements, not unchecked full tables')
    temperatures = _host_array(thermo.T_g(jnp.asarray(rho_g)) / const.kB, 'background temperature')
    if temperatures.ndim != 1 or np.any(temperatures <= 0) or np.any(np.diff(temperatures) > 0):
        raise ValueError('Only positive monotone cooling histories are supported')
    start = float(kwargs.get('T_start', const.T_start)) / const.kB if kwargs.get('T_start') is not None else const.T_start / const.kB
    end = float(kwargs.get('T_end', const.T_end)) / const.kB if kwargs.get('T_end') is not None else const.T_end / const.kB
    if not 0 < end < start:
        raise ValueError('Invalid integration interval')
    # Validate the complete supplied history as well as requested endpoints.
    bounds = (min(float(temperatures.min()), end), max(float(temperatures.max()), start))
    prepared = prepare_dd_tables(model.nuclear_net, replacements, nuclear_rates_q,
                                temperature_bounds_K=bounds, boundary_policy=boundary_policy)
    return model(rho_g, rho_nu, rho_extra, p_extra,
                 nuclear_rates_q=prepared.effective_q,
                 rate_tables_override=prepared.tables, **kwargs)
