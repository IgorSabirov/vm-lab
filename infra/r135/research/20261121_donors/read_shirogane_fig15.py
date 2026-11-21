"""Read the vector markers and error bars of Shirogane et al., arXiv:2011.10292v2, Fig. 15."""
import argparse
import csv
import hashlib
import sys
from pathlib import Path

import fitz


PDF_SHA = "68dbd48c343f53cd73a93781d623853204503fc5330f660ea0cd4587c50e7e98"
# PDF drawing-object numbers on page 22. Legend symbols are excluded.
SERIES = [
    (48, "hot", 308, 180), (48, "cold", 309, 242), (48, "all", 307, 118),
    (64, "hot", 305, 19), (64, "cold", 306, 52), (64, "all", 304, 85),
]


def extract(pdf):
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != PDF_SHA:
        raise ValueError("Expected the published arXiv v2 PDF, identified by its SHA-256")
    with fitz.open(pdf) as doc:
        drawing = doc[21].get_drawings()
    # Visible tick labels: x = 0.988 ... 1.012, y = 0.2 ... 2.
    left, right = (drawing[i]["rect"].x0 for i in (10, 16))
    bottom, top = (drawing[i]["rect"].y0 for i in (0, 9))
    def xval(x):
        return 0.988 + 0.024 * (x - left) / (right - left)
    def yval(y):
        return 0.2 + 1.8 * (bottom - y) / (bottom - top)
    for i in range(7):
        assert abs(xval(drawing[10+i]["rect"].x0) - (0.988 + 0.004*i)) < 0.00001
    for i in range(10):
        assert abs(yval(drawing[i]["rect"].y0) - (0.2 + 0.2*i)) < 0.001
    for ns, phase, line_id, bars_id in SERIES:
        lines = drawing[line_id]["items"]
        centers = [lines[0][1]] + [end for _, _, end in lines]
        assert len(centers) == 30
        assert all(a.x < b.x for a,b in zip(centers,centers[1:]))
        bars = [segment for i in (bars_id, bars_id+1) for segment in drawing[i]["items"]
                if segment[0] == "l" and abs(segment[1].x-segment[2].x) < 0.001]
        markers = drawing[bars_id+2:bars_id+32] if ns == 64 else drawing[bars_id+2:bars_id+62:2]
        for center, marker in zip(centers, markers, strict=True):
            box = marker["rect"]
            assert marker["type"] == ("f" if ns == 64 else "s")
            assert abs(center.x - (box.x0+box.x1)/2) < 0.04
            assert abs(center.y - (box.y0+box.y1)/2) < 0.04
            pairs = [(a.y,b.y) for _,a,b in bars if abs(a.x-center.x)<0.04
                     and abs((a.y+b.y)/2-center.y)<0.05]
            assert len(pairs) == 1
            low, high = sorted(yval(y) for y in pairs[0])
            mid = yval(center.y)
            assert low < mid < high
            yield (ns, 8, ns//8, phase, f"{xval(center.x):.6f}", f"{mid:.5f}",
                   f"{mid-low:.5f}", f"{high-mid:.5f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["Ns","Nt","LT","series","T_over_Tc","w_over_T4","drawn_error_minus","drawn_error_plus"])
    writer.writerows(extract(args.pdf))
