"""Offline serial SQRT trajectories with explicit counts, timers and checkpoints."""
import json
import os
import shutil
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.integrate import simpson
from scipy.sparse.linalg import expm_multiply

from sqrt_exp.model import save_json, sha, validate, rk4, maxabs, make_direct_rhs


def initial(case):
    a = np.zeros(216, complex)
    b = a.copy()
    a[np.ravel_multi_index((1, 0, 0, 1, 1, 1), (2, 2, 2, 3, 3, 3))] = 1
    b[np.ravel_multi_index((0, 1, 0, 1, 1, 1), (2, 2, 2, 3, 3, 3))] = 1
    if case['state'] == 'mix':
        rho = (np.outer(a, a.conj()) + np.outer(b, b.conj())) / 2
    else:
        psi = (a + np.exp(1j * case['phase_index'] * np.pi / 2) * b) / np.sqrt(2)
        rho = np.outer(psi, psi.conj())
    return rho.reshape(-1, order='F')


class Progress:
    def __init__(self, total):
        self.start = time.monotonic()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.data = {'experiment': 'E001X_J0', 'total_cases': total, 'completed_cases': 0}
        self.thread = threading.Thread(target=self.beat, daemon=True)
        self.thread.start()

    def update(self, **kwargs):
        with self.lock:
            self.data.update(kwargs)
            self.data.update(elapsed_seconds=time.monotonic() - self.start,
                             heartbeat_utc=datetime.now(timezone.utc).isoformat())
            save_json('progress.json', self.data)

    def beat(self):
        while not self.stop.wait(5):
            self.update()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)


def preflight(model, config):
    dt = config['integration']['dt']
    v = initial({'state': 'phase', 'phase_index': 0})
    rng = np.random.default_rng(20261028)
    a = rng.normal(size=(216, 3)) + 1j * rng.normal(size=(216, 3))
    rho = a @ a.conj().T
    rho /= np.trace(rho)
    rv = rho.reshape(-1, order='F')
    direct = make_direct_rhs(model['H'], model['jumps'])(rv)
    rhs_error = float(np.linalg.norm(model['L'] @ rv - direct) / np.linalg.norm(direct))
    coarse, fine = v.copy(), v.copy()
    for _ in range(round(1 / dt)):
        coarse = rk4(model['L'].dot, coarse, dt)
    for _ in range(round(2 / dt)):
        fine = rk4(model['L'].dot, fine, dt / 2)
    exact = expm_multiply(model['L'], v)
    expm_error = float(np.linalg.norm(coarse - exact) / np.linalg.norm(exact))
    refinement = maxabs(model['rows'] @ (coarse - fine))
    checks = {'rhs_relative_error': rhs_error, 'expm_relative_error': expm_error,
              'dt_halving_max_observable_difference': refinement,
              'rk4_steps': round(3 / dt), 'state': validate(coarse, config['acceptance'], True)}
    checks['passed'] = (rhs_error < 1e-12 and expm_error <= config['acceptance']['expm_reference_relative']
                        and refinement <= config['acceptance']['refinement_observables'])
    if not checks['passed']:
        raise RuntimeError('Preflight failure: ' + json.dumps(checks))
    return checks


def snapshot(v, case, step):
    folder = Path('states') / case['id']
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'rho_step{step:06d}.npz'
    temp = path.with_suffix('.tmp')
    with temp.open('wb') as f:
        np.savez_compressed(f, rho=v.reshape((216, 216), order='F'), time=step*case['dt'],
                            step=step, case_json=json.dumps(case))
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    event = {'case_id': case['id'], 'step': step, 'time': step*case['dt'], 'path': str(path),
             'sha256': sha(path), 'bytes': path.stat().st_size}
    with Path('snapshot_events.jsonl').open('a') as f:
        f.write(json.dumps(event) + '\n')
        f.flush()
        os.fsync(f.fileno())
    save_json('checkpoint_latest.json', event)
    return event


