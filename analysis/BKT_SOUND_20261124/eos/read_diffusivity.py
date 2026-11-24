"""Read blue D2 marker centres from Christodoulou Fig. 5.10, printed page 119."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import fitz
import numpy as np
from scipy.ndimage import find_objects, label

PDF_SHA = 'cb952375f3392ccb0bc51017c70bbba4dc672855e874d2b2a2c3f32bfa22b06f'
HERE = Path(__file__).resolve().parent


def extract(pdf):
    if sha256(pdf.read_bytes()).hexdigest() != PDF_SHA:
        raise ValueError('Expected archived Cambridge thesis PDF (DOI 10.17863/CAM.82718)')
    with fitz.open(pdf) as doc:
        page = doc[132]
        if 'Figure 5.10:' not in page.get_text():
            raise ValueError('Unexpected PDF page')
        pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=fitz.Rect(205, 85, 412, 234),
                              colorspace=fitz.csRGB, alpha=False)
    r, g, b = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height,pix.width,3).astype(int).transpose(2,0,1)
    # Blue marker interiors are lavender, their outlines black, and their bars dark blue.
    interior = (b-r > 24) & (abs(g-r) < 12) & (r > 110) & (r < 175)
    marks, _ = label(interior)
    points = []
    for k, bounds in enumerate(find_objects(marks), start=1):
        if np.sum(marks[bounds] == k) < 150:
            continue
        y, x = [(s.start+s.stop-1)/2 for s in bounds]
        # Calibration uses the plot ticks, not the positions of the tabulated temperatures.
        t = .6 + (x-171.5)*.8/(662-171.5)
        diffusivity = (560-y)*10/(560-224)
        points.append(dict(pixel_x=x,pixel_y=y,t_graph=round(t,5),
                           D2_over_hbar_m=round(diffusivity,3)))
    if len(points) != 6:
        raise ValueError('Expected six second-sound markers')
    return dict(doi='10.17863/CAM.82718', pdf_sha256=PDF_SHA, figure='5.10', pdf_page=133,
                tick_pixels=dict(x_at_t_0p6=171.5,x_at_t_1p4=662,y_at_D_0=560,y_at_D_10=224),
                points=sorted(points,key=lambda p:p['pixel_x']))


def extract_vector(pdf):
    digest = sha256(pdf.read_bytes()).hexdigest()
    if digest != 'cd9aa9a93e170913963e0e2ecd710e63ee4b8007ce6f0b852d3cbf751d07d0ef':
        raise ValueError('Expected Cambridge thesis PDF (DOI 10.17863/CAM.96553)')
    with fitz.open(pdf) as doc:
        page = doc[70]
        if 'Fig. 4.9:' not in page.get_text():
            raise ValueError('Unexpected PDF page')
        paths = page.get_drawings()
    # Vector tick marks at t=0.5,1.5 and D=0,10; PDF points, y increasing downwards.
    x0,x1,y0,y10 = 232.81,352.81,160.83,104.11
    output = {}
    for mode,rgb,count in [('D1',(153,0,0),9),('D2',(23,60,126),6),('DT',(0,113,0),3)]:
        bars = [p['rect'] for p in paths if len(p['items'])==1 and p['items'][0][0]=='l'
                and tuple(round(255*c) for c in p['color'])==rgb]
        if len(bars) != 4*count:
            raise ValueError('Expected four error bar segments per point')
        points = []
        for i in range(0,len(bars),4):
            left,right,low,high = bars[i:i+4]
            x,y = left.x1,left.y1
            if max(abs(x-right.x0),abs(y-right.y0),abs(low.x1-x),abs(high.x1-x),
                   abs(low.y0-y),abs(high.y1-y))>.01:
                raise ValueError('Error bars do not share a centre')
            points.append(dict(t_graph=round(.5+(x-x0)/(x1-x0),5),
                               t_halfbar=round((right.x1-left.x0)/(2*(x1-x0)),5),
                               D_over_hbar_m=round((y0-y)*10/(y0-y10),3),
                               D_halfbar=round((low.y1-high.y0)*5/(y0-y10),3)))
        output[mode] = sorted(points,key=lambda v:v['t_graph'])
    return dict(doi='10.17863/CAM.96553',pdf_sha256=digest,figure='4.9',pdf_page=71,modes=output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('thesis',type=Path)
    parser.add_argument('galka',type=Path)
    args = parser.parse_args()
    (HERE/'figure_4_9.json').write_text(json.dumps(extract_vector(args.galka),indent=2)+'\n')
    (HERE/'figure_5_10.json').write_text(json.dumps(extract(args.thesis),indent=2)+'\n')
