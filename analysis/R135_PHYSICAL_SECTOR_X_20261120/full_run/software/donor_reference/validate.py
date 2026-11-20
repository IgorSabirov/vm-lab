"""Replay P1 from verified donor bytes and preserve dimensional/control evidence.

All initial a, eta and neutrino choices below are diagnostic. The four FMS
mass/entropy preparations retain their external-model origin. No physical X
production run, metastable EOS or total portal width is produced here.
"""
from __future__ import annotations

import argparse
import copy
import sys
import time
from pathlib import Path

import numpy as np

SOFTWARE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOFTWARE))
from r135 import donor_inputs, thermodynamics, nucleation, collisions
from r135.common import sha256, write_json, read_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():parser.error('choose a new output directory')
    args.out.mkdir(parents=True)
    start=time.monotonic()
    config={'cache':str(args.cache.resolve()),'offline':True,'point_id':'XB-FMS-top-left','scale_method':'r0',
            'entropy_covariance_policy':'diagonal_sensitivity',
            'pressure_anchor_uncertainty':{'sigma_over_Tc4':0.,'kind':'diagnostic_fixed_anchor',
                                           'source':'fixed pressure anchor for this code control; physical uncertainty open'}}
    report=donor_inputs.prepare(config);preparation=report['literature_preparation']
    initial={'a0':1.,'eta_b':6e-10,'phase':'cold','T_X_MeV':preparation['T_X_MeV'],
             'T_gamma_MeV':preparation['T_gamma_MeV'],
             'neutrinos':{'kind':'thermal','T_MeV':preparation['T_gamma_MeV']},
             'source':'FMS/entropy-derived cold boundary plus explicitly assigned diagnostic a0, eta, thermal neutrinos'}
    p1_config={'donor_inputs':config,'initial_history':initial}
    write_json(args.out/'P1_CONFIG.json',p1_config)
    result=thermodynamics.run(p1_config,{},args.out/'p1')
    if result['software_status']!='PASS':raise RuntimeError('actual source-driven P1 failed')
    bundle=thermodynamics.EOSBundle(report['eos'])
    checks={}
    for phase,eos in bundle.phases.items():
        temperatures=np.linspace(eos.minimum,eos.maximum,257)
        states=eos.at(temperatures)
        checks[phase]={'T_MeV':[eos.minimum,eos.maximum],
                       'minimum_cv_MeV3':float(min(states['cv_MeV3'])),
                       'cs2_range':[float(min(states['cs2'])),float(max(states['cs2']))]}
    boundaries=[]
    for name in ('top-left','top-right','bottom-left','bottom-right'):
        c=copy.deepcopy(config);c['point_id']='XB-FMS-'+name
        boundaries.append(donor_inputs.prepare(c)['literature_preparation'])
    tc=preparation['T_X_MeV']
    thin_cfg={'finite_a_diagnostic':True,'domain_source':'diagnostic interval 1-T/Tc <= 0.03',
              'maximum_supercooling_fraction':.03,'T_MeV':[tc*.98,tc*.99],
              'prefactor_MeV4':[1.,1.],'prefactor_source':'assigned 1 MeV^4 for software control only'}
    wall={'friction_MeV4':tc**4,'conductivity_MeV3':tc**3,'reference_temperature_MeV':tc,
          'max_abs_speed':.9,'max_relative_temperature_difference':.05,'T_range_MeV':[.97*tc,tc],
          'friction_source':'assigned diagnostic coefficient, not measured X transport',
          'conductivity_source':'assigned diagnostic coefficient, not measured X transport',
          'domain_source':'diagnostic thin-wall software control'}
    p5_config={'donor_thin_wall':thin_cfg,'wall':wall}
    write_json(args.out/'P5_CONFIG.json',p5_config)
    donor_artifact={'donor_inputs':args.out/'p1/donor_inputs.json'}
    p5_result=nucleation.run(p5_config,donor_artifact,args.out/'p5')
    number_cfg={'source':'diagnostic FMS sensitivity preparation','m0_MeV':1000.,'B':1.,'N':3,
                'kinetic_equilibrium':{'source':'assumed diagnostic hierarchy; independent measurement remains open',
                   'rate_kind':'momentum_relaxation','required_ratio':10.,'minimum_rate_over_H':100.,
                   'minimum_rate_over_chemical_rate':100.},
                'low_momentum_applicability':{'T_X_range_MeV':[1.,180.],'maximum_T_X_over_m0':.2,
                                              'source':'explicitly assigned diagnostic low-momentum range'}}
    scalar_cfg={'source':'assigned diagnostic portal inputs; not a calibrated cosmological-X model',
                'm0_MeV':1000.,'M_MeV':1e7,'T_X_MeV':tc,'T_gamma_MeV':preparation['T_gamma_MeV'],
                'chi3':2.,'renormalization_scale_MeV':1000.,
                'energy_support':{'center_of_mass_energy_MeV':[1000.,1e6],
                                  'source':'diagnostic assigned source support','omitted_probability_bound':1e-10,
                                  'maximum_omitted_probability':1e-8},
                'eft_applicability':{'maximum_energy_over_M':.1,'source':'diagnostic declared EFT margin'},
                'running_alpha_s':{'mu_MeV':[500.,1000.,2000.],'alpha_s':[.3,.2,.1],'nf_intervals':[3,3],
                                   'thresholds_MeV':[],'renormalization_scheme':'MSbar',
                                   'source':'assigned diagnostic running table; not a QCD fit'},
                'partonic_applicability':{'minimum_scalar_mass_MeV':2000.,'maximum_alpha_s':.3,
                                          'source':'diagnostic declared bound; no hadronic matching claim'}}
    model={'source':'explicit isolated diagnostic transfer','thermal_channels':[],
           'thermalization':{'status':'EXPLICIT_DIAGNOSTIC_THERMAL_LIMIT','source':'diagnostic reservoir'}}
    p6_config={'model':model,'donor_scalar_portal':scalar_cfg,'donor_3to2':number_cfg}
    write_json(args.out/'P6_CONFIG.json',p6_config)
    p6_result=collisions.run(p6_config,donor_artifact,args.out/'p6')
    p6_number=collisions.run({'model':model,'donor_3to2':number_cfg},donor_artifact,args.out/'p6_number')
    partial=read_json(args.out/'p6/scalar_portal_partial_width.json')
    number=read_json(args.out/'p6/number_changing_model.json')
    if (p5_result['evidence_status']!='DIAGNOSTIC' or p6_result['evidence_status']!='OPEN_INPUT' or
            partial['usable_as_total_width'] or partial['partonic_applicable'] or
            len((args.out/'p6/decay_table.csv').read_text().splitlines())!=1):
        raise RuntimeError('partial or diagnostic donor result incorrectly acquired a physical interpretation')
    summary={'schema':'R135-donor-native-control-v1','status':'PASS','physical_R135_run':False,
             'production_precision_validated':False,'P1_result':result,'P5_result':p5_result,
             'P6_partial_result':p6_result,'P6_number_result':p6_number,
             'P6_control_numbers':{'partial_gg_width_MeV':partial['partial_width_MeV'],
                                  'coefficient_3to2_MeV_minus5':number['coefficient_MeV_minus5'],
                                  'partial_width_not_in_decay_table':True},
             'stable_branch_checks':checks,
             'literature_boundaries':boundaries,'scale_routes':report['scale_alternatives'],
             'selected_scale':report['scale'],'same_pressure_anchor_at_transition':
                 bundle.at(tc,'hot')['p_MeV4']==bundle.at(tc,'cold')['p_MeV4'],
             'source_sha256':{str(p.relative_to(SOFTWARE)):sha256(p) for p in
                [Path(__file__),SOFTWARE/'r135/donor_inputs.py',SOFTWARE/'r135/thermodynamics.py',
                 SOFTWARE/'r135/common.py',SOFTWARE/'donors/fetch.py',SOFTWARE/'donors/extract.py',
                 SOFTWARE/'r135/nucleation.py',SOFTWARE/'r135/collisions.py',
                 SOFTWARE/'r135/gravitationalwaves.py',
                 SOFTWARE/'donors/uncertainties.py',SOFTWARE/'donors/sources.json']},
             'elapsed_seconds':time.monotonic()-start,
             'limitations':report['limitations']}
    write_json(args.out/'VALIDATION.json',summary)
    print({'status':summary['status'],'elapsed_seconds':summary['elapsed_seconds'],
           'P1':result['software_status'],'P5':p5_result['evidence_status'],
           'P6_partial':p6_result['evidence_status'],'P6_number':p6_number['evidence_status'],
           'boundary_count':len(boundaries)})


if __name__=='__main__':main()
