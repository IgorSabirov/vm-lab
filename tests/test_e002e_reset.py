"""Independent small-system truth plus failures that must block scientific output."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from scipy import sparse as sp
from scipy.linalg import expm
from e002_exp.model import build_liouvillian,maxabs
from e002e_exp.space import Space
from e002e_reset_exp.core import Reset,analyze,sign_decision,relative_decision,target_check,entropy
from e002e_reset_exp.numerics import Solver
from e002e_reset_exp.task import solve_model,random_rhs,measure_raw,run
from e002e_reset_exp.verify import verify_case,verify_report
from e002e_reset_exp.plan import workload,PROTOCOL,implementation_hash,protocol_hash


def toy(name='QS'):
    lower=np.array([[0.,1.],[0.,0.]]);n=lower.T@lower;I=np.eye(2)
    H=.4*(np.kron(lower.T,lower)+np.kron(lower,lower.T))+.2*np.kron(n,I)
    jumps=[('down_N',sp.csr_matrix(np.sqrt(.7)*np.kron(lower,I))),
           ('up_N',sp.csr_matrix(np.sqrt(.25)*np.kron(lower.T,I))),
           ('down_E',sp.csr_matrix(np.sqrt(.5)*np.kron(I,lower))),
           ('up_E',sp.csr_matrix(np.sqrt(.35)*np.kron(I,lower.T)))]
    H=sp.csr_matrix(H);L=build_liouvillian(H,jumps);space=Space(np.zeros(4,int))
    # space.pack uses the single all-operator block with standard Fortran vec.
    F=sp.csr_matrix(np.kron(n,I));obs=dict(F=F,J_h=F,source=F,h6=.1*F,P_m6_N2=.2*sp.eye(4),inventory=sp.eye(4))
    model=dict(H=H,L=L,jumps=jumps,space=space,observables=obs,dimensions=(2,2),case=dict(model=name,id='toy_'+name))
    A=L.toarray().copy();b=np.zeros(16,complex);A[-1]=space.trace_row.toarray();b[-1]=1
    rho=np.linalg.solve(A,b);raw=measure_raw(model,rho)
    evidence=dict(baseline=dict(raw=raw),corr=dict(result=dict(signed_area=.02,area_uncertainty=1e-7)))
    return model,rho,evidence


class ResetAlgebra(unittest.TestCase):
    def test_coherent_target_against_kraus_and_dense_superoperator(self):
        model,_,_=toy();tau=np.array([[.6,.12j],[-.12j,.4]]);R=Reset(model['space'],tau,(2,2))
        rng=np.random.default_rng(813);x=rng.normal(size=16)+1j*rng.normal(size=16);rho=model['space'].unpack(x)
        vals,vecs=np.linalg.eigh(tau);out=np.zeros((4,4),complex);complete=np.zeros((4,4),complex)
        for a in range(2):
            for b in range(2):
                K=np.kron(np.eye(2),np.sqrt(vals[a])*np.outer(vecs[:,a],vecs[:,b].conj()))
                out+=K@rho@K.conj().T;complete+=K.conj().T@K
        np.testing.assert_allclose(R.apply(x),model['space'].pack(out),atol=1e-13)
        np.testing.assert_allclose(complete,np.eye(4),atol=1e-13)
        np.testing.assert_allclose(R.apply(2*x+1j*x),2*R.apply(x)+1j*R.apply(x),atol=1e-13)
        self.assertEqual(R.rank,4);R.certify_action(x)

    def test_nontrivial_node_charge_rank_and_no_projection(self):
        s=Space(np.repeat([0,1,1,2],2));R=Reset(s,np.array([[.5,.2],[.2,.5]]),(4,2))
        self.assertEqual(R.rank,6)
        x=random_rhs(s,17);R.certify_action(x)
        rho=s.unpack(x);rho[0,7]=.01
        with self.assertRaises(ValueError):s.pack(rho)

    def test_invalid_target(self):
        for a in (np.eye(2),np.array([[1.2,0],[0,-.2]]),np.array([[.5,1],[0,.5]]),np.array([[np.nan]])):
            with self.assertRaises((ValueError,ArithmeticError)):target_check(a)

    def test_target_is_immutable(self):
        m,_,_=toy();tau=np.eye(2)/2;R=Reset(m['space'],tau,(2,2));tau[0,0]=0
        self.assertEqual(R.tau[0,0],.5)
        with self.assertRaises(ValueError):R.tau[0,0]=0

    def test_poisson_finite_rate_exact_series(self):
        # Pure reset generator is exactly an average over Poisson event counts.
        m,_,_=toy();R=Reset(m['space'],np.diag([.7,.3]),(2,2));x=random_rhs(m['space'],9)
        gamma=.4;t=.8;mat=(R.U@R.V).toarray();power=np.eye(16,dtype=complex);poisson=np.zeros((16,16),complex)
        weight=np.exp(-gamma*t)
        for n in range(24):
            poisson+=weight*power;power=mat@power;weight*=gamma*t/(n+1)
        np.testing.assert_allclose(poisson@x,expm(gamma*t*(mat-np.eye(16)))@x,atol=1e-13)


class ResetSolvers(unittest.TestCase):
    def test_woodbury_and_adjoint_match_dense(self):
        m,rho,_=toy();R=Reset(m['space'],np.array([[.6,.1j],[-.1j,.4]]),(2,2));rhs=random_rhs(m['space'],66)
        for method in ('lu','gmres_ilu'):
            s=Solver(m['L'],m['space'],.2,R,method=method)
            x,eq=s.solve(rhs);dense=s.base.toarray()+.2*(s.U@s.V).toarray()
            truth=np.linalg.solve(dense,np.r_[rhs,0.])[:-1]
            np.testing.assert_allclose(x,truth,atol=1e-10)
            if method=='lu':
                b=np.r_[rhs,0.];np.testing.assert_allclose(s.inverse(b,True),np.linalg.solve(dense.conj().T,b),atol=1e-12)
                self.assertGreater(s.condition_estimate()['value'],0)
            self.assertGreaterEqual(s.counts['factor_rhs_columns'],R.rank+1)
            self.assertLess(eq['absolute_inf'],1e-10)

    def test_response_sign_integral_and_finite_difference(self):
        from e002e_corr_exp.core import marginals
        m,rho,_=toy();s=Solver(m['L'],m['space']);R=Reset(m['space'],marginals(m['space'].unpack(rho),(2,2))[1],(2,2))
        q=R.apply(rho)-rho;X,_=s.solve(-q)
        # Exact augmented exponential integral, independent of inverse formula.
        A=np.zeros((17,17),complex);A[:16,:16]=m['L'].toarray();A[:16,16]=q
        integral=expm(A*100)[:16,16]
        np.testing.assert_allclose(X,integral,atol=1e-11)
        eps=1e-5;shifted=Solver(m['L'],m['space'],eps,R);new,_=shifted.solve(trace=1.)
        np.testing.assert_allclose((new-rho)/eps,X,rtol=1e-4,atol=1e-6)

    def test_zero_response_full_reset_control(self):
        m,rho,_=toy();q=rho*m['space'].trace(rho)-rho
        X,eq=Solver(m['L'],m['space']).solve(-q)
        self.assertLess(maxabs(X),1e-12)
        _,eq=Solver(m['L'],m['space']).solve(np.zeros(16))
        self.assertIsNone(eq['relative_true'])

    def test_traceful_rhs_rejected(self):
        m,rho,_=toy()
        with self.assertRaises(ValueError):Solver(m['L'],m['space']).solve(rho)

    def test_gmres_failure_not_pass(self):
        m,_,_=toy()
        with patch('e002e_reset_exp.numerics.gmres',return_value=(np.zeros(17),7)):
            with self.assertRaises(ArithmeticError):Solver(m['L'],m['space'],method='gmres_ilu').solve(trace=1.)


class Decisions(unittest.TestCase):
    def test_sign_boundaries(self):
        for s,u,expected in [(1,0,'SUPPORTED'),(-1,0,'REFUTED'),(1,1,'UNRESOLVED'),(0,0,'UNRESOLVED')]:
            self.assertEqual(sign_decision(s,u)['status'],expected)

    def test_relative_intervals_and_guard(self):
        self.assertEqual(relative_decision(1.01,.001,1,.001,1,.001,.1)['status'],'SUPPORTED')
        self.assertEqual(relative_decision(1.2,.001,1,.001,1,.001,.1)['status'],'REFUTED')
        self.assertEqual(relative_decision(1.1,.02,1,.02,1,.02,.1)['status'],'UNRESOLVED')
        self.assertEqual(relative_decision(0,0,0,0,0,0,.1)['status'],'NOT_ASSESSED_SMALL_SIGNAL')

    def test_small_S_does_not_disable_window_or_sign(self):
        a=dict(S=5e-7,flux={'0.0':.1,'0.001':.1000000005,'0.002':.100000001})
        r=analyze(a,a,.05,1e-6)
        self.assertEqual(r['sign']['status'],'SUPPORTED')
        self.assertEqual(r['linearity_status'],'NOT_ASSESSED_SMALL_SIGNAL')
        self.assertEqual(r['window']['status'],'REFUTED')

    def test_caps_and_nonfinite_block(self):
        a=dict(S=.05,flux={'0.0':.1,'0.001':.10005,'0.002':.1001})
        with self.assertRaises(ArithmeticError):analyze(a,dict(a,S=.051),.05,1e-6)
        b=dict(a,flux=dict(a['flux'],**{'0.001':.10006}))
        with self.assertRaises(ArithmeticError):analyze(a,b,.05,1e-6)
        with self.assertRaises(ValueError):sign_decision(float('nan'),0)


class Workflow(unittest.TestCase):
    def test_final_calibration_budget_verified_and_immutable(self):
        from contextlib import ExitStack
        from e002e_exp.export import write_manifest
        from e002e_reset_exp.task import snapshot
        models={n:toy(n) for n in ('QS','RR_QS')};cs=[m[0]['case'] for m in models.values()]
        cfg=dict(mode='calibration',source_commit='a'*40,protocol_sha256=protocol_hash(),implementation_sha256=implementation_hash(),
            forecast=dict(expected_seconds=1.,lower_seconds=.1,upper_seconds=5.),memory_budget=dict(peak_additional_bytes=2**30,reserve_bytes=2**30))
        gate=dict(evidence={m[0]['case']['id']:m[2] for m in models.values()},counts=workload('calibration'),environment=dict(comparable=False))
        def env():
            value=snapshot();value['address_space_rlimit']=[2**33]*2;return value
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            for module in ('task','verify'):
                stack.enter_context(patch('e002e_reset_exp.'+module+'.cases',return_value=cs))
                stack.enter_context(patch('e002e_reset_exp.'+module+'.make_full',side_effect=lambda c:models[c['model']][0]))
                stack.enter_context(patch('e002e_reset_exp.'+module+'.uniqueness',return_value={'status':'TEST_FIXTURE'}))
            stack.enter_context(patch('e002e_reset_exp.task.preflight',return_value=gate))
            stack.enter_context(patch('e002e_reset_exp.plan.preflight',return_value=gate))
            stack.enter_context(patch('e002e_reset_exp.task.snapshot',side_effect=env))
            run(cfg,Path(d));folder=Path(d)/'report'
            hashes={p.name:p.read_bytes() for p in folder.iterdir()}
            self.assertEqual(verify_report(folder)['status'],'VERIFIED')
            self.assertEqual(hashes,{p.name:p.read_bytes() for p in folder.iterdir()})
            p=folder/'calibration.json';v=json.loads(p.read_text());v['production_forecast']['expected_seconds']+=1;p.write_text(json.dumps(v));write_manifest(folder)
            with self.assertRaisesRegex(ValueError,'budget'):verify_report(folder)
            p.write_bytes(hashes[p.name]);np.savez_compressed(folder/'physical_response.npz',vector=np.zeros(16));write_manifest(folder)
            with self.assertRaisesRegex(ValueError,'artifact set'):verify_report(folder)
            (folder/'physical_response.npz').unlink();p=folder/'QS_case.json';v=json.loads(p.read_text());v['extra']={'nested':{'S':1.}};p.write_text(json.dumps(v));write_manifest(folder)
            with self.assertRaisesRegex(ValueError,'Forbidden'):verify_report(folder)

    def test_complete_worker_and_manifest_tamper(self):
        from contextlib import ExitStack
        from e002e_exp.export import write_manifest
        models={n:toy(n) for n in ('QS','RR_QS')};cs=[m[0]['case'] for m in models.values()]
        cfg=dict(mode='production',source_commit='a'*40,protocol_sha256=protocol_hash(),implementation_sha256=implementation_hash(),
            forecast=dict(expected_seconds=1.,lower_seconds=.1,upper_seconds=5.))
        gate=dict(evidence={m[0]['case']['id']:m[2] for m in models.values()},counts=workload('production'),environment=dict(comparable=True))
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            for module in ('task','verify'):
                stack.enter_context(patch('e002e_reset_exp.'+module+'.cases',return_value=cs))
                stack.enter_context(patch('e002e_reset_exp.'+module+'.make_full',side_effect=lambda c:models[c['model']][0]))
                stack.enter_context(patch('e002e_reset_exp.'+module+'.uniqueness',return_value={'status':'TEST_FIXTURE'}))
            stack.enter_context(patch('e002e_reset_exp.task.preflight',return_value=gate))
            stack.enter_context(patch('e002e_reset_exp.plan.preflight',return_value=gate))
            run(cfg,Path(d));folder=Path(d)/'report'
            self.assertEqual(verify_report(folder)['status'],'VERIFIED')
            self.assertTrue((folder/'README.md').exists());self.assertTrue((folder/'data_manifest.json').exists())
            p=folder/'QS_uniqueness_scope_v1.json';p.write_text('{}');write_manifest(folder)
            with self.assertRaisesRegex(ValueError,'Uniqueness'):verify_report(folder)

    def test_calibration_seed_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);m,_,e=toy();r=solve_model(m,e,'calibration',folder,dict.fromkeys(workload('calibration'),0))
            np.savez_compressed(folder/r['rows'][0]['random_rhs_file'],vector=random_rhs(m['space'],100))
            with self.assertRaisesRegex(ValueError,'seed'):verify_case(folder,r,m,'calibration')

    def test_production_complete_small_cycle_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            counts=dict.fromkeys(workload('production'),0)
            for name in ('QS','RR_QS'):
                m,_,e=toy(name);rec=solve_model(m,e,'production',Path(d),counts)
                verify_case(Path(d),rec,m,'production')
                original=rec['result']['sign']['value'];rec['result']['sign']['value']+=.1
                with self.assertRaises(ValueError):verify_case(Path(d),rec,m,'production')
                rec['result']['sign']['value']=original
            self.assertEqual(counts,workload('production'))

    def test_calibration_no_response_or_finite_NESS(self):
        with tempfile.TemporaryDirectory() as d:
            counts=dict.fromkeys(workload('calibration'),0)
            for name in ('QS','RR_QS'):
                m,_,e=toy(name);rec=solve_model(m,e,'calibration',Path(d),counts)
                verify_case(Path(d),rec,m,'calibration')
                self.assertNotIn('S',rec['branches']['lu'])
                self.assertEqual(list(rec['branches']['lu']['flux']),['0.0'])
            self.assertEqual(counts,workload('calibration'))

    def test_published_baseline_mismatch_blocks(self):
        m,_,e=toy();e['baseline']['raw']['F']+=.01
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ArithmeticError):solve_model(m,e,'production',Path(d),dict.fromkeys(workload('production'),0))

    def test_worker_saves_failure(self):
        with tempfile.TemporaryDirectory() as d,patch('e002e_reset_exp.task.preflight',side_effect=ValueError('bad provenance')):
            with self.assertRaises(ValueError):run({},Path(d))
            self.assertEqual(json.loads((Path(d)/'report/status.json').read_text())['status'],'FAILED')
            self.assertTrue((Path(d)/'report/failure.json').exists())


if __name__=='__main__':unittest.main()
