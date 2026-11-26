"""Prospective kinetic intervention on n+p <-> D+gamma in the existing R150 bench."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np

BENCH = Path(__file__).resolve().parents[1] / 'network_bench'
sys.path.insert(0, str(BENCH))
from bench import Config, History, OBS, solve

HOT, COLD = .080, .060
OBSERVED = ('D', 'p_periodic', 'z_MeV', 'C_mean')


class CaptureWindow(History):
    def __init__(self, fraction):
        super().__init__()
        self.fraction = fraction
        if self.names[0] != 'npdg':
            raise ValueError('Unexpected first reaction')

    def forward_rates(self, T):
        rates = super().forward_rates(T)
        if self.fraction and COLD < T < HOT:
            phase = np.log(T/COLD) / np.log(HOT/COLD)
            rates[0] *= 1 + self.fraction*np.sin(np.pi*phase)**2
        # bench derives the inverse rate from this same forward coefficient.
        return rates


def write_json(path, values):
    path.write_text(json.dumps(values, indent=2, allow_nan=False)+'\n')


def surrogate(T, original, YD, max_correlation=None):
    """Fixed-seed band-limited-by-sampling phase shuffle on a uniform log-T grid."""
    grid = np.linspace(np.log(COLD), np.log(HOT), 257)
    local = np.interp(grid, np.log(T[::-1]), original[::-1])
    background = History()
    abundance = np.interp(grid, np.log(T[::-1]), YD[::-1])
    rho_b = np.exp(np.interp(grid, background.logT[::-1], background.logrho[::-1]))
    number_density = abundance * rho_b  # proportional to n_D, constant cancels in correlation
    ft = np.fft.rfft(local)
    rng = np.random.default_rng(150)
    for trial in range(1, 1001):
        phases = rng.uniform(0., 2*np.pi, len(ft)-1)
        shuffled = np.fft.irfft(np.r_[ft[0], ft[1:]*np.exp(1j*phases)], n=len(grid))
        correlation = float(np.corrcoef(local, shuffled)[0,1])
        corr_D = float(np.corrcoef(number_density, shuffled)[0,1])
        if max_correlation is None or abs(corr_D) <= max_correlation:
            break
    else:
        raise ArithmeticError('Unable to match requested correlation on the input grid')
    np.testing.assert_allclose(abs(np.fft.rfft(shuffled)),abs(ft),atol=2e-14)
    np.testing.assert_allclose(np.mean(shuffled**2),np.mean(local**2),rtol=1e-12)
    # Preserve the measured tails. The joins can change the two endpoint slopes.
    lt = np.log(T[::-1])
    x = np.r_[lt[lt<grid[0]],grid,lt[lt>grid[-1]]]
    y = np.r_[original[::-1][lt<grid[0]],shuffled,original[::-1][lt>grid[-1]]]
    diagnostics = dict(correlation_input=correlation,correlation_nD=corr_D,
                       original_correlation_nD=float(np.corrcoef(number_density,local)[0,1]),trial=trial)
    return np.c_[np.exp(x),y], diagnostics


def run(out, rtol):
    out.mkdir(exist_ok=True, parents=True)
    config = Config(**json.loads((BENCH/'example.json').read_text()))
    config = replace(config,rtol=rtol)
    results, contrasts, profiles = {}, {}, {}
    def one(label,c,amplitude):
        file = out/(label+'.csv')
        ans = solve(CaptureWindow(amplitude),c,save=file)
        results[label] = ans
        return np.genfromtxt(file,names=True,delimiter=',')
    for forward,reverse in [(0,0),(1,0),(0,1),(1,1)]:
        label = f'f{forward}r{reverse}'
        c = replace(config,forward=bool(forward),reverse=bool(reverse))
        for name,amp in [('off',0.),('pulse',.10)]:
            profiles[label+'_'+name] = one(label+'_'+name,c,amp)
    for name,amp in [('off',0.),('pulse',.10)]:
        profiles['lambda0_'+name] = one('lambda0_'+name,replace(config,lam=0.),amp)
    T = profiles['f1r1_off']['Tgamma_MeV']
    before = T>HOT
    after = T<COLD
    peak_with_temp = lambda arr,mask: {
        'value':float(arr[mask][np.argmax(abs(arr[mask]))]),
        'T_MeV':float(T[mask][np.argmax(abs(arr[mask]))])}
    for label in ['f0r0','f1r0','f0r1','f1r1','lambda0']:
        a,b = (profiles[label+'_'+name] for name in ('pulse','off'))
        np.testing.assert_array_equal(a['Tgamma_MeV'],b['Tgamma_MeV'])
        result = {}
        for key in OBSERVED:
            diff = a[key]-b[key]
            result[key] = {'pre_max_abs':float(max(abs(diff[before]))),
                           'peak':peak_with_temp(diff,~before),
                           'post':peak_with_temp(diff,after),
                           'final':float(diff[-1])}
        contrasts[label] = result
    def logy(name):
        return np.log([results[name][k] for k in OBS])
    def mixed(name):
        return logy('f1r1_'+name)-logy('f1r0_'+name)-logy('f0r1_'+name)+logy('f0r0_'+name)
    # Copy the full external input history from the coupled run on each side
    # of the intervention. The nuclear solver still receives the same np pulse.
    replay = {}
    for name,amp in [('off',0.),('pulse',.10)]:
        tr=profiles['f1r1_'+name]
        profile = out/('prescribed_'+name+'_input.csv')
        np.savetxt(profile,np.c_[T[::-1],tr['deltaBD_MeV'][::-1]],delimiter=',',header='T,B',comments='')
        forced=replace(config,mode='imposed',reverse=False,profile_file=str(profile.resolve()))
        one('prescribed_'+name,forced,amp)
        replay[name]=(logy('prescribed_'+name)-logy('f1r1_'+name)).tolist()
    baseline_profile = str((out/'prescribed_off_input.csv').resolve())
    one('fixed_profile_pulse', replace(config,mode='imposed',reverse=False,profile_file=baseline_profile),.10)
    fixed_gap = (logy('f1r1_pulse')-logy('f1r1_off')
                 -logy('fixed_profile_pulse')+logy('prescribed_off'))
    placebo = {}
    for label, limit in [('placebo',None), ('decorrelated',.05)]:
        reference = profiles['f1r1_off']
        table, diagnostics = surrogate(T, reference['deltaBD_MeV'], reference['D'], limit)
        file=out/(label+'_input.csv')
        np.savetxt(file,table,delimiter=',',header='T,B',comments='')
        one(label,replace(config,mode='imposed',reverse=False,profile_file=str(file.resolve())),0.)
        placebo[label] = dict(**diagnostics,
                              minus_prescribed_ln=(logy(label)-logy('prescribed_off')).tolist())
    def graph_interaction(name):
        # Subtract nuclear self-response with the same two reverse-arrow settings.
        return (logy('f1r1_'+name)-logy('f1r0_'+name)
                -logy('lambda0_'+name)+logy('zero_contact_'+name))
    for name,amp in [('off',0.),('pulse',.10)]:
        one('zero_contact_'+name,replace(config,lam=0.,reverse=False),amp)
    diff=mixed('pulse')-mixed('off')
    graph_diff=graph_interaction('pulse')-graph_interaction('off')
    audit = dict(rtol=rtol,temperature_window_MeV=[COLD,HOT],fraction=.10,outputs=list(OBS),
                 cases=results,signal=contrasts,feedback_mixed_off=mixed('off').tolist(),
                 feedback_mixed_pulse=mixed('pulse').tolist(),intervention_on_mixed_ln=diff.tolist(),
                 graph_interaction_off=graph_interaction('off').tolist(),
                 graph_interaction_pulse=graph_interaction('pulse').tolist(),
                 intervention_on_graph_interaction_ln=graph_diff.tolist(),
                 prescribed_minus_live_ln=replay,live_minus_fixed_pulse_effect_ln=fixed_gap.tolist(),
                 placebo=placebo)
    if max(r['max_baryon_error'] for r in results.values())>1e-9:
        raise ArithmeticError('Baryon residual')
    write_json(out/'summary.json',audit)
    return audit


if __name__ == '__main__':
    arg=argparse.ArgumentParser()
    arg.add_argument('--out',type=Path,required=True)
    arg.add_argument('--rtol',type=float,required=True)
    args=arg.parse_args()
    run(args.out,args.rtol)
