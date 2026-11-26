"""Run independent CPU cases with atomic, resumable per-case records."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from zipfile import ZipFile

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from intervention import BENCH, CaptureWindow, Config, History, OBS, solve

BASE = Config(**json.loads((BENCH/'example.json').read_text()))
RTOL = 7e-10


def native(name):
    with ZipFile(HERE.parent/'results/e6_trajectories.zip') as archive:
        with archive.open(name+'.csv') as stream:
            return np.genfromtxt(stream, names=True, delimiter=',')


def net(h, cfg, profile=None, track=False):
    with tempfile.TemporaryDirectory() as tmp:
        if profile is not None:
            file = Path(tmp)/'profile.csv'
            np.savetxt(file,profile,delimiter=',',header='T,B',comments='')
            cfg = replace(cfg,mode='imposed',reverse=False,profile_file=str(file))
        file = Path(tmp)/'trace.csv'
        result = solve(h,cfg,save=file if track else None)
        if track:
            rows = np.genfromtxt(file,names=True,delimiter=',')
            result['trace'] = {k:rows[k].tolist() for k in ('Tgamma_MeV','D','p_periodic','z_MeV','drive_MeV')}
    return result


def timed(task):
    module, name, args = task
    begin = time.process_time()
    result = importlib.import_module(module).case(*args)
    return name, dict(result=result,cpu_s=time.process_time()-begin)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('module',choices=['ensemble','scans','nuclear'])
    parser.add_argument('out',type=Path)
    parser.add_argument('--workers',type=int,default=6)
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True,parents=True)
    manifest = importlib.import_module(args.module).manifest()
    jobs = [(args.module,k,v) for k,v in manifest.items() if not (args.out/(k+'.json')).exists()]
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(timed,j):j[1] for j in jobs}
        for future in as_completed(futures):
            name, record = future.result()
            dest = args.out/(name+'.json')
            tmp=dest.with_suffix('.part')
            tmp.write_text(json.dumps(record,separators=(',',':'),allow_nan=False))
            tmp.replace(dest)
    files=[json.loads((args.out/(k+'.json')).read_text()) for k in manifest]
    stats=dict(cases=len(files),new_cases=len(jobs),workers=args.workers,
               elapsed_s=time.monotonic()-started,cpu_s=sum(r['cpu_s'] for r in files))
    (args.out/'_timing.json').write_text(json.dumps(stats,indent=2)+'\n')
    print(stats)


if __name__ == '__main__':
    main()
