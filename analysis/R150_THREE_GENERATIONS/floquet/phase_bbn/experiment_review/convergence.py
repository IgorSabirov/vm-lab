"""Refine only the four branches needed to isolate the graph contact in final yields."""
import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from intervention import BENCH, CaptureWindow, Config, OBS, solve, write_json


def evaluate(rtol):
    cfg = Config(**json.loads((BENCH / 'example.json').read_text()))
    cases = {}
    contrasts = {}
    for pulse, magnitude in [('off', 0.0), ('pulse', 0.10)]:
        outputs = []
        for label, contact, reverse in [('coupled', cfg.lam, True), ('mediated', cfg.lam, False),
                                        ('self_only', 0.0, True), ('zero_contact', 0.0, False)]:
            result = solve(CaptureWindow(magnitude), replace(cfg, lam=contact, reverse=reverse, rtol=rtol))
            cases[f'{label}_{pulse}'] = result
            outputs.append(np.log([result[key] for key in OBS]))
        a, b, c, d = outputs
        contrasts[pulse] = (a-b-c+d).tolist()
    difference = np.subtract(contrasts['pulse'], contrasts['off'])
    return dict(rtol=rtol, outputs=list(OBS), cases=cases, graph_interaction=contrasts,
                intervention_on_graph_interaction_ln=difference.tolist())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rtol', type=float, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    write_json(args.out, evaluate(args.rtol))
