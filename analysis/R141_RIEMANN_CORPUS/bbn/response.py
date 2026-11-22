"""Linear response along the archived 384-point trajectory. No new background solve."""
import json
from pathlib import Path
import sys

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.linalg import expm


def trajectory_response(primat, archive, subdivisions, max_t9):
    sys.path.insert(0, str(Path(primat).resolve() / 'primat'))
    from network_builder import compile_network, NetworkKernels
    archive = Path(archive)
    doc = json.loads((archive / 'canonical.json').read_text())
    with np.load(archive / 'primat.npz') as saved:
        times, abundances = saved['time_s'], saved['Y']
    plasma = np.load(archive / 'plasma.npz')
    parameters = np.load(archive / 'rate_parameters.npz')
    reactions = doc['rates']['reactions']
    species = doc['rates']['species']
    names = [r['id'] for r in reactions]
    channels = ['dpHe3g','He3dap','ddHe3n','ddtp']
    selected = [names.index(n) for n in channels]
    topology = [({0:1},{1:1})]
    for r in reactions:
        topology.append(tuple({species.index(s): n for s,n in r[side].items()}
                              for side in ('reactants','products')))
    kernel = NetworkKernels(compile_network(topology,len(species)))
    history = doc['history']
    background_time = np.log(history['time_s'])
    # Original common-history convention: log Tγ and log a interpolated in log t.
    log_tg = np.log(history['T_gamma_MeV'])
    log_density = np.log(plasma['rho_b_g_cm3'])
    start = np.interp(np.log(max_t9 / 11.60451812), log_tg[::-1], background_time[::-1])
    ends = np.r_[start, np.log(times)[np.log(times)>start]]
    fine = np.interp(np.linspace(0, len(ends)-1, (len(ends)-1)*subdivisions+1),
                     np.arange(len(ends)), ends)
    midpoint = (fine[:-1]+fine[1:])/2
    steps = np.diff(np.exp(fine))
    t_mev = np.exp(np.interp(midpoint,background_time,log_tg))
    t9 = t_mev*11.60451812
    density = np.exp(np.interp(midpoint,background_time,log_density))
    y_mid = PchipInterpolator(np.log(times),abundances,axis=0)(midpoint)
    alpha,beta,gamma = parameters['reverse_alpha_beta_gamma']
    rates = np.empty((len(t9), 2+2*len(names)))
    for j,key in enumerate(['n_to_p_s_inv','p_to_n_s_inv']):
        rates[:,j] = np.interp(t_mev,plasma['weak_T_MeV'],plasma[key])
    logsigma = np.empty((len(t9),len(selected)))
    for i,r in enumerate(reactions):
        forward = np.interp(t9,r['T9'],r['values'],left=0,right=0)
        rates[:,2+2*i] = forward
        rates[:,3+2*i] = forward * alpha[i]*t9**beta[i]*np.exp(gamma[i]/t9)
        if i in selected:
            # Derivative through LINX's linear interpolation of the shifted ordinates.
            derivative = np.interp(t9,r['T9'],r['values']*np.log(parameters[names[i]]))
            logsigma[:,selected.index(i)] = derivative/forward
    sensitivity = np.zeros((2,len(t9),len(selected)))
    adjoint = np.zeros((2,len(species)))
    adjoint[0,2],adjoint[0,1] = 1/abundances[-1,2],-1/abundances[-1,1]
    adjoint[1,5] = 1/abundances[-1,5]
    n = len(species)
    for k in reversed(range(len(t9))):
        # Exact propagation for the local constant Jacobian and the selected reaction fluxes.
        block = np.zeros((n+len(selected),n+len(selected)))
        block[:n,:n] = kernel.jacobian(y_mid[k],density[k],rates[k])
        for j,i in enumerate(selected):
            direct = np.zeros(rates.shape[1])
            direct[2+2*i:4+2*i] = rates[k,2+2*i:4+2*i]
            block[:n,n+j] = kernel.rhs(y_mid[k],density[k],direct)
        step = expm(steps[k]*block)
        sensitivity[:,k,:] = adjoint @ step[:n,n:]
        adjoint = adjoint @ step[:n,:n]
    plasma.close()
    parameters.close()
    return t9, sensitivity, logsigma
