"""Compute two real CLASS spectra and consume each with pinned ACT and SPT.

These explicitly assigned cosmologies validate the adapter and nuisance
profiling. They are neither an R135 physical history nor a cosmological fit.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
from pathlib import Path
import sys
import time

SOFTWARE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOFTWARE))
from r135.backends import run_class
from r135.common import canonical_hash,read_json,sha256,write_json
from r135.external_cmb import ACT,SPT,evaluate_batch


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--class-source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.out.exists():p.error('choose a new output directory')
    args.out.mkdir(parents=True)
    # Capture before the expensive native calls. Reading inspect source only at
    # the end can use stale line numbers if another developer edited this shared
    # module meanwhile, even when the executed function itself did not change.
    source_at_launch=inspect.getsource(run_class)
    if not source_at_launch.startswith('def run_class('):
        raise RuntimeError('CLASS source moved between import and provenance capture; restart the control')
    (args.out/'executed_run_class.py').write_text(source_at_launch)
    function_sha=hashlib.sha256(source_at_launch.encode()).hexdigest()
    module_sha=sha256(SOFTWARE/'r135/backends.py')
    start=time.monotonic()
    initial={"perturbation_model":{"kind":"standard_free_streaming_after_matching",
          "source":"assigned diagnostic cosmology, not an independently calibrated X preparation",
          "domain_proof_source":"software zero-X control; no transfer or surviving relic",
          "all_transfer_finished_before_relevant_modes_enter":True,"adiabatic_initial_perturbations":True,
          "massless_collisionless_extra_radiation":True,"no_surviving_interacting_relic":True},
        "parameters":{"H0":67.4,"omega_b":.02242,"omega_cdm":.12,"T_cmb":2.7255,
                      "tau_reio":.054,"n_s":.965,"A_s":2.1e-9,"N_ur":3.044},
        "l_max_scalars":9000}
    tasks={};native=[]
    for label,multiplier in [('baseline',1.),('As_plus_2_percent',1.02)]:
        cfg=read_json_from_copy(initial)
        cfg['parameters']['A_s']*=multiplier
        write_json(args.out/(label+'_input.json'),cfg)
        out=args.out/'class'/label
        spectrum,receipt=run_class(cfg,args.class_source,out,YHe=.245)
        if spectrum['ell'][-1]!=9000 or spectrum.get('lensed') is not True:
            raise RuntimeError('CLASS did not supply the declared lensed coverage')
        tasks[label]={'path':str((out/'spectra.json').resolve()),'sha256':sha256(out/'spectra.json'),
                      'cosmology':cfg['parameters'],
                      'producer_receipt':{'path':str((out/'receipt.json').resolve()),'sha256':sha256(out/'receipt.json')}}
        native.append({'label':label,'receipt_sha256':sha256(out/'receipt.json'),
                       'spectra_sha256':sha256(out/'spectra.json'),'lmax':9000})
    request={'mode':'validation','cache':str(args.cache.resolve()),'offline':True,
             'variants':[ACT,SPT],'spectra':tasks,'spt_tau_prior':'include',
             'profile_nuisance':False,'adapter_sha256':sha256(SOFTWARE/'r135/external_cmb.py')}
    write_json(args.out/'request_fixed.json',request)
    fixed=evaluate_batch(request)
    write_json(args.out/'fixed.json',fixed)
    for variant in (ACT,SPT):
        difference=fixed['evaluations']['As_plus_2_percent'][variant]['logL']-fixed['evaluations']['baseline'][variant]['logL']
        if abs(difference)<1e-3:raise RuntimeError('controlled real CLASS change was not consumed')
    request.update(profile_nuisance=True,profile_policy={'spt_ecal_bounds':[.8,1.2],
        'starts':{ACT:[{'A_act':1.,'P_act':1.},{'A_act':1.02,'P_act':.99}],
                  SPT:[{'Tcal':1.,'Ecal':1.},{'Tcal':1.003,'Ecal':1.01}]},
        'maxiter':300,'ftol':1e-9,'xtol':1e-7})
    write_json(args.out/'request_profiled.json',request)
    profiled=evaluate_batch(request)
    write_json(args.out/'profiled.json',profiled)
    for tag in tasks:
        for variant in (ACT,SPT):
            if profiled['evaluations'][tag][variant]['log_posterior']+1e-7<fixed['evaluations'][tag][variant]['log_posterior']:
                raise RuntimeError('nuisance profiling worsened its registered initial value')
    summary={'scope':'REAL_CLASS_TO_ACT_SPT_AND_NUISANCE_PROFILE_CONTROL','physical_R135_run':False,
             'status':'PASS','actual_CLASS_solves':2,'source_function_sha256':{
                'r135.backends.run_class':function_sha},
             'backends_module_sha256_at_launch':module_sha,
             'adapter_sha256':sha256(SOFTWARE/'r135/external_cmb.py'),
             'runtime_lock_sha256':sha256(SOFTWARE/'external_cmb_sources.lock.json'),
             'runner_sha256':sha256(Path(__file__)),'native':native,
             'fixed':{k:{v:{n:a[n] for n in ('logL','log_prior','log_posterior')} for v,a in row.items()} for k,row in fixed['evaluations'].items()},
             'profiled':{k:{v:{n:a[n] for n in ('logL','log_prior','log_posterior','nuisance')} for v,a in row.items()} for k,row in profiled['evaluations'].items()},
             'fixed_result_sha256':sha256(args.out/'fixed.json'),'profiled_result_sha256':sha256(args.out/'profiled.json'),
             'elapsed_seconds':time.monotonic()-start,
             'limitations':['assigned zero-X cosmologies; no R135 physical preparation',
                            'fixed-cosmology nuisance fits, not a common cosmological baseline/X fit',
                            'no CLASS precision refinement or calibrated exclusion follows from this control',
                            'ACT, SPT and Planck remain separate alternatives']}
    write_json(args.out/'VALIDATION.json',summary)
    print({k:summary[k] for k in ('status','actual_CLASS_solves','elapsed_seconds','fixed','profiled')})


def read_json_from_copy(doc):
    from copy import deepcopy
    return deepcopy(doc)


if __name__=='__main__':main()
