"""Finite algebra and arithmetic for the review. Run from any directory with Python and NumPy."""
import hashlib
import importlib.util
import json
from collections import Counter
from itertools import product
from math import pi, sqrt
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ANALYSIS = HERE.parent
ENGINE = ANALYSIS / "ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py"
WITNESSES = ANALYSIS / "R132_ADD_YM_CCM_20261119/neighbor_review/duality_prediction.json"
OMEGA = np.exp(2j * pi / 3)


def samples(word, offsets):
    return Counter(tuple(word[(i + d) % len(word)] for d in offsets) for i in range(len(word)))


def shift(n):
    return np.roll(np.eye(n), 1, axis=0)


def commutator(a, b):
    return a @ b @ a.conj().T @ b.conj().T


def close(x, y):
    np.testing.assert_allclose(x, y, rtol=0, atol=1e-12)


def four_trace(proj, s):
    return np.trace(proj[1] @ s @ proj[2] @ s @ proj[1] @ s @ proj[2] @ np.linalg.matrix_power(s.T, 3))


def graph(word):
    n = len(word)
    s = shift(n)
    a = np.diag(OMEGA ** np.array(word))
    adjacent = samples(word, (0, 1))
    delta = adjacent[1, 2] - adjacent[2, 1]
    residual = abs(commutator(a, s).trace().imag / n - 3 * sqrt(3) * delta / (2*n))
    p = [np.diag(np.array(word) == j) for j in range(3)]
    four = samples(word, range(4))
    close(four_trace(p, s), four[2, 1, 2, 1])
    plus = sum(four[j, (j+1)%3, j, (j+1)%3] for j in range(3))
    minus = sum(four[(j+1)%3, j, (j+1)%3, j] for j in range(3))
    return residual, [delta, four[2, 1, 2, 1], four[1, 2, 1, 2], plus+minus, plus-minus]


def su3(seed):
    rng = np.random.default_rng(seed)
    m = rng.normal(size=(3, 3)) + 1j*rng.normal(size=(3, 3))
    q, r = np.linalg.qr(m)
    q = q @ np.diag(np.conj(np.diag(r)/np.abs(np.diag(r))))
    u, _, vh = np.linalg.svd(q)
    q = u @ vh
    q[:, -1] *= np.linalg.det(q).conjugate()
    return q


def twisted_trace(links, phases):
    n = len(links)
    total = 0j
    for k in range(phases):
        z = np.exp(2j*pi*k/phases)
        t = np.zeros((n, 3, n, 3), complex)
        for i, u in enumerate(links):
            t[i, :, (i+1)%n, :] = u * (z if i == n-1 else 1)
        t = t.reshape(3*n, 3*n)
        d = (t-t.conj().T)/2
        total += z.conjugate()*np.trace(np.linalg.matrix_power(d, n))
    return total*2**n/(phases*n)


def gauge_controls():
    a, b = np.diag(OMEGA ** np.arange(3)), shift(3)
    k = commutator(a, b)
    inverted = commutator(a.conj().T, b.T)
    values = [m.trace().imag/3 for m in (k, inverted, commutator(a.conj(), b.conj()), k.conj().T, commutator(OMEGA*a, b))]
    close(values, np.array([1, 1, -1, -1, 1])*sqrt(3)/2)
    a, b = su3(3), su3(9)
    close(commutator(a.conj().T, b.conj().T), (b@a).conj().T @ commutator(a, b) @ (b@a))
    g, h, v, eye = su3(17), su3(57), su3(32), np.eye(3)
    fixed = [[g, eye, eye], [h, h.conj().T@g, eye, eye], [h@v, v.conj().T@h.conj().T@g, eye, eye]]
    for links in fixed:
        for phases in (3, 4, 6):
            close(twisted_trace(links, phases), g.trace())
    return {"clock_shift_J": np.round(values, 12).tolist(), "fixed_g_Im_ell_cubed": round(float((g.trace()**3/27).imag), 12), "twist_and_frame_tolerance": 1e-12}


