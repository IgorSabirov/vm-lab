"""Compute drive-to-centre lags, conditional damping comparisons and width contrasts."""
import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from spectral import compare_spectra

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WINDOWS_MS = [(140, 260), (145, 255), (150, 250), (140, 200), (200, 260)]


def wrap(degrees):
    return (degrees + 180) % 360 - 180


def phase_at_frequency(samples, frequency, window):
    times, ordinate = np.asarray(samples).T
    keep = (times > window[0]) & (times < window[1])
    angle = 2 * np.pi * frequency * times[keep] / 1000
    design = np.column_stack((np.sin(angle), np.cos(angle), np.ones(len(angle))))
    y = ordinate[keep]
    start = np.linalg.lstsq(design, y, rcond=None)[0]
    fit = least_squares(lambda coefficients: design @ coefficients - y, start,
                        loss='soft_l1', f_scale=1.)
    if not fit.success:
        raise ValueError(f'Phase fit did not converge at {frequency} Hz')
    return np.arctan2(fit.x[1], fit.x[0])


def measure_phases():
    samples = {}
    with (HERE / 'phase_traces.csv').open() as f:
        for row in csv.DictReader(f):
            key = (int(row['drive_Hz']), row['channel'])
            samples.setdefault(key, []).append((float(row['time_ms']), float(row['ordinate_pixels_up'])))
    rows = []
    for frequency in sorted({key[0] for key in samples}):
        lags = []
        for window in WINDOWS_MS:
            drive = phase_at_frequency(samples[frequency, 'force'], frequency, window)
            com = phase_at_frequency(samples[frequency, 'COM'], frequency, window)
            lags.append(float(wrap(np.degrees(drive - com))))
        rows.append(dict(frequency_hz=frequency, lag_deg=lags[0], window_lags_deg=lags,
                         max_window_change_deg=float(np.max(np.abs(wrap(np.array(lags) - lags[0])))),
                         lag_shift_deg_per_ms=.36 * frequency))
    return rows


def compare_phase_laws(phases, fit, bogoliubov_hz):
    frequencies = np.array([row['frequency_hz'] for row in phases])
    observed = np.array([row['lag_deg'] for row in phases])
    w1, w2, g1, g2 = fit['physical'][:4]
    scale = 33 / 23
    s = -1j * frequencies / bogoliubov_hz
    degrees_per_ms = .36 * frequencies
    rows = []
    for p1 in (0, 1, 2):
        for p2 in (0, 1, 2):
            response = (fit['f1'] / (s*s + scale**p1*g1*s + (scale*w1)**2)
                        + fit['f2component'] / (s*s + scale**p2*g2*s + (scale*w2)**2))
            predicted = np.degrees(np.angle(response))
            residual = wrap(observed - predicted)
            delay = np.dot(degrees_per_ms, residual) / np.dot(degrees_per_ms, degrees_per_ms)
            after_delay = residual - degrees_per_ms * delay
            assert np.max(np.abs(after_delay)) < 180
            rows.append(dict(first_exponent=p1, second_exponent=p2, predicted_deg=predicted.tolist(),
                             rms_deg=float(np.sqrt(np.mean(residual**2))),
                             local_best_common_delay_ms=float(delay),
                             rms_after_delay_deg=float(np.sqrt(np.mean(after_delay**2)))))
    return rows


def width_contrasts(fit):
    assert fit['physical_order'][2:4] == ['Gamma1', 'Gamma2']
    widths = np.asarray(fit['physical'][2:4])
    result = {}
    for name in ('physical_boot_cov', 'physical_local_cov'):
        cov = np.array(fit[name])[2:4, 2:4]
        row = {'correlation': float(cov[0, 1] / np.sqrt(cov[0, 0] * cov[1, 1]))}
        for label, contrast in [('sum', np.array([1., 1.])), ('difference_1_minus_2', np.array([1., -1.]))]:
            row[label] = dict(value=float(contrast @ widths), sd=float(np.sqrt(contrast @ cov @ contrast)))
        result[name] = row
    return result


def calculate():
    fit = json.loads((ROOT / 'results' / 'BLIND.json').read_text())['S2']
    table = np.loadtxt(ROOT / 'data' / 'S2.txt', skiprows=1)
    comparison = json.loads((HERE.parent / 'repeat_boxes.json').read_text())
    scales = comparison['paired_frequency_grid_candidates']['cold']['42.5']['inferred_scales_hz']
    bogoliubov_hz = round(float(np.mean(scales)), 2)
    phases = measure_phases()
    return dict(source_revision='344d179bd5b0f4f8d915b8afbb4741ca787a1418', cold_bins=len(table),
                cold_scale_hz_for_conditional_transfer=bogoliubov_hz, phase_windows_ms=WINDOWS_MS,
                printed_phases=phases, phase_laws=compare_phase_laws(phases, fit, bogoliubov_hz),
                width_contrasts=width_contrasts(fit), spectra=compare_spectra(fit, table),
                matched_observed_width_ratio=comparison['observed_width_ratio'])


if __name__ == '__main__':
    (HERE / 'results.json').write_text(json.dumps(calculate(), indent=2, allow_nan=False) + '\n')
