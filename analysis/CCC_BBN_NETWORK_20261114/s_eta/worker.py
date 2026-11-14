"""Use the frozen S1 worker in S0 mode, with the declared eta configuration."""
import argparse
from pathlib import Path
import runpy
import sys
import common as c

ap=argparse.ArgumentParser()
ap.add_argument('--upstream',required=True);ap.add_argument('--root',required=True);ap.add_argument('--run-id',required=True)
args=ap.parse_args();sys.path.insert(0,str(Path(args.upstream).resolve()))
from primat.config import PRIMATConfig
params=c.config_for(args.run_id,Path(args.root)/'caches/BG8000')
cfg=PRIMATConfig(params)
anchor=PRIMATConfig(c.read(c.PARENT_ROOT/'runs/R8/MANIFEST.json')['config'])
target=anchor.eta0b*c.row_for(args.run_id)['eta_factor']
audit={'eta_baseline':anchor.eta0b,'eta_target':target,'eta_resolved':cfg.eta0b,
       'Omegabh2':cfg.Omegabh2,'conversion':cfg.Omegabh2_to_eta0b,
       'relative_roundtrip_residual':abs(cfg.eta0b/target-1),
       'relative_mapping_residual':abs(cfg.Omegabh2*cfg.Omegabh2_to_eta0b/target-1)}
if max(audit['relative_roundtrip_residual'],audit['relative_mapping_residual'])>1e-14:
    raise ValueError('eta mapping failed')
c.write(Path(args.root)/'ETA_INPUTS'/f'{args.run_id}.json',audit)
# common already resolves to this package; original worker source is unchanged.
runpy.run_path(str(c.PKG.parent/'s1_fullnet/worker.py'),run_name='__main__')
