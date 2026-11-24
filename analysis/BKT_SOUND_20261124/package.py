"""Build the downloadable, self-contained audit from its tracked components."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
ROOT=Path(__file__).resolve().parent
FILES=['REPORT.md','model.py','lm.cpp','power.py','replay.py','verify.py','figure.py',
       'thermodynamics.py','package.py','tests/test_sound.py','run_design/PROTOCOL.md',
       'run_design/OWNER_SCOPE.md','preregistration/ANCESTOR_CONTRACTS.json',
       'preregistration/seal.sha256','preregistration/reveal.json','data/manifest.json',
       'data/cambridge.zip','data/S1.txt','data/S2.txt','results/BLIND.json',
       'results/POWER.json','results/PROFILE.json','results/CHECKS.json',
       'results/THERMO_INPUTS.csv','results/spectra.png','tests/test_eos.py',
       'eos/DESIGN.md','eos/REPORT.md','eos/theta.csv','eos/inversion.py','eos/joint.py',
       'eos/run.py','eos/resolution.py','eos/theta_sensitivity.py','eos/figure.py',
       'eos/results.json','eos/summary.csv','eos/resolution.json','eos/theta_sensitivity.json','eos/density.png']
if __name__=='__main__':
    with ZipFile(ROOT/'bkt-sound.zip','w') as z:
        for file in sorted(FILES):
            info=ZipInfo(file,date_time=(2026,11,24,0,0,0))
            info.external_attr=0o100644<<16
            z.writestr(info,(ROOT/file).read_bytes(),compress_type=ZIP_DEFLATED,compresslevel=9)
