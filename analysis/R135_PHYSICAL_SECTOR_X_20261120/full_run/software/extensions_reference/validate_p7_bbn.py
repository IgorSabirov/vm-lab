"""Computed P7 -> nonthermal weak integrals -> nonzero native nuclear networks.

This is a numerical development control with diagnostic X parameters, a
specified initial n/p mixture and no flavour oscillations. It is not a
calibrated cosmological prediction and does not run the full R135 matrix.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import time
import numpy as np

SOFTWARE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SOFTWARE),str(SOFTWARE/'tests')]
from r135 import history, backends, observations
from r135.kinetics import MomentumGrid
from r135.neutrino_rates import weak_rates_from_history
from r135.common import write_json,sha256,canonical_hash
from test_kinetic_history import kinetic_fixture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():parser.error('choose a new output directory')
    args.out.mkdir(parents=True)
    start=time.monotonic()
    definitions=kinetic_fixture()
    definitions[0].update(duration_H0=100,samples=257,max_step_H0=.2,rtol=1e-9,atol_relative=1e-12)
    # Explicitly retain the four mu/tau neutrino/antineutrino helicities.
    grid=MomentumGrid(np.linspace(0,5,25),degeneracy=4)
    for s in definitions[0]['kinetic_species']:s['operator']={'kind':'collisionless'}
    definitions[0]['kinetic_species'].append(dict(name='mu_tau',sector='nu',statistics='fermion',
        source='diagnostic four equal mu/tau helicities, no oscillations',degeneracy=4,q_edges_MeV=grid.q_edges.tolist(),
        initial_occupation=grid.fermi_dirac(1,.5).tolist(),operator={'kind':'collisionless'}))
    model=history.CoupledModel(*definitions)
    rows,meta=model.solve('00')
    computed=history._payload(rows)
    weak=weak_rates_from_history(computed)
    rates,reverse=backends.prepare_native_rates()
    nonzero=sum(bool(np.any(np.asarray(r['values'])>0)) for r in rates['reactions'])
    if nonzero!=12:raise RuntimeError('expected all twelve actual nuclear reaction tables')
    item=observations.adapt_history(computed,rates,weak,producer='computed kinetic P7 development control',
        created_utc='2026-11-20T00:00:00Z',initial_abundances=[.2,.8,0,0,0,0,0,0],
        applicability={'scope':'DIAGNOSTIC_X_INPUTS','weak_precision':'Born static nucleon, corrections open'})
    item['reverse_alpha_beta_gamma']=reverse
    write_json(args.out/'P7_inputs.json',definitions)
    write_json(args.out/'P7_history.json',computed)
    write_json(args.out/'P7_summary.json',{**meta,**history.summarize(rows,meta)})
    write_json(args.out/'weak_rates.json',weak)
    write_json(args.out/'BBN_input.json',item)
    pair=backends.NativePair();answers={};receipts={}
    policies=[{'rtol':1e-8,'atol':1e-12},{'rtol':1e-10,'atol':1e-14}]
    for engine in ('linx','primat'):
        for i,policy in enumerate(policies):
            tag=f'{engine}/{i}'
            answer,receipt=pair.solve(item,engine,policy,args.out/tag)
            if answer['D_H']<=0 or answer['Yp']<=1e-12:raise RuntimeError('nonzero network failed to synthesize nuclei')
            if receipt['history_sha256']!=item['canonical']['provenance']['history_sha256']:
                raise RuntimeError('native network did not read the computed P7 history')
            answers[tag]=answer;receipts[tag]=receipt
    differences={name:abs(answers['linx/1'][name]/answers['primat/1'][name]-1) for name in ('D_H','Yp')}
    refinements={engine:{name:abs(answers[engine+'/0'][name]/answers[engine+'/1'][name]-1) for name in ('D_H','Yp')}
                 for engine in ('linx','primat')}
    if max(differences.values())>1e-4 or max(v for d in refinements.values() for v in d.values())>1e-4:
        raise RuntimeError('native kernel/refinement control differs above registered 1e-4 diagnostic tolerance')
    summary={'scope':'COMPUTED_NONTHERMAL_P7_TO_NONZERO_BBN_CONTROL','physical_R135_run':False,
             'production_precision_validated':False,'actual_P7_history_sha256':observations.bridge_hash(computed),
             'nonzero_nuclear_tables':nonzero,'nuclear_tables_modified':False,'actual_native_solves':4,
             'P7_time_s':[computed['time_s'][0],computed['time_s'][-1]],
             'P7_T_gamma_MeV':[computed['T_gamma_MeV'][0],computed['T_gamma_MeV'][-1]],
             'P7_balance':history.summarize(rows,meta),'abundances':answers,'backend_relative_difference':differences,
             'refinement_relative_change':refinements,'native_receipts':receipts,'elapsed_seconds':time.monotonic()-start,
             'source_sha256':{str(p.relative_to(SOFTWARE)):sha256(p) for p in
                [Path(__file__),SOFTWARE/'tests/test_kinetic_history.py',SOFTWARE/'tests/test_history.py',
                 *[SOFTWARE/'r135'/name for name in ('history.py','kinetic_history.py','kinetics.py','neutrino_rates.py',
                     'observations.py','backends.py','common.py','thermodynamics.py','nucleation.py','collisions.py')]]},
             'limitations':['diagnostic bulk X/initial preparation, no model calibration',
                            'Born weak approximation, no neutrino flavour oscillations',
                            'two native refinements for one history, not the five-corner production gate',
                            'no late CMB or cascade prediction follows from this control']}
    write_json(args.out/'VALIDATION.json',summary)
    print({k:summary[k] for k in ('actual_native_solves','elapsed_seconds','backend_relative_difference','refinement_relative_change')})


if __name__=='__main__':main()
