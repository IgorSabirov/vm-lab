"""Extract centre lines of the printed fits in Christodoulou Fig. 5.4b."""
from pathlib import Path
import csv
import hashlib
import io
import json
import sys

import fitz
import numpy as np
from PIL import Image

BASE = Path(__file__).resolve().parent
EDITION = BASE.parents[1] / 'eos' / 'figure_5_10.json'
PANELS = [(1126, 3, 744, 15), (1127, 5, 746, 42), (1125, 1, 649, 70)]

def extract(pdf):
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != json.loads(EDITION.read_text())['pdf_sha256']:
        raise ValueError('The coordinates require the identified thesis edition')
    rows = []
    with fitz.open(pdf) as doc:
        images = {item[0] for item in doc[124].get_images()}
        for xref, left, right, hz in PANELS:
            assert xref in images
            image = doc.extract_image(xref)['image']
            rgb = np.asarray(Image.open(io.BytesIO(image)).convert('RGB'))
            for channel, color in [('COM', (23,60,126)), ('force', (0,170,0))]:
                mask = np.all(rgb == color, axis=2)
                for x in range(left+3, right-2):
                    ys = np.flatnonzero(mask[:, x])
                    if len(ys):
                        t_ms = 140 + (x-left)*120/(right-left)
                        rows.append((hz, channel, f'{t_ms:.9f}', -float(np.median(ys))))
    with (BASE/'phase_traces.csv').open('w', newline='') as out:
        writer = csv.writer(out, lineterminator='\n')
        writer.writerow(('drive_Hz','channel','time_ms','ordinate_pixels_up'))
        writer.writerows(rows)

if __name__ == '__main__':
    extract(Path(sys.argv[1]))