def run_case(case, model, config, progress, completed):
    started = time.monotonic()
    timing = dict(integration=0., observations=0., diagnostics=0., checkpoint_io=0.)
    dt, endpoint = case['dt'], case['horizon']
    nsteps = round(endpoint / dt)
    obs_every = round(config['integration']['observable_interval'] / dt)
    snap_every = round(config['integration']['rho_interval'] / dt)
    if abs(nsteps*dt-endpoint) > 1e-10 or obs_every < 1 or snap_every < 1:
        raise ValueError('Invalid integration grid')
    v = initial(case)
    index, names, L = model['index'], model['names'], model['L']
    samples, diagnostics, events = [], [], []
    window = deque(maxlen=round(10/config['integration']['rho_interval'])+1)
    folder = Path('cases')
    folder.mkdir(exist_ok=True)
    save_json(folder / (case['id']+'_schema.json'), {'case': case, 'observable_names': names})
    with (folder / (case['id']+'.jsonl')).open('w') as stream:
        for step in range(nsteps+1):
            if step:
                tick = time.monotonic()
                v = rk4(L.dot, v, dt)
                timing['integration'] += time.monotonic()-tick
            if step % obs_every == 0:
                tick = time.monotonic()
                row = np.asarray(model['rows'] @ v)
                if not np.isfinite(row).all() or maxabs(row.imag) > 1e-8:
                    raise RuntimeError('Invalid expectation values')
                vals = row.real.tolist()
                samples.append((step*dt, vals))
                stream.write(json.dumps({'time': step*dt, 'values': vals}, allow_nan=False)+'\n')
                timing['observations'] += time.monotonic()-tick
            if step % snap_every == 0:
                tick = time.monotonic()
                t = step*dt
                check = validate(v, config['acceptance'], abs(t/config['integration']['positivity_interval']-round(t/config['integration']['positivity_interval'])) < 1e-9)
                node = np.einsum('abcb->ac', v.reshape((216,216), order='F').reshape(8,27,8,27))
                check.update(time=t, relative_rhs=float(np.linalg.norm(L@v)/np.linalg.norm(v)),
                             node_coherence_fro=float(np.linalg.norm(node-np.diag(np.diag(node)))))
                diagnostics.append(check)
                window.append({'time': t, 'relative_rhs': check['relative_rhs'], 'v': v.copy()})
                timing['diagnostics'] += time.monotonic()-tick
                tick = time.monotonic()
                stream.flush()
                os.fsync(stream.fileno())
                event = snapshot(v, case, step)
                events.append(event)
                progress.update(status='running', current_case=case['id'], model_time=t,
                                target_time=endpoint, current_step=step, target_steps=nsteps,
                                completed_cases=completed, last_checkpoint=event)
                if shutil.disk_usage('.').free < config['acceptance']['disk_floor_bytes']:
                    raise RuntimeError('Declared disk reserve reached')
                timing['checkpoint_io'] += time.monotonic()-tick
    times = np.array([x[0] for x in samples])
    values = np.array([x[1] for x in samples])
    recent = values[times >= endpoint-10-1e-9, index['sink_flux']]
    stat = {'window_start': window[0]['time'], 'window_end': window[-1]['time'],
            'max_relative_rhs': max(x['relative_rhs'] for x in window),
            'relative_flux_range': float(np.ptp(recent)/max(abs(recent[-1]),1e-14)),
            'relative_rho_change': float(np.linalg.norm(window[-1]['v']-window[0]['v'])/np.linalg.norm(v))}
    limits = config['stationarity']
    stat['absolute_flux_range'] = float(np.ptp(recent))
    stat['flux_range_bound'] = limits.get('absolute_flux_range', 0.) + limits['relative_flux_range']*abs(float(recent[-1]))
    stat['passed'] = bool(endpoint >= 10 and stat['max_relative_rhs'] <= limits['relative_rhs']
                          and stat['absolute_flux_range'] <= stat['flux_range_bound']
                          and stat['relative_rho_change'] <= limits['relative_rho_change'])
    take = lambda k: values[:,index[k]]
    balance = maxabs(take('dn2_dt') - take('I_hop_sink') - take('I_form_sink') - take('I_idle_sink') + take('sink_flux'))
    partition = maxabs(take('B_L_total')+take('M_L_total')+take('E_L_total')-take('sum_pL'))
    if max(balance, partition) > config['acceptance']['algebra']:
        raise RuntimeError('Recorded balance identity failed')
    selected = ['sink_flux','I_hop_sink','I_form_sink','I_idle_sink','pump_flux','break_flux']
    integrals = {k: float(simpson(take(k), x=times)) for k in selected}
    integrals['stored_sink'] = float(take('n2')[0]-take('n2')[-1])
    integrals['sink_balance_residual'] = integrals['sink_flux']-sum(integrals[k] for k in ['I_hop_sink','I_form_sink','I_idle_sink','stored_sink'])
    integrals['inventory_change'] = float(take('inventory')[-1]-take('inventory')[0])
    integrals['inventory_balance_residual'] = integrals['inventory_change']-integrals['pump_flux']+integrals['break_flux']
    summary = {'case':case, 'stationarity':stat, 'final_observables':dict(zip(names, values[-1].tolist())),
               'timing_seconds':timing, 'elapsed_seconds':time.monotonic()-started,
               'steps':nsteps, 'rhs_calls':4*nsteps, 'scalar_records':len(times), 'snapshots':len(events),
               'integrals':integrals, 'recorded_balance_max':balance, 'partition_max':partition,
               'state_quality':{'max_trace_error':max(d['trace_error'] for d in diagnostics),
                                'max_hermiticity_error':max(d['hermiticity_error'] for d in diagnostics),
                                'min_sampled_eigenvalue':min(d['min_eigenvalue'] for d in diagnostics if 'min_eigenvalue' in d)},
               'final_node_coherence_fro':diagnostics[-1]['node_coherence_fro'],
               'last_checkpoint':events[-1]}
    save_json(folder / (case['id']+'_diagnostics.json'), diagnostics)
    save_json(folder / (case['id']+'.json'), summary)
    return summary
