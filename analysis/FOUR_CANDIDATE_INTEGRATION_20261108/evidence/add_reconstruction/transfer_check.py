#!/usr/bin/env python3
"""Exact transfer-matrix check. Requires SymPy and supplied sector_statistics."""
import json
import sympy as sp
import sector_statistics as s

out = {}
for quiet in (False, True):
    A = sp.zeros(16)
    for i in s.ALLOWED_STATES:
        for j in s.transition_table(quiet)[i]:
            A[i, j] = 1
    out['Q' if quiet else 'E0'] = {
        'characteristic_polynomial': str(sp.factor(A.charpoly().as_expr())),
        'trace_L6': int(sp.trace(A**6)),
        'trace_L12': int(sp.trace(A**12)),
        'trace_L100': int(sp.trace(A**100)),
    }
print(json.dumps(out, indent=2))
