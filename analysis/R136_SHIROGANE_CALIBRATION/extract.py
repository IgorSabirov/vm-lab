"""Read original gnuplot vector geometry. Never execute the PostScript."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile

import numpy as np
from numpy.polynomial import Polynomial

FIGS = {
    "calibration": ("figs/bcnt.eps", "ed28e82bf6306e31e5c6cca3c2aa49434a7492936439e3c6a5cf214cff28ee72"),
    "fig3_48": ("fig/flowclx48t8_NL_u0.eps", "6b6fb2f747dea7ee5b7f313ee2c1b9f153fd28c9032ce43a74ae9518cb31f45f"),
    "fig3_64": ("fig/flowclx64t8_NL_u0.eps", "f78834c8551e9a98f28796c09867f264e40d621476d571f781d9a4d3a841bfbc"),
    "fig15": ("fig/histerisis_t8_NL_u0_b.eps", "fcf34ef90d02ab511003a4dee7573725f5d390982c80bf141f374da34d29a1f6"),
    "fig13": ("fig/ep_sftx_deriv_NL_u0.eps", "8351c6289aec7c68b5cb9b1b9517e72929880d4a5f0aea5ecac0136bc900ad78"),
    "fig16": ("fig/histerisis_derivative_b.eps", "4b3365ec743465b025237c6a4b2fdb9bbc7f4bfd76ce15a3bcb73342ab029a8a"),
}


def read_figure(archive, key):
    member, expected = FIGS[key]
    with tarfile.open(archive) as tar:
        raw = tar.extractfile(member).read()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"Unexpected source version for {member}")
    return raw.decode("latin-1")


def axes(eps):
    ticks = np.array(re.findall(r'(\d+) (\d+) M\n\[ \[\(Helvetica\).*?\(\s*([-\d.]+)\)\]', eps), float)
    x_ticks = ticks[ticks[:, 1] == 704]
    y_ticks = ticks[ticks[:, 0] == ticks[0, 0]]
    transforms = []
    for pix, val in [(x_ticks[:, 0], x_ticks[:, 2]), (y_ticks[:, 1], y_ticks[:, 2])]:
        assert len(pix) >= 5 and np.all(np.diff(pix) > 0) and np.all(np.diff(val) > 0)
        scale = Polynomial.fit(pix, val, 1)
        assert np.max(abs((scale(pix)-val)/scale.deriv()(pix))) < 0.7
        transforms.append(scale)
    return transforms


def points(eps, rgb, marker, expected):
    # In gnuplot 4.2 each coloured block has its own M/R/V moves followed by markers.
    # Legend markers are the last point in those blocks which also contain a legend.
    spans = re.split(r'^([\d.]+ [\d.]+ [\d.]+) C ', eps, flags=re.M)
    matches = []
    for color, body in zip(spans[1::2], spans[2::2]):
        if color != rgb:
            continue
        coords = re.findall(r'^(\d+) (\d+) '+marker+r'$', body, re.M)
        if len(coords) in (expected, expected+1):
            bars = {}
            x = y = 0
            for dx, dy, op in re.findall(r'^(-?\d+) (-?\d+) ([MRV])$', body, re.M):
                dx, dy = int(dx), int(dy)
                if op == 'M':
                    x, y = dx, dy
                else:
                    if op == 'V' and dx == 0 and dy > 0:
                        bars.setdefault(x, []).append((y, y+dy))
                    x, y = x+dx, y+dy
            series = []
            for xs, ys in coords[:expected]:
                x, y = int(xs), int(ys)
                # The first M may share its line with the colour instruction; splitting above preserves it.
                b = [v for v in bars.get(x, []) if abs(sum(v)/2-y) <= 1]
                assert len(b) == 1, (x,y,b)
                series.append((x,y,(b[0][1]-b[0][0])/2))
            matches.append(np.array(series))
    assert len(matches)==1, (rgb,marker,expected)
    tx, ty = axes(eps)
    x,y,e = matches[0].T
    return np.column_stack((tx(x),ty(y),e*ty.deriv()(y)))


def digitize(paper, scale_paper):
    eps = read_figure(scale_paper, "calibration")
    body = eps.split('% Begin plot #3')[1].split('% End plot #3')[0]
    ops = re.findall(r'^(-?\d+) (-?\d+) ([MV])$', body, re.M)
    assert [a[2] for a in ops] == ['M']+['V']*99
    x,y = np.cumsum([(int(a),int(b)) for a,b,_ in ops], axis=0).T
    tx, ty = axes(eps)
    out = {"calibration_curve_Nt_beta":np.column_stack((tx(x),ty(y))).round(9).tolist()}
    for ns in (48,64):
        mark = "Crs" if ns==48 else "CircleF"
        f3 = points(read_figure(paper, f"fig3_{ns}"),"0.00 0.39 0.00","CircleF",51)
        flow = {}
        for t in (0,1.4):
            sel = f3[abs(f3[:,0]-t)<.0006]
            assert len(sel)==1
            flow[str(t)]=sel[0,1:].round(9).tolist()
        data = {"fig3_jump_error":flow}
        for fig in ("fig15","fig16"):
            eps = read_figure(paper, fig)
            phases = {}
            for phase,rgb in [('hot','1.00 0.00 0.00'),('cold','0.00 0.00 1.00')]:
                count = 30 if fig=="fig15" else (26 if ns==48 else (24 if phase=="hot" else 23))
                rows = points(eps,rgb,mark,count)
                assert np.all(np.diff(rows[:,0]) > 0)
                phases[phase] = rows.round(9).tolist()
            data[fig+'_x_q_error'] = phases
        f13 = points(read_figure(paper,'fig13'),'0.00 0.39 0.00','TriU',2)
        data['fig13_derivative_jump_error'] = f13[0 if ns==48 else 1,1:].round(9).tolist()
        out[str(ns)] = data
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper",type=Path)
    parser.add_argument("scale_paper",type=Path)
    args = parser.parse_args()
    print(json.dumps(digitize(args.paper,args.scale_paper),separators=(',',':')))
