"""Graph diagnostics along the stored CONTROL temperature and abundance history."""
from pathlib import Path
import csv
import math
import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.optimize import minimize_scalar


def evaluate(x_at):
    with Path(__file__).with_name("control.csv").open() as stream:
        data = sorted(csv.DictReader(stream), key=lambda row: float(row["t_s"]))
    times, selected = np.unique([float(row["t_s"]) for row in data], return_index=True)
    def column(name):
        return np.array([float(row[name]) for row in data])[selected]
    temp = column("T_MeV")
    deuterium = column("Y_D")
    helium = column("Y_He4")
    bind = (2.2246 * deuterium + 8.4818 * column("Y_T")
            + 7.7180 * column("Y_He3") + 28.2957 * helium)
    def at_temperature(array, T):
        return float(np.interp(T, temp[::-1], array[::-1]))
    # Normalize to this trace's helium abundance at 0.015 MeV.
    final = at_temperature(helium, .015)
    cuts = [np.flatnonzero(helium >= level * final)[0] for level in (.1, .5, .9)]
    bounds = [float(np.interp(level * final, helium[k-1:k+1], times[k-1:k+1]))
              for level, k in zip((.1,.5,.9), cuts)]
    peak = np.argmax(deuterium)
    def trial(L, J, barrier, samples):
        begin, end = bounds[0], bounds[-1]
        vis_temp = 2 * J / x_at(L - 1, .01)
        start = max(begin, at_temperature(times, vis_temp))
        if start >= end:
            return dict(T_vis_MeV=vis_temp, fraction_visible=0., exposure=0.,
                        weighted_opportunity=0.)
        grid = np.linspace(start, end, samples)
        T = np.interp(grid,times,temp)
        rate = (J / 6.582119569e-22) * np.exp(-barrier * J / T)
        # Reverse cumulative integral avoids subtracting large neighbouring counts.
        future = -cumulative_trapezoid(rate[::-1], grid[::-1], initial=0)[::-1]
        he = np.interp(grid, times, helium)
        total = np.interp(end,times,helium) - np.interp(begin,times,helium)
        increments = np.diff(grid) * (rate[:-1] + rate[1:]) / 2
        mean_survival = np.ones_like(increments)
        np.divide(-np.expm1(-increments), increments, out=mean_survival, where=increments > 0)
        opportunity = 1 - np.exp(-future[1:]) * mean_survival
        return dict(T_vis_MeV=vis_temp, fraction_visible=float((he[-1]-he[0])/total),
                    exposure=float(future[0]),
                    weighted_opportunity=float(np.sum(opportunity * np.diff(he))/total))
    trials = {}
    for L,J,barrier in [(7,.15,4),(7,.15,24),(7,.15,26),(7,.15,28),
                        (9,.222,4),(9,.222,16),(15,.40,4)]:
        key = f"L{L}_J{J}_c{barrier}"
        trials[key] = trial(L,J,barrier,8193)
        coarse = trial(L,J,barrier,4097)
        assert abs(trials[key]["weighted_opportunity"]-coarse["weighted_opportunity"]) < 1e-4
    return dict(helium_reference_at_0p015_MeV=4*final,
                helium_10_50_90=[dict(T_MeV=float(np.interp(t,times,temp)),t_s=t) for t in bounds],
                deuterium_peak_grid=dict(T_MeV=float(temp[peak]),t_s=float(times[peak]),Y_D=float(deuterium[peak])),
                samples={str(T):dict(Y_D=at_temperature(deuterium,T),
                        helium_mass=4*at_temperature(helium,T),binding_MeV_per_baryon=at_temperature(bind,T))
                        for T in (.10,.09,.08,.07,.06,.05,.03,.015)},
                graph_trials=trials)


def energy_peak(N, contrast):
    def energy(x):
        return -2*math.log1p(-contrast(N,x))/x
    best=minimize_scalar(lambda c:-energy(c*N*N), bounds=(.03,2),method="bounded")
    return dict(x=float(best.x*N*N), T_over_J=float(2/(best.x*N*N)),
                deltaF_over_J=float(-best.fun))
