"""Verified donor bytes -> dimensionful, phase-aware P1/P5/P6 inputs.

The source release supplies marginal errors and stable phase measurements.
It does not supply an independent cosmological-X mass, a joint EOS covariance,
metastable continuations, a nucleation prefactor, or a complete portal width.
The adapter makes these distinctions executable rather than filling the gaps.
"""
from __future__ import annotations

import copy
import importlib
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

from .common import (InputError, OpenInput, finite, sha256, HBAR_MEV_S,
                     read_json, require_input)

HERE = Path(__file__).resolve().parents[1]
DONORS = HERE/'donors'


def _readers():
    # Load the checkout's package under its own name; never shadow an unrelated
    # global module named fetch, extract, audit, or uncertainties.
    name = '_r135_primary_donors'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, DONORS/'__init__.py',
                                                      submodule_search_locations=[str(DONORS)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return tuple(importlib.import_module(name+'.'+part) for part in ('fetch','extract','uncertainties'))


def load_prepared(inputs):
    """Load the P1 artifact; normal stage execution also verifies its receipt.

    Downstream stages do not rerun preparation with hidden defaults. They use
    one bound P1 artifact and reject a changed source lock or reader version.
    This provenance check supplements, rather than replaces, the pipeline's
    receipt and artifact-hash verification.
    """
    path=require_input(inputs,'donor_inputs')
    prepared=read_json(path)
    if (prepared.get('schema')!='R135-donor-stage-inputs-v1' or
            prepared.get('software_status')!='PASS'):
        raise InputError('donor_inputs must be a successful P1 donor preparation artifact')
    fetch,_,_=_readers()
    provenance=prepared.get('donor_provenance',{})
    if provenance.get('source_lock_sha256')!=sha256(DONORS/'sources.json'):
        raise InputError('P1 donor source lock differs from the current pinned release')
    groups = {'physics','lattice_controls','portal'}
    if prepared.get('relic_spectrum_control',{}).get('spectrum_model') == 'athenodorou_teper':
        groups.add('glueball_spectrum')
    selected={name:row for name,row in fetch.sources().items() if row['group'] in groups}
    records=provenance.get('files',{})
    if set(records)!=set(selected):
        raise InputError('P1 donor source inventory is incomplete or belongs to a different preparation')
    for name,row in selected.items():
        if any(records[name].get(key)!=row[key] for key in ('url','bytes','sha256')):
            raise InputError('P1 donor source identity mismatch: '+name)
    for name in ('fetch.py','extract.py','uncertainties.py'):
        if provenance.get('reader_sha256',{}).get(name)!=sha256(DONORS/name):
            raise InputError('P1 donor reader changed; replay preparation before consuming it: '+name)
    if prepared.get('scale',{}).get('anchor',{}).get('unit')!='MeV':
        raise InputError('P1 donor scalar mass must be expressed in MeV')
    return prepared,{'artifact':path.name,'sha256':sha256(path),
                     'schema':prepared['schema'],
                     'source_lock_sha256':provenance['source_lock_sha256']}


def _required(config, names, label):
    missing=[name for name in names if name not in config or config[name] is None]
    if missing:
        raise OpenInput(label+' requires '+', '.join(missing))


def _vector(value, label, *, positive=False):
    a = np.asarray(value, dtype=float)
    if a.ndim != 1 or not np.isfinite(a).all() or (positive and np.any(a <= 0)):
        raise InputError(label+' must be a finite one-dimensional array'+(' with positive values' if positive else ''))
    return a


def _covariance(value, size, label):
    a = np.asarray(value, dtype=float)
    if a.shape != (size,size) or not np.isfinite(a).all() or not np.allclose(a,a.T,rtol=1e-12,atol=1e-25):
        raise InputError(label+' must be a finite symmetric matrix of the declared size')
    if np.linalg.eigvalsh(a).min() < -1e-12*max(np.max(np.abs(a)),1e-300):
        raise InputError(label+' is not positive semidefinite')
    return a


class EntropyTableEOS:
    """Positive piecewise-linear entropy and its exact pressure integral.

    At an internal knot the reported heat capacity uses the interval to its
    right. At the last knot it uses the left interval. The derivative jump is
    interpolation information, not a claim of a smooth continuum EOS.
    """
    def __init__(self, spec):
        self.spec = copy.deepcopy(spec)
        self.kind = 'entropy_integral_table'
        self.phase = str(spec.get('phase','unnamed'))
        if not spec.get('source') or not spec.get('pressure_anchor',{}).get('source'):
            raise OpenInput('entropy nodes and their common pressure anchor need sources')
        self.axis = _vector(spec['T_MeV'],'entropy temperatures',positive=True)
        self.entropy = _vector(spec['s_MeV3'],'entropy nodes',positive=True)
        n = len(self.axis)
        if n < 2 or self.entropy.shape != self.axis.shape or np.any(np.diff(self.axis)<=0):
            raise InputError('entropy table needs matching strictly increasing temperature nodes')
        self.minimum,self.maximum = float(self.axis[0]),float(self.axis[-1])
        self.slopes = np.diff(self.entropy)/np.diff(self.axis)
        if np.any(self.slopes<=0):
            raise InputError('nonpositive heat capacity in supplied entropy interval')
        mode = spec.get('uncertainty_mode')
        if mode not in {'diagonal_sensitivity','supplied_joint_covariance'}:
            raise OpenInput('entropy table needs an explicit covariance policy')
        covariance = _covariance(spec['entropy_covariance_MeV6'],n,'entropy covariance')
        anchor = spec['pressure_anchor']
        self.anchor_temperature = finite(anchor['T_MeV'],'anchor temperature',positive=True)
        self.anchor_pressure = finite(anchor['p_MeV4'],'anchor pressure')
        self.anchor_sigma = finite(anchor['sigma_MeV4'],'anchor uncertainty',nonnegative=True)
        if not self.minimum<=self.anchor_temperature<=self.maximum:
            raise InputError('pressure anchor lies outside the phase interval')
        cross = _vector(spec.get('anchor_entropy_covariance_MeV7',[0.]*n),'anchor/entropy covariance')
        if len(cross)!=n:
            raise InputError('anchor/entropy covariance has the wrong length')
        self.cov = np.zeros((n+1,n+1))
        self.cov[0,0] = self.anchor_sigma**2
        self.cov[1:,1:] = covariance
        self.cov[0,1:] = self.cov[1:,0] = cross
        # Scale out heterogeneous MeV powers before checking joint PSD.
        units = np.r_[max(self.anchor_sigma,abs(self.anchor_pressure),1e-300),
                      np.maximum(self.entropy,1e-300)]
        _covariance(self.cov/np.outer(units,units),n+1,'joint pressure/entropy covariance')
        self._anchor_weights = self._integral_weights(self.anchor_temperature)
        self.validation = {'entropy_nodes_reproduced':True,
                           'pressure_entropy_identity':'exact for the selected piecewise-linear interpolation',
                           'heat_capacity':'one-sided at interpolation knots',
                           'uncertainty_mode':mode,
                           'production_uncertainty_validated':bool(spec.get('production_uncertainty_validated',False)),
                           'no_extrapolation':True}
        # Density and causal sound-speed checks at both ends of every segment.
        for i,(left,right) in enumerate(zip(self.axis[:-1],self.axis[1:])):
            if max(self.entropy[i]/(left*self.slopes[i]),self.entropy[i+1]/(right*self.slopes[i])) > 1+1e-12:
                raise InputError('acausal sound speed in an entropy interpolation interval')
        if np.any(self.at(self.axis)['rho_MeV4']<=0):
            raise InputError('common pressure anchor gives nonpositive energy density')

    def _interval(self, t):
        return min(max(int(np.searchsorted(self.axis,t,side='right'))-1,0),len(self.axis)-2)

    def _integral_weights(self, t):
        weights = np.zeros(len(self.axis))
        i = self._interval(t)
        for j in range(i):
            h = self.axis[j+1]-self.axis[j]
            weights[j:j+2] += h/2
        h = self.axis[i+1]-self.axis[i]
        d = t-self.axis[i]
        weights[i] += d-d*d/(2*h)
        weights[i+1] += d*d/(2*h)
        return weights

    def at(self, T_MeV):
        values = np.asarray(T_MeV,dtype=float)
        if not np.isfinite(values).all() or np.any(values<self.minimum) or np.any(values>self.maximum):
            from .thermodynamics import EOSDomainError
            raise EOSDomainError(f'{self.phase}: temperature outside [{self.minimum}, {self.maximum}] MeV')
        rows=[]
        for t in values.ravel():
            i=self._interval(t);w=(t-self.axis[i])/(self.axis[i+1]-self.axis[i])
            bs=np.zeros(len(self.axis)+1);bs[i+1]=1-w;bs[i+2]=w
            bp=np.r_[1.,self._integral_weights(t)-self._anchor_weights]
            br=t*bs-bp
            p=self.anchor_pressure+bp[1:]@self.entropy
            s=bs[1:]@self.entropy
            cv=t*self.slopes[i]
            rows.append(dict(p_MeV4=p,s_MeV3=s,rho_MeV4=t*s-p,cv_MeV3=cv,cs2=s/cv,
                             p_sigma_MeV4=math.sqrt(max(float(bp@self.cov@bp),0.)),
                             s_sigma_MeV3=math.sqrt(max(float(bs@self.cov@bs),0.)),
                             rho_sigma_MeV4=math.sqrt(max(float(br@self.cov@br),0.))))
        return {k:float(rows[0][k]) if values.ndim==0 else np.array([r[k] for r in rows]).reshape(values.shape)
                for k in rows[0]}

    def temperature_for_density(self,rho_MeV4):
        rho=finite(rho_MeV4,'density',positive=True)
        if not self.at(self.minimum)['rho_MeV4']<=rho<=self.at(self.maximum)['rho_MeV4']:
            from .thermodynamics import EOSDomainError
            raise EOSDomainError('density lies outside the stable phase EOS')
        return brentq(lambda t:self.at(t)['rho_MeV4']-rho,self.minimum,self.maximum,
                      xtol=max(self.minimum*1e-13,1e-14))


def scale_alternatives(physics, files, controls):
    """Separate dimensionless routes; never average continuum and finite-a results."""
    p=physics;tc=p['r0_Tc'];m=p['r0_m0']
    ratio=tc['value']/m['value']
    relative=[tc['sigma']/tc['value'],m['sigma_stat']/m['value'],m['sigma_anisotropy']/m['value']]
    rows={'r0':{'value':ratio,'sigma':ratio*math.hypot(*relative),'unit':'1','origin':'derived',
                'source':'Francis r0 Tc / Morningstar-Peardon r0 m0',
                'uncertainty_assumption':'zero covariance sensitivity; statistical and anisotropy pieces retained',
                'absolute_sigma_range_unknown_correlations':[ratio*max(0.,2*max(relative)-sum(relative)),ratio*sum(relative)],
                'relative_uncertainty_components':relative,'finite_a_mass':False}}
    a,b=p['Tc_over_sqrt_sigma'],p['m0_over_sqrt_sigma']
    ratio=a['value']/b['value'];u=[a['sigma']/a['value'],b['sigma']/b['value']]
    rows['string_tension']={'value':ratio,'sigma':ratio*math.hypot(*u),'unit':'1','origin':'derived',
                            'source':'Giusti et al. Tc/sqrt(sigma) divided by m0/sqrt(sigma)',
                            'uncertainty_assumption':'zero covariance sensitivity',
                            'absolute_sigma_range_unknown_correlations':[ratio*abs(u[0]-u[1]),ratio*sum(u)],
                            'relative_uncertainty_components':u,'finite_a_mass':False}
    flow=controls.scales(p,files)
    for row in flow['finite_a_Wilson']:
        a=p['Tc_sqrt_t0'];ratio=a['value']/row['m0_sqrt_t0']
        u=[a['sigma']/a['value'],row['mass_only_sigma']/row['m0_sqrt_t0']]
        rows['flow_beta_'+str(row['beta'])]={'value':ratio,'sigma':ratio*math.hypot(*u),'unit':'1','origin':'derived',
            'source':'Giusti continuum Tc sqrt(t0) / Athenodorou et al. Wilson finite-a m0 sqrt(t0)',
            'uncertainty_assumption':'mass-only denominator error; flow interpolation and finite-a/volume systematics open',
            'absolute_sigma_range_unknown_correlations':[ratio*abs(u[0]-u[1]),ratio*sum(u)],
            'finite_a_mass':True,'beta':row['beta'],'L_over_a':row['L_over_a']}
    return rows


def prepare(config):
    """Build P1-ready EOS/scale plus P5/P6 controls from verified cache objects.

    Required: cache, scale_method, either point_id or sourced MeV m0 anchor,
    entropy_covariance_policy, pressure_anchor_uncertainty. No network unless
    offline is explicitly false. Initial thermal history remains an input.
    """
    fetch,extract,controls=_readers()
    if not config.get('cache'):
        raise OpenInput('donor input preparation needs a cache path')
    try:
        spectrum = config.get('spectrum_model', 'fms')
        if spectrum not in ('fms','athenodorou_teper'):
            raise InputError('unknown glueball spectrum model')
        groups = {'physics','lattice_controls','portal'}
        if spectrum == 'athenodorou_teper':
            groups.add('glueball_spectrum')
        files=fetch.acquire(Path(config['cache']),groups,config.get('offline',True))
        p=extract.physics(files)
    except (KeyError,ValueError,OSError) as exc:
        raise InputError('verified donor replay failed: '+str(exc)) from exc
    alternatives=scale_alternatives(p,files,controls)
    method=config.get('scale_method')
    if method not in alternatives:
        raise OpenInput('choose one explicit scale route: '+', '.join(alternatives))
    if alternatives[method]['finite_a_mass'] and config.get('allow_finite_a_scale') is not True:
        raise OpenInput('finite-a flow ratios require an explicit diagnostic sensitivity selection')
    point=None
    if config.get('point_id'):
        matches=[q for q in p['preparations'] if q['point_id']==config['point_id']]
        if len(matches)!=1:
            raise InputError('point_id is not one of the four extracted FMS preparations')
        if 'anchor' in config:
            raise InputError('do not prescribe an extra mass anchor for a fixed FMS preparation')
        point=matches[0]
        anchor=dict(value=point['m0_GeV']*1000,sigma=0.,unit='MeV',origin='external_model',
                    source='Forestell-Morrissey-Sigurdson figure 3, '+point['point_id'],
                    uncertainty_interpretation='fixed published model parameter, not a measurement')
    else:
        anchor=copy.deepcopy(config.get('anchor',{}))
        if (anchor.get('unit')!='MeV' or not anchor.get('source') or
                anchor.get('origin') not in {'measured_independently','external_model','parameter_scan','diagnostic'}):
            raise OpenInput('a sourced m0 anchor in MeV with an explicit origin is required')
        finite(anchor['value'],'m0 anchor',positive=True)
        finite(anchor.get('sigma',0.),'m0 uncertainty',nonnegative=True)
    tc=float(anchor['value'])*alternatives[method]['value']
    covariance_policy=config.get('entropy_covariance_policy')
    if covariance_policy not in {'diagonal_sensitivity','supplied_joint_covariance'}:
        raise OpenInput('published marginal entropy errors do not determine a covariance; select an explicit policy')
    error=config.get('pressure_anchor_uncertainty',{})
    if not error.get('source') or 'sigma_over_Tc4' not in error:
        raise OpenInput('pressure anchor uncertainty is not published by this reader; supply it or declare a diagnostic fixed anchor')
    anchor_sigma=finite(error['sigma_over_Tc4'],'pressure anchor error',nonnegative=True)
    if anchor_sigma==0 and error.get('kind')!='diagnostic_fixed_anchor':
        raise OpenInput('zero pressure anchor uncertainty must be explicitly diagnostic')
    branch_rows={name:sorted([r for r in p['continuum_s_over_T3'] if (r['T_over_Tc']<1)==(name=='cold')]+
                           [dict(T_over_Tc=1.,**p['phase_entropy'][name])],key=lambda r:r['T_over_Tc'])
                 for name in ('cold','hot')}
    order=[dict(phase=name,T_over_Tc=r['T_over_Tc']) for name,rows in branch_rows.items() for r in rows]
    errors=np.array([r['sigma']*r['T_over_Tc']**3 for rows in branch_rows.values() for r in rows])
    if covariance_policy=='diagonal_sensitivity':
        if 'entropy_covariance_over_Tc6' in config:
            raise InputError('a supplied joint covariance must select its matching policy')
        covariance=np.diag(errors**2)
    else:
        if not config.get('entropy_covariance_source'):
            raise OpenInput('joint entropy covariance requires its independent source')
        covariance=_covariance(config['entropy_covariance_over_Tc6'],len(order),'joint entropy covariance')
        if not np.allclose(np.diag(covariance),errors**2,rtol=1e-9,atol=1e-25):
            raise InputError('joint covariance does not reproduce the published marginal entropy errors')
    cross=_vector(config.get('anchor_entropy_covariance_over_Tc7',[0.]*len(order)),
                  'anchor/entropy joint covariance')
    if len(cross)!=len(order):
        raise InputError('anchor/entropy covariance must follow the full declared node order')
    if np.any(cross) and not config.get('anchor_entropy_covariance_source'):
        raise OpenInput('nonzero anchor/entropy covariance needs its independent source')
    joint=np.zeros((len(order)+1,len(order)+1))
    joint[0,0]=anchor_sigma**2;joint[1:,1:]=covariance
    joint[0,1:]=joint[1:,0]=cross
    _covariance(joint,len(order)+1,'dimensionless joint anchor/entropy covariance')
    phases={};cursor=0
    for name,rows in branch_rows.items():
        count=len(rows)
        spec=dict(kind='entropy_integral_table',phase=name,source='Giusti et al. stable branch entropy nodes and one-sided Tc limits',
                  T_MeV=[r['T_over_Tc']*tc for r in rows],
                  s_MeV3=[r['value']*(r['T_over_Tc']*tc)**3 for r in rows],
                  entropy_covariance_MeV6=(covariance[cursor:cursor+count,cursor:cursor+count]*tc**6).tolist(),
                  anchor_entropy_covariance_MeV7=(cross[cursor:cursor+count]*tc**7).tolist(),
                  uncertainty_mode=covariance_policy,production_uncertainty_validated=False,
                  pressure_anchor=dict(T_MeV=tc,p_MeV4=p['entropy_fit']['p_anchor_hot']*tc**4,
                                       sigma_MeV4=anchor_sigma*tc**4,source='Giusti hot pressure fit p1 at Tc; common to both phases',
                                       uncertainty_source=error['source'],shared_id='Giusti-pTc'),
                  applicability='stable equilibrium branch only; no metastable extrapolation',
                  interpolation_error_status='OPEN_INPUT; compare phase interpolation variants')
        EntropyTableEOS(spec)
        phases[name]=spec;cursor+=count
    i_c=len(branch_rows['cold'])-1;i_h=len(branch_rows['cold'])
    difference=np.zeros(len(order));difference[i_h]=1;difference[i_c]=-1
    latent=(p['phase_entropy']['hot']['value']-p['phase_entropy']['cold']['value'])*tc**4
    uncertainty=math.sqrt(max(float(difference@covariance@difference),0.))*tc**4
    matched=controls.matched_interface(files)
    interface={**matched,'T_c_MeV':tc,
               'sigma_MeV3':matched['sigma_over_Tc3']['value']*tc**3,
               'sigma_sigma_MeV3':matched['sigma_over_Tc3']['sigma']*tc**3,
               'latent_heat_MeV4':matched['latent_over_Tc4']['value']*tc**4,
               'latent_heat_sigma_MeV4':matched['latent_over_Tc4']['sigma']*tc**4,
               'applicability':'matched finite-a tadpole action, Ns=32 Nt=4; not the continuum EOS latent heat',
               'physical_nucleation_status':'OPEN_INPUT','prefactor_status':'OPEN_INPUT','wall_transport_status':'OPEN_INPUT'}
    lock=fetch.sources()
    provenance={'source_lock_sha256':sha256(DONORS/'sources.json'),
                'files':{name:dict(url=lock[name]['url'],bytes=path.stat().st_size,sha256=sha256(path)) for name,path in files.items()},
                'reader_sha256':{name:sha256(DONORS/name) for name in ('fetch.py','extract.py','uncertainties.py')}}
    if spectrum == 'athenodorou_teper':
        states = extract.continuum_spin_spectrum(files['at-su3-spectrum'])
        spectrum_id, locator = 'at-su3-spectrum', 'Athenodorou–Teper v2, paper.tex, table_MK_J'
    else:
        states = p['states']
        spectrum_id, locator = 'fms', 'Forestell–Morrissey–Sigurdson v2, draft-final.tex, tab:states'
    limitations=['marginal entropy errors do not provide the measured joint covariance',
                 'pressure-anchor uncertainty and interpolation systematic require independent justification',
                 'stable phase domains do not provide a metastable transition history',
                 'scale routes are separate sensitivity alternatives, not independent repeated measurements',
                 'the published FMS mass is an external model parameter, not a cosmological-X calibration',
                 'a complete initial thermal history, prefactor, wall transport and portal channels remain inputs']
    if point is not None:
        # The donor SM file is tabulated in GeV. Interpolate g_s in log T as
        # in the independently retained xb_reference coordinate calculation.
        table=np.loadtxt(files['sm'])
        if table.shape!=(10000,5) or not np.isfinite(table).all() or np.any(np.diff(table[:,0])<=0) or np.any(table[:,3]<=0):
            raise InputError('unexpected SM entropy table')
        logt=np.log(table[:,0]);gs=table[:,3]
        if np.any(np.diff(np.log(gs)+3*logt)<=0):
            raise InputError('SM entropy is not monotone on its tabulated temperature domain')
        target=p['phase_entropy']['cold']['value']*(tc/1000.)**3/point['R_post']
        def residual(y):
            return math.log(2*math.pi**2/45*np.interp(y,logt,gs))+3*y-math.log(target)
        if residual(logt[0])>0 or residual(logt[-1])<0:
            raise OpenInput('literature preparation lies outside the pinned SM entropy table')
        tg=math.exp(brentq(residual,logt[0],logt[-1],xtol=1e-13))*1000
        point={**point,'T_X_MeV':tc,'T_gamma_MeV':tg,'xi':tc/tg,
               'surface':'confined equilibrium side at Tc; R=s_X/s_SM after confinement',
               'neutrino_preparation_status':'OPEN_INPUT; entropy ratio does not specify neutrino spectra'}
    return {'schema':'R135-donor-stage-inputs-v1','software_status':'PASS','evidence_status':'CONDITIONAL',
            'physical_input_status':'PARTIAL','production_precision_validated':False,
            'scale':{'anchor':anchor,'ratio':alternatives[method],'correlation':0.,
                     'correlation_assumption':'diagnostic zero covariance of chosen mass anchor and dimensionless ratio'},
            'scale_method':method,'scale_alternatives':alternatives,
            'eos':{'phases':phases,'transitions':[dict(hot='hot',cold='cold',T_c_MeV=tc,
                    latent_heat_MeV4=latent,latent_heat_sigma_MeV4=uncertainty)],
                    'cross_phase_entropy_covariance_over_Tc6':covariance.tolist(),'covariance_node_order':order,
                    'joint_anchor_entropy_covariance_dimensionless':joint.tolist(),
                    'shared_pressure_anchor_variance_MeV8':(anchor_sigma*tc**4)**2,
                    'latent_heat_pressure_anchor_cancels':True,'production_uncertainty_validated':False},
            'published_latent_heat_control':{**p['latent_heat'],'derived_endpoint_difference_over_Tc4':latent/tc**4,
                                            'same_data_not_independent_measurements':True},
            'literature_preparation':point,'interface_control':interface,
            'portal_control':extract.scalar_portal(files),
            'relic_spectrum_control':{
                'status':'MASS_RATIOS_ONLY','spectrum_model':spectrum,'source':locator,
                'donor_sha256':provenance['files'][spectrum_id]['sha256'],
                'mass_source':copy.deepcopy(anchor),
                'states':[{**row,'mass_MeV':row['m_over_m0']*float(anchor['value']),
                           'spin_degeneracy':2*row['spin']+1} for row in states],
                'mass_ratio_uncertainty_status':'OPEN_INPUT; joint mass covariance not reported',
                'populations_and_reaction_network_status':'OPEN_INPUT',
                'decay_widths_status':'OPEN_INPUT'},
            'within_phase_secant_controls':controls.eos_intervals(p),
            'donor_provenance':provenance,'limitations':limitations}


def thin_wall_control(prepared, config):
    """Produce a P5 kernel only for the explicitly selected finite-a control.

    This uses Delta p=L(1-T/Tc) from the matched finite-a measurement. It must
    not be relabelled as the metastable continuation of the continuum P1 EOS.
    """
    if config.get('finite_a_diagnostic') is not True or not config.get('domain_source'):
        raise OpenInput('matched finite-a thin-wall construction needs explicit diagnostic scope and domain source')
    _required(config,('T_MeV','maximum_supercooling_fraction','prefactor_MeV4','prefactor_source'),
              'matched finite-a thin-wall construction')
    t=_vector(config['T_MeV'],'thin-wall temperatures',positive=True)
    tc=prepared['interface_control']['T_c_MeV']
    if len(t)<2 or np.any(np.diff(t)<=0) or np.any(t>=tc):
        raise InputError('thin-wall control requires increasing temperatures strictly below Tc')
    delta=1-t/tc
    limit=finite(config['maximum_supercooling_fraction'],'thin-wall domain',positive=True)
    if np.any(delta>limit) or limit>=1:
        raise InputError('temperature outside explicitly supplied thin-wall supercooling domain')
    prefactor=_vector(config['prefactor_MeV4'],'nucleation prefactor',positive=True)
    if prefactor.shape!=t.shape or not config.get('prefactor_source'):
        raise OpenInput('an independently sourced dimensional prefactor is required at each temperature')
    interface=prepared['interface_control']
    return {'kind':'thin_wall','T_MeV':t.tolist(),
            'delta_p_MeV4':(interface['latent_heat_MeV4']*delta).tolist(),
            'sigma_MeV3':[interface['sigma_MeV3']]*len(t),'prefactor_MeV4':prefactor.tolist(),
            'prefactor_source':config['prefactor_source'],
            'source':'matched Beinlich-Karsch-Peikert Ns=32 Nt=4 tadpole action; linear Delta p finite-a control',
            'domain_source':config['domain_source'],'physical_input_status':'DIAGNOSTIC_ONLY',
            'continuum_metastable_EOS':False,
            'donor_source_sha256':prepared['donor_provenance']['files']['improved-su3']['sha256']}


def running_alpha_s(spec, mu_MeV):
    """Read a sourced running-coupling table; do not extrapolate through flavours."""
    if not spec.get('source') or not spec.get('renormalization_scheme'):
        raise OpenInput('running alpha_s needs its source and renormalization scheme')
    axis=_vector(spec['mu_MeV'],'alpha_s scale nodes',positive=True)
    values=_vector(spec['alpha_s'],'alpha_s values',positive=True)
    flavours=np.asarray(spec['nf_intervals'])
    if (len(axis)<2 or values.shape!=axis.shape or np.any(np.diff(axis)<=0) or
            np.any(np.diff(values)>0) or flavours.shape!=(len(axis)-1,) or
            not np.all(np.isin(flavours,[3,4,5,6]))):
        raise InputError('invalid scale-ordered QCD coupling/flavour table')
    thresholds=_vector(spec.get('thresholds_MeV',[]),'flavour thresholds',positive=True)
    if np.any(np.diff(thresholds)<=0):
        raise InputError('flavour thresholds must be increasing')
    interior=thresholds[(thresholds>axis[0])&(thresholds<axis[-1])]
    changes=np.flatnonzero(np.diff(flavours)!=0)+1
    if (len(changes)!=len(interior) or any(not math.isclose(axis[i],v,rel_tol=1e-12)
            for i,v in zip(changes,interior)) or np.any(np.diff(flavours)<0) or np.any(np.diff(flavours)>1)):
        raise InputError('every flavour change must coincide with a declared threshold knot')
    if len(interior) and not spec.get('threshold_matching_source'):
        raise OpenInput('flavour-threshold matching needs its source')
    if len(interior) and spec.get('threshold_prescription')!='continuous_matched_table':
        raise OpenInput('this adapter requires a continuous matched coupling table at flavour thresholds')
    mu=finite(mu_MeV,'renormalization scale',positive=True)
    if not axis[0]<=mu<=axis[-1]:
        raise OpenInput('renormalization scale lies outside the supplied running-alpha_s table')
    i=min(np.searchsorted(axis,mu,side='right')-1,len(axis)-2)
    return {'alpha_s':float(np.interp(math.log(mu),np.log(axis),values)),
            'n_f':int(flavours[i]),'mu_MeV':mu,'scheme':spec['renormalization_scheme'],
            'source':spec['source'],'thresholds_MeV':thresholds.tolist(),
            'interpolation':'linear alpha_s in log(mu); no extrapolation'}


def scalar_partonic_width(prepared, config):
    """One FMS 0++ -> gg partonic partial width with explicit EFT checks.

    No result from this function is a total lifetime, a hadronic branching
    table, or a cosmological Q source, including when the EFT checks pass.
    """
    if not config.get('source'):
        raise OpenInput('portal masses, Wilson coefficient and bath preparation need a source')
    _required(config,('m0_MeV','M_MeV','T_X_MeV','T_gamma_MeV','chi3',
                      'renormalization_scale_MeV','running_alpha_s'),'scalar partial width')
    m=finite(config['m0_MeV'],'scalar mass',positive=True)
    if not math.isclose(m,prepared['scale']['anchor']['value'],rel_tol=1e-12):
        raise InputError('portal scalar mass differs from the selected donor preparation')
    mediator=finite(config['M_MeV'],'mediator scale',positive=True)
    tx=finite(config['T_X_MeV'],'X temperature',nonnegative=True)
    tg=finite(config['T_gamma_MeV'],'visible temperature',nonnegative=True)
    chi=finite(config['chi3'],'FMS gluonic Wilson coefficient')
    support=config.get('energy_support',{})
    if not support.get('source'):
        raise OpenInput('EFT checks require a sourced process-energy support and its tail budget')
    energies=_vector(support['center_of_mass_energy_MeV'],'process-energy support',positive=True)
    if len(energies)!=2 or not energies[0]<=m<=energies[1]:
        raise InputError('process-energy support must cover the scalar decay energy')
    tail=finite(support['omitted_probability_bound'],'omitted energy-tail probability',nonnegative=True)
    allowed_tail=finite(support['maximum_omitted_probability'],'allowed energy-tail probability',nonnegative=True)
    if tail>allowed_tail or allowed_tail>=1:
        raise OpenInput('process energy-tail error exceeds its declared budget')
    eft=config.get('eft_applicability',{})
    if not eft.get('source'):
        raise OpenInput('EFT hierarchy criterion needs an independently justified source')
    maxratio=finite(eft['maximum_energy_over_M'],'EFT hierarchy criterion',positive=True)
    if maxratio>=1:
        raise InputError('EFT hierarchy criterion must be smaller than one')
    ratios={'m0_over_M':m/mediator,'T_X_over_M':tx/mediator,
            'T_gamma_over_M':tg/mediator,'E_max_over_M':energies[-1]/mediator}
    if max(ratios.values())>maxratio:
        raise OpenInput('portal scale is outside the declared EFT hierarchy')
    running=running_alpha_s(config['running_alpha_s'],config['renormalization_scale_MeV'])
    parton=config.get('partonic_applicability',{})
    if not parton.get('source'):
        raise OpenInput('partonic approximation needs a sourced energy/coupling domain')
    minimum=finite(parton['minimum_scalar_mass_MeV'],'partonic lower mass',positive=True)
    alpha_max=finite(parton['maximum_alpha_s'],'partonic coupling bound',positive=True)
    partonic_ok=m>=minimum and running['alpha_s']<=alpha_max
    coefficient=prepared['portal_control']['K_gg']
    factor=running['alpha_s']**2*chi**2*m*(m/mediator)**8
    width=coefficient*factor
    if not math.isfinite(width):
        raise InputError('partial width overflow; verify the dimensional scales')
    return {'schema':'R135-FMS-scalar-partial-width-v1','status':'PARTIAL_WIDTH_ONLY',
            'partial_width_MeV':width,'partial_width_s_inv':width/HBAR_MEV_S,
            'm0_MeV':m,'M_MeV':mediator,'T_X_MeV':tx,'T_gamma_MeV':tg,
            'mass_source':copy.deepcopy(prepared['scale']['anchor']),
            'matrix_element_input_range_MeV':[v*factor for v in prepared['portal_control']['K_gg_one_sigma_input_range']],
            'channel':'0++ -> gg, partonic EFT','source':config['source'],
            'donor_sha256':prepared['donor_provenance']['files']['fms-portals']['sha256'],
            'running_alpha_s':running,'eft_ratios':ratios,'eft_maximum_ratio':maxratio,
            'energy_support':copy.deepcopy(support),'partonic_applicable':bool(partonic_ok),
            'partonic_applicability':copy.deepcopy(parton),'usable_as_total_width':False,
            'hadronic_matching_status':'OPEN_INPUT','C_odd_channels_status':'OPEN_INPUT',
            'cosmological_energy_source_status':'OPEN_INPUT',
            'production_precision_validated':False,
            'limitations':['only the scalar matrix-element marginal variation is propagated here',
                           'all other open channels, inverse reactions, hadronization and energy deposition remain required']}


def nda_3to2(prepared, config):
    """FMS low-momentum SU(3) NDA coefficient in MeV^-5, with explicit closure.

    B multiplies the rate (not its square); it is a sensitivity parameter, not
    a probability distribution. The kinetic relaxation requirements refer to
    momentum relaxation, not merely a total elastic collision count.
    """
    if not config.get('source'):
        raise OpenInput('NDA mass, B and approximation domain need a source')
    _required(config,('m0_MeV','B'),'NDA coefficient')
    m=finite(config['m0_MeV'],'NDA scalar mass',positive=True)
    if not math.isclose(m,prepared['scale']['anchor']['value'],rel_tol=1e-12):
        raise InputError('NDA scalar mass differs from the selected donor preparation')
    B=finite(config['B'],'NDA rate multiplier B',positive=True)
    if config.get('N',3)!=3:
        raise OpenInput('these sourced masses and preparation describe SU(3), not another N')
    closure=config.get('kinetic_equilibrium',{})
    if not closure.get('source') or closure.get('rate_kind')!='momentum_relaxation':
        raise OpenInput('MB closure needs a sourced momentum-relaxation criterion')
    required=finite(closure['required_ratio'],'kinetic equilibration margin',positive=True)
    if required<=1:
        raise InputError('kinetic-equilibrium separation must be stronger than unity')
    ratios=[finite(closure[name],name,positive=True) for name in
            ('minimum_rate_over_H','minimum_rate_over_chemical_rate')]
    if min(ratios)<required:
        raise OpenInput('kinetic relaxation does not dominate expansion and chemical evolution')
    domain=config.get('low_momentum_applicability',{})
    if not domain.get('source'):
        raise OpenInput('the low-momentum NDA rate needs its explicit temperature domain')
    temps=_vector(domain['T_X_range_MeV'],'NDA temperature range',positive=True)
    limit=finite(domain['maximum_T_X_over_m0'],'NDA temperature ratio limit',positive=True)
    if len(temps)!=2 or temps[0]>=temps[1] or temps[-1]/m>limit or limit>=1:
        raise InputError('temperature range lies outside the declared low-momentum approximation')
    coefficient=B*(4*math.pi/3)**6/((4*math.pi)**3*m**5)
    return {'schema':'R135-FMS-NDA-3to2-v1','status':'NDA_SENSITIVITY',
            'coefficient_MeV_minus5':coefficient,'B':B,'N':3,'m0_MeV':m,
            'mass_source':copy.deepcopy(prepared['scale']['anchor']),
            'source':config['source'],'donor_sha256':prepared['donor_provenance']['files']['fms']['sha256'],
            'kinetic_equilibrium':copy.deepcopy(closure),'T_X_range_MeV':temps.tolist(),
            'low_momentum_applicability':copy.deepcopy(domain),'B_probability_measure':None,
            'number_source_convention':'dn/dt + 3Hn = - coefficient_MeV_minus5 / hbar_MeV_s * n^2 * (n - n_eq)',
            'energy_source_convention':'3<->2 conserves total isolated species energy; solve number and energy together',
            'production_precision_validated':False,
            'limitations':['single scalar MB gas in kinetic equilibrium',
                           'NDA is not a calibrated energy-dependent multi-species collision kernel']}
