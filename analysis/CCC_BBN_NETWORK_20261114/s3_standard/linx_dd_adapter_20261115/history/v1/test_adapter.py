"""Engineering tests only: reaction tables, RHS and JIT; no BBN integration."""
import dataclasses
import time

import jax
jax.config.update('jax_enable_x64', True)
import jax.numpy as jnp
import equinox as eqx
import numpy as np
import pytest
from linx.nuclear import NuclearRates
from linx import const
from dd_adapter import CHANNELS, UNITS, DDTable, prepare_dd_tables, network_fingerprint

METRICS = {}

@pytest.fixture(scope='module', params=['linear', 'log'])
def net(request):
    return NuclearRates(nuclear_net='key_PRIMAT_2023', interp_type=request.param)

def payloads(net, scale=1.0):
    result = {}
    for r in net.reactions:
        if r.name in CHANNELS:
            values = np.asarray(r.mu_median_vec, dtype=np.float64) * scale
            if r.interp_type == 'log':
                values = np.log(values)
            result[r.name] = DDTable(np.asarray(r.T9_vec, dtype=np.float64), values,
                                     r.interp_type, UNITS)
    return result

def prepare(net, inputs=None, q=None, **kwargs):
    kwargs.setdefault('temperature_bounds_K', (1e7, 1e9))
    return prepare_dd_tables(net, inputs or payloads(net), q, **kwargs)

def test_native_table_identity_and_other_nuisances(net):
    q = np.linspace(-0.4, 0.7, len(net.reactions), dtype=np.float64)
    before = q.copy()
    snapshot = network_fingerprint(net)
    p = prepare(net, q=q)
    expected_q = q.copy()
    for n in CHANNELS:
        expected_q[net.reactions_names.index(n)] = 0
    native = net.precompute_rate_tables(jnp.asarray(expected_q))
    for r, a, b in zip(net.reactions, p.tables, native):
        np.testing.assert_allclose(a, b, rtol=3e-15, atol=0)
        if r.name not in CHANNELS:
            original = net.precompute_rate_tables(jnp.asarray(q))[net.reactions_names.index(r.name)]
            np.testing.assert_array_equal(a, original)
    np.testing.assert_array_equal(q, before)
    np.testing.assert_array_equal(p.effective_q, expected_q)
    assert network_fingerprint(net) == snapshot

def test_single_channel_and_detailed_balance(net):
    data = payloads(net)
    old = prepare(net, data)
    n = CHANNELS[0]
    v = data[n].values
    v = v * 1.07 if net.interp_type == 'linear' else v + np.log(1.07)
    data[n] = dataclasses.replace(data[n], values=v)
    new = prepare(net, data)
    T = jnp.asarray(8e8)
    for i, r in enumerate(net.reactions):
        f0, f1 = r.frwrd_rate_from_table(T, old.tables[i]), r.frwrd_rate_from_table(T, new.tables[i])
        b0, b1 = r.bkwrd_rate_from_table(T, old.tables[i]), r.bkwrd_rate_from_table(T, new.tables[i])
        ratio = 1.07 if r.name == n else 1.0
        np.testing.assert_allclose(f1, ratio*f0, rtol=3e-14, atol=0)
        np.testing.assert_allclose(b1, ratio*b0, rtol=3e-14, atol=0)
        expected = r.alpha * (T*1e-9)**r.beta * jnp.exp(r.gamma/(T*1e-9)) * f1
        np.testing.assert_allclose(b1, expected, rtol=3e-14, atol=0)

@pytest.mark.parametrize('defect', ['shape', 'nan', 'inf', 'grid', 'encoding', 'units', 'float32', 'rate'])
def test_reject_invalid_inputs_before_jit(net, defect):
    data = payloads(net)
    key = CHANNELS[0]
    a = data[key]
    if defect == 'shape': a = dataclasses.replace(a, values=a.values[:-1])
    if defect in ('nan', 'inf', 'rate'):
        v = a.values.copy()
        v[0] = {'nan':np.nan, 'inf':np.inf, 'rate':0.0 if net.interp_type == 'linear' else 1000.0}[defect]
        a = dataclasses.replace(a, values=v)
    if defect == 'grid': a = dataclasses.replace(a, t9=a.t9*1.001)
    if defect == 'encoding': a = dataclasses.replace(a, encoding='unlabelled')
    if defect == 'units': a = dataclasses.replace(a, units='unlabelled')
    if defect == 'float32': a = dataclasses.replace(a, values=a.values.astype(np.float32))
    data[key] = a
    with pytest.raises(ValueError): prepare(net, data)

def test_reject_wrong_reactions_and_q(net):
    data = payloads(net)
    data['other'] = data.pop(CHANNELS[0])
    with pytest.raises(ValueError): prepare(net, data)
    with pytest.raises(ValueError): prepare(net, q=np.ones(1, dtype=np.float64))
    reordered = eqx.tree_at(lambda n:n.reactions_names, net, list(reversed(net.reactions_names)))
    with pytest.raises(ValueError): prepare(reordered)

def test_boundary_policy(net):
    with pytest.raises(ValueError): prepare(net, temperature_bounds_K=(1e7, 1e11))
    if net.interp_type == 'log':
        with pytest.raises(ValueError):
            prepare(net, temperature_bounds_K=(1e7,1e11), boundary_policy='upstream-zero-linear')
    else:
        p = prepare(net, temperature_bounds_K=(1e7,1e11), boundary_policy='upstream-zero-linear')
        for n in CHANNELS:
            i=net.reactions_names.index(n)
            assert float(net.reactions[i].frwrd_rate_from_table(jnp.asarray(1e11),p.tables[i])) == 0

def test_log_zero_and_negative_values_are_valid(net):
    if net.interp_type != 'log': return
    data=payloads(net)
    for n in CHANNELS:
        data[n]=dataclasses.replace(data[n],values=np.linspace(-10.,0.,len(data[n].values)))
    prepare(net,data)

def test_rhs_identity_and_jit_reuse(net):
    q=np.linspace(-0.1,0.2,len(net.reactions),dtype=np.float64)
    p0=prepare(net,q=q); p1=prepare(net,payloads(net,1.03),q=q)
    Y=jnp.asarray([0.12,0.87,0.004,0.0002,0.0003,0.0007,1e-10,1e-10])
    Ti=jnp.asarray([0.05,0.1,0.2]); weak=jnp.asarray([0.1,0.2,0.3])
    args=(Y,jnp.asarray(0.1),jnp.asarray(1e-5),Ti,weak,weak*1.1)
    native=jnp.asarray(net(*args,nuclear_rates_q=p0.effective_q))
    traces=[]
    @jax.jit
    def evaluate(tables):
        traces.append(1)
        return jnp.asarray(net(*args,rate_tables=tables))
    t=time.perf_counter(); y0=evaluate(p0.tables); y0.block_until_ready(); cold=time.perf_counter()-t
    t=time.perf_counter(); y1=evaluate(p1.tables); y1.block_until_ready(); warm=time.perf_counter()-t
    np.testing.assert_allclose(y0,native,rtol=5e-13,atol=1e-30)
    assert not np.array_equal(np.asarray(y0),np.asarray(y1))
    assert len(traces)==1
    METRICS[net.interp_type]={'rhs_cold_seconds':cold,'rhs_warm_seconds':warm,
                             'trace_count':len(traces),'max_abs_native_rhs_residual':float(jnp.max(jnp.abs(y0-native)))}