def thermal():
    hot, cold, latent = 1.471, .2928, 1.175
    r = hot/cold
    xi = (.044518075411783944/latent)**.25
    e = hot-.01768
    return {"a_end_over_start": r**(1/3), "H0_dt_end": (r**(2/3)-1)/2,
            "H0_dt_90": ((1-.9*(1-1/r))**(-2/3)-1)/2, "xi_budget": xi,
            "e_hot_over_Tc4": e, "rho_X_over_rho_visible": e*xi**4/(pi**2*10.75/30),
            "xi_equal_energy": (pi**2*10.75/(30*e))**.25,
            "xi_new_over_old": (1.413/latent)**.25, "nucleation_background_factor": (1.413/latent)**2}


def main():
    spec = importlib.util.spec_from_file_location("project_add", ENGINE)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    cases = json.loads(WITNESSES.read_text())["dynamics"]["cases"]
    pairs = {"short": ["00121221", "22121001"], "R131_24": cases["binary"]["words"]}
    output = {}
    for label, words in pairs.items():
        w, v = [tuple(map(int, a)) for a in words]
        assert all(samples(w, range(k)) == samples(v, range(k)) for k in (1, 2, 3))
        all_triples = all(samples(w, (0, d, e)) == samples(v, (0, d, e)) for d, e in product(range(len(w)), repeat=2))
        assert all_triples == (label == "R131_24")
        rows = []
        for word in (w, v):
            x = engine.named(word)
            lengths = [len(x)]
            for _ in range(4 if label == "short" else 2):
                x = engine.forward(x, (1,) if label == "short" else (1, -1))
                lengths.append(len(x))
            rows.append({"word": "".join(map(str, word)), "lengths": lengths,
                         "delta_N2121_N1212_Mplus_Mminus": graph(word)[1],
                         "N011_offsets_013": samples(word, (0, 1, 3))[0, 1, 1]})
        output[label] = {"rows": rows, "equal_triples_all_offsets": all_triples}
    assert [a['lengths'] for a in output['short']['rows']] == [[8,6,8,9,10],[8,6,7,9,9]]
    assert [a['lengths'] for a in output['R131_24']['rows']] == [[24,19,23],[24,19,24]]
    assert [a['delta_N2121_N1212_Mplus_Mminus'] for a in output['short']['rows']] == [[0,0,1,1,1],[0,1,0,1,-1]]
    assert [a['delta_N2121_N1212_Mplus_Mminus'] for a in output['R131_24']['rows']] == [[0,2,2,4,0],[0,1,1,2,0]]
    labels = np.array([1, 2, 2])
    phases = OMEGA ** labels
    occupation_odd = lambda v: np.imag(np.mean(v)**3)
    close(occupation_odd(phases), -sqrt(3)/9)
    close(occupation_odd(phases[::-1]), occupation_odd(phases))
    close(occupation_odd(phases.conj()), -occupation_odd(phases))
    output["I_122_reflection_conjugation"] = [round(float(occupation_odd(v)),12)
                                              for v in (phases, phases[::-1], phases.conj())]
    nwords = 0
    worst = 0.
    for n in range(1, 9):
        for w in product(range(3), repeat=n):
            worst = max(worst, graph(w)[0])
            nwords += 1
    assert nwords == 9840 and worst < 1e-12
    # A directed witness on which 2121 and its reverse have unequal counts.
    word = np.array([2, 1, 2, 1, 0, 0, 0, 0])
    a, s = np.diag(OMEGA**word), shift(len(word))
    p = [sum(OMEGA**(-j*k)*np.linalg.matrix_power(a,k) for k in range(3))/3 for j in range(3)]
    close(four_trace(p, s), 1)
    close(four_trace([p[0], p[2], p[1]], s), 0)
    close(np.trace(p[2]@s@p[1]@s@p[2]@s@p[1]@s), 0)
    output.update(word_count=nwords, algebra_tolerance=1e-12, gauge=gauge_controls(), thermal=thermal(),
                  input_sha256=hashlib.sha256((HERE/"NEIGHBOR_ORIGINAL.txt").read_bytes()).hexdigest(),
                  engine_sha256=hashlib.sha256(ENGINE.read_bytes()).hexdigest())
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
