"""Reproduce geometry and trapped-pocket controls; no R135 physical inputs."""
from pathlib import Path
import argparse
import sys
import numpy as np
SOFTWARE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SOFTWARE),str(SOFTWARE/'tests')]
from r135.pockets import C_CM_S,projected_distribution,voxel_geometry,evolve_thermal_pocket
from r135.common import write_json,sha256
from test_pockets import PocketTests


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args()
    if args.out.exists():parser.error('choose a new output directory')
    args.out.mkdir(parents=True)
    t=np.linspace(0,34,3401);istar=-np.log(.29);speed=2.
    h=dict(time_s=t.tolist(),scale_factor=np.ones(len(t)).tolist(),
           nucleation_rate_cm3_s=(istar/(8*np.pi*speed**3)*np.exp(t-30)).tolist(),
           wall_speed=np.full(len(t),speed/C_CM_S).tolist())
    projection=projected_distribution(h,3000)
    write_json(args.out/'projection_input.json',h);write_json(args.out/'projection.json',projection)
    t=np.linspace(0,1,101)
    h=dict(time_s=t.tolist(),scale_factor=np.ones(len(t)).tolist(),
           nucleation_rate_cm3_s=np.ones(len(t)).tolist(),wall_speed=np.full(len(t),1/C_CM_S).tolist())
    geometry=[voxel_geometry(h,box_comoving_cm=6,cells=n,seed=s,snapshot_indices=[100]) for n in (24,48) for s in range(8)]
    write_json(args.out/'geometry_input.json',h);write_json(args.out/'geometry.json',geometry)
    fractions={str(n):[r['snapshots'][0]['old_fraction'] for r in geometry if r['cells']==n] for n in (24,48)}
    pockets={}
    for name,xi,end in [('no_cooling',0,8),('cooling',.02,8),('cutoff',.1,12)]:
        cfg=PocketTests().fixture();cfg.update(surface_emissivity=xi,time_s=np.linspace(0,end,161).tolist())
        result=evolve_thermal_pocket(cfg)
        write_json(args.out/(name+'_input.json'),cfg);write_json(args.out/(name+'.json'),result)
        pockets[name]={'radius_final_cm':result['radius_cm'][-1], 'max_relative_energy_balance':result['max_relative_energy_balance'],
                       'termination':result['termination'],'max_compactness':result['max_compactness']}
    summary={'scope':'ANALYTIC_AND_STOCHASTIC_DEVELOPMENT_CONTROLS','physical_R135_run':False,
             'projection':{k:projection[k] for k in ('old_fraction','mean_radius_cm','volume_shape_factor_required','number_density_cm3')},
             'poisson_expected_old_fraction':float(np.exp(-np.pi/3)),
             'poisson':{n:{'mean':float(np.mean(f)),'standard_error':float(np.std(f,ddof=1)/np.sqrt(len(f)))} for n,f in fractions.items()},
             'same_seed_max_grid_fraction_shift':float(np.max(np.abs(np.array(fractions['24'])-fractions['48']))),
             'pockets':pockets,'source_sha256':{str(p.relative_to(SOFTWARE)):sha256(p) for p in [Path(__file__),SOFTWARE/'r135/pockets.py',SOFTWARE/'tests/test_pockets.py']},
             'limitations':['finite-box/grid geometry controls do not establish a physical X pocket spectrum',
                            'local spherical thermal closure is not global P7 feedback or general hydrodynamics']}
    write_json(args.out/'summary.json',summary);print(summary)


if __name__=='__main__':main()
