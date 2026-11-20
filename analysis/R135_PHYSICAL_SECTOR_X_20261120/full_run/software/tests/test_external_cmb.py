import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from r135.common import InputError,OpenInput,canonical_hash,read_json,sha256,write_json
from r135.external_cmb import (ACT,SPT,ExternalCMBLikelihood,required_lmax,to_dl,
                              evaluate_batch,_read_task,profile_pair,validate_covariance,isolated_batch)


def sky(n=9):
    ell=np.arange(2,n+1)
    return dict(ell=ell.tolist(),unit='microK^2',convention='Cl',lensed=True,
                TT=(np.ones(len(ell))*3).tolist(),EE=(np.ones(len(ell))*2).tolist(),
                TE=(-np.ones(len(ell))).tolist())


class ExternalCMBTests(unittest.TestCase):
    def test_covariance_rounding_is_exposed_but_indefiniteness_rejected(self):
        c=np.array([[10000.,.1],[.1+1e-9,.01]])
        before=c.copy();check=validate_covariance(c)
        self.assertGreater(check['normalized_max_asymmetry'],0)
        np.testing.assert_array_equal(c,before)
        self.assertFalse(check['symmetrized'])
        for bad in ([[1.,2.],[2.,1.]],[[1.,.3],[.2,1.]]):
            with self.assertRaises(InputError):validate_covariance(bad)

    def test_signed_cl_to_dl_once_with_complete_coverage(self):
        s=sky();d=to_dl(s,lmax=9)
        np.testing.assert_array_equal(d['ell'],np.arange(10))
        self.assertEqual(d['TT'][0],0)
        self.assertAlmostEqual(d['TE'][6],-42/(2*np.pi))
        self.assertEqual(len(d['EE']),10)

    def test_missing_lensing_units_or_multipoles_are_rejected(self):
        for key,value in [('lensed',False),('unit','K^2'),('convention','Dl')]:
            s=sky();s[key]=value
            with self.assertRaises((InputError,OpenInput)):to_dl(s,lmax=9)
        with self.assertRaises(InputError):to_dl(sky(8),lmax=9)
        s=sky();s['ell'][3]=s['ell'][2]
        with self.assertRaises(InputError):to_dl(s,lmax=9)

    def test_sky_covariance_positivity_and_auto_spectrum(self):
        s=sky();s['TE'][2]=4
        with self.assertRaises(InputError):to_dl(s,lmax=9)
        s=sky();s['EE'][1]=-1
        with self.assertRaises(InputError):to_dl(s,lmax=9)

    def test_variants_and_automatic_combination_are_not_ambiguous(self):
        self.assertEqual(required_lmax([ACT,SPT]),9000)
        self.assertEqual(required_lmax([SPT]),4095)
        for names in ([],[ACT,ACT],['Planck']):
            with self.assertRaises(InputError):required_lmax(names)
        with self.assertRaises(OpenInput):evaluate_batch({'variants':[ACT], 'combine_with':['Planck']})

    def test_consumed_file_and_tau_are_bound_to_producer(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'spectra.json';receipt=Path(td)/'receipt.json';write_json(p,sky())
            write_json(receipt,{'spectra_sha256':sha256(p),'input':{'parameters':{'tau_reio':.054,'h':.67}}})
            task={'path':str(p),'sha256':sha256(p),'cosmology':{'tau_reio':.054},
                  'producer_receipt':{'path':str(receipt),'sha256':sha256(receipt)}}
            self.assertEqual(_read_task(task)[1]['tau_reio'],.054)
            wrong=copy.deepcopy(task);wrong['cosmology']['tau_reio']=.051
            with self.assertRaises(InputError):_read_task(wrong)
            no_proof=dict(task);no_proof.pop('producer_receipt')
            with self.assertRaises(OpenInput):_read_task(no_proof)
            self.assertEqual(_read_task(no_proof,validation=True)[0],sky())
            write_json(p,sky(10))
            with self.assertRaises(InputError):_read_task(task)

    def test_nuisance_optimization_is_not_cosmological_optimization(self):
        like=object.__new__(ExternalCMBLikelihood);like.variant=ACT
        like.default_nuisance={'A_act':1.,'P_act':1.}
        def evaluate(s,n,*,cosmology):
            value=-((n['A_act']-1.04)/.03)**2-((n['P_act']-.99)/.02)**2
            return dict(logL=value,log_prior=0.,log_posterior=value,support=True,nuisance=n)
        like.evaluate=evaluate
        r=like.profile({},cosmology={'tau_reio':.054})
        self.assertEqual(r['status'],'PROFILED_FIXED_COSMOLOGY')
        self.assertEqual(r['cosmological_optimization'],'NOT_PERFORMED')
        self.assertAlmostEqual(r['best']['nuisance']['A_act'],1.04,places=5)
        self.assertAlmostEqual(r['best']['nuisance']['P_act'],.99,places=5)
        like.variant=SPT;like.default_nuisance={'Tcal':1.,'Ecal':1.}
        with self.assertRaises(OpenInput):like.profile({},cosmology={'tau_reio':.054})

    def test_common_profile_recomputes_both_models_under_identical_policy(self):
        class Like:
            default_nuisance={'cal':1.}
            def evaluate(self,spectra,nuisance,*,cosmology):
                value=-(spectra['position']-.3)**2-(nuisance['cal']-1.02)**2
                return dict(logL=value,log_prior=0.,log_posterior=value,support=True,nuisance=nuisance)
        calls={'baseline':[],'X':[]}
        def provider(label,offset):
            def make(c):
                calls[label].append(dict(c))
                return {'spectra':{'position':c['shape']+offset},'cosmology':dict(c),
                        'cosmology_sha256':canonical_hash(c),'execution_receipt':{'model':label,'input':dict(c)}}
            return make
        policy={'source':'analytic optimization control',
                'parameters':{'shape':{'kind':'cosmology','bounds':[-2,2]},
                              'cal':{'kind':'nuisance','bounds':[.5,1.5]}},
                'starts':[{'shape':-.7,'cal':.8},{'shape':.8,'cal':1.1}],
                'fixed_cosmology':{'tau_reio':.054}}
        result=profile_pair(Like(),provider('baseline',0),provider('X',.2),policy)
        self.assertEqual(result['status'],'PROFILED_REGISTERED_PARAMETER_SUBSPACE')
        self.assertFalse(result['confidence_calibrated'])
        self.assertAlmostEqual(result['models']['baseline']['best']['cosmology']['shape'],.3,places=4)
        self.assertAlmostEqual(result['models']['X']['best']['cosmology']['shape'],.1,places=4)
        for label in calls:
            self.assertGreater(len(calls[label]),4)
            self.assertEqual(len(result['models'][label]['evaluations']),len(calls[label]))
        wrong=provider('baseline',0)
        def stale(c):
            r=wrong(c);r['cosmology_sha256']='0'*64;return r
        with self.assertRaises(InputError):profile_pair(Like(),stale,provider('X',.2),policy)


@unittest.skipUnless(os.environ.get('R135_EXTERNAL_CMB_NATIVE')=='1','needs pinned ACT/SPT environment and donor cache')
class NativeExternalCMBTests(unittest.TestCase):
    def test_fresh_isolated_worker_replays_actual_class_control(self):
        root=Path(__file__).resolve().parents[1]/'external_cmb_reference/native_control'
        request=read_json(root/'request_fixed.json')
        request['cache']=os.environ.get('R135_DONOR_CACHE','/tmp/r135-fresh-donors')
        for label,task in request['spectra'].items():
            task['path']=str(root/'class'/label/'spectra.json')
            task['producer_receipt']['path']=str(root/'class'/label/'receipt.json')
        with tempfile.TemporaryDirectory() as td:
            answer=isolated_batch(request,sys.executable,Path(td)/'worker',
                                  interpreter_sha256=sha256(Path(sys.executable)))
            control=read_json(root/'fixed.json')
            for label,results in control['evaluations'].items():
                for variant,record in results.items():
                    for key in ('logL','log_prior','log_posterior'):
                        self.assertAlmostEqual(answer['evaluations'][label][variant][key],record[key],places=7)
            self.assertEqual(answer['request_sha256'],canonical_hash(request))
            self.assertFalse(answer['confidence_calibrated'])

    def test_spt_official_spectrum_and_single_tau_prior(self):
        cache=Path(os.environ.get('R135_DONOR_CACHE','/tmp/r135-fresh-donors'))
        sources=read_json(Path(__file__).resolve().parents[1]/'donors/sources.json')
        table=np.loadtxt(cache/sources['spt-control-spectrum']['sha256'])
        ell=table[:,0];factor=2*np.pi/(ell*(ell+1))
        spectra={'ell':ell.astype(int).tolist(),'unit':'microK^2','convention':'Cl','lensed':True,
                 **{name:(table[:,i]*factor).tolist() for i,name in enumerate(('TT','TE','EE'),1)}}
        like=ExternalCMBLikelihood(SPT,cache,spt_tau_prior='include')
        try:
            full=like.evaluate(spectra,{'Tcal':1.001,'Ecal':.999},cosmology={'tau_reio':.054})
            self.assertAlmostEqual(full['log_posterior'],-83.20924274362947,places=7)
            like.spt_tau_prior='omit'
            omit=like.evaluate(spectra,{'Tcal':1.001,'Ecal':.999},cosmology={'tau_reio':.054})
            self.assertAlmostEqual(omit['log_posterior']-full['log_posterior'],.125,places=10)
            self.assertEqual(omit['logL'],full['logL'])
            self.assertFalse(omit['priors']['tau']['included'])
        finally:like.close()


if __name__=='__main__':unittest.main()
