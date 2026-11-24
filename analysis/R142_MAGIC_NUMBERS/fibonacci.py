"""Finite periodic approximants. Hopping 1; onsite A=0, B=contrast."""
import numpy as np


def audit():
    word = 'A'
    phi = (1 + np.sqrt(5)) / 2
    rows = []
    for iteration in range(1, 11):
        word = ''.join('AB' if s == 'A' else 'A' for s in word)
        if iteration < 7:
            continue
        n = len(word)
        k = word.count('B')
        row = dict(size=n, A=n-k, B=k, ids=k/n, predicted_limit=1/phi**2)
        for contrast in (0, 1):
            edges = []
            for twist in (1, -1):
                h = np.diag([float(contrast*(s=='B')) for s in word])
                h += np.diag(np.ones(n-1),1) + np.diag(np.ones(n-1),-1)
                h[0,-1] = h[-1,0] = twist
                edges.extend(np.linalg.eigvalsh(h))
            edges.sort()
            row[f'gap_contrast_{contrast}'] = edges[2*k]-edges[2*k-1]
        assert abs(row['gap_contrast_0'])<1e-10 and row['gap_contrast_1']>0
        rows.append(row)
    return rows
