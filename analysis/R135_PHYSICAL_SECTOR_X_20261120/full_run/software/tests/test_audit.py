"""Independent-reconstruction and adversarial coverage tests.

All fixtures are explicitly diagnostic; these tests run no physical ensemble,
nuclear network, cosmological production model, or observational fit.
"""
import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135 import audit, graph, lattice, response, statistics
from r135.common import (G_NEWTON_MEV_MINUS2, HBAR_MEV_S, InputError, OpenInput, canonical_hash,
                         sha256, write_csv, write_json)

KEY = dict(claim_id="XA_carrier", model_id="XA-graph", point_id="fixture",
           thermal_path="isolated_during_transition")


def seal_fixture(root, stage, config=None, key=None, evidence="CONDITIONAL"):
    """Create content-addressed fixture receipts, not simulated execution claims."""
    key = key or KEY
    config = config or {}
    source_files = [{"path": "diagnostic_fixture.py", "bytes": 1, "sha256": "0" * 64}]
    source = dict(files=source_files, sha256=canonical_hash(source_files), clean=False)
    request = dict(schema="r135-stage-request-v1", stage=stage, key=key,
                   config=config, config_sha256=canonical_hash(config), mode="validation",
                   inputs=[], execution_sha="a" * 40, source_sha256=source["sha256"])
    receipt = dict(schema="r135-stage-receipt-v1", stage=stage, key=key, mode="validation",
                   execution_sha=request["execution_sha"], source_sha256=source["sha256"],
                   request_sha256=canonical_hash(request), config_sha256=request["config_sha256"],
                   scientific_acceptance="owner_review", result=dict(software_status="PASS", evidence_status=evidence))
    write_json(root / "SOURCE.json", source)
    write_json(root / "REQUEST.json", request)
    write_json(root / "EXECUTION_RECEIPT.json", receipt)
    reseal_fixture(root)
    return root / "MANIFEST.json"


def reseal_fixture(root):
    request = json.loads((root / "REQUEST.json").read_text())
    files = [dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size, sha256=sha256(p))
             for p in sorted(root.rglob("*")) if p.is_file() and p.name != "MANIFEST.json"]
    write_json(root / "MANIFEST.json", dict(schema="r135-stage-manifest-v1",
               request_sha256=canonical_hash(request), files=files))


def thermodynamic_fixture(root):
    root.mkdir()
    for name in ("scale.json", "eos_bundle.json", "initial_history.json"):
        write_json(root / name, dict(scope="diagnostic hash/coverage fixture"))
    return seal_fixture(root, "P1")


def raw_chain(chain, seed, role, n=32):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        field = np.exp(2j * np.pi * rng.integers(0, 3, (4, 4, 4)) / 3)
        rows.append(dict(chain_id=chain, seed=seed, config_id=f"{chain}:{i}",
                         role=role, sweep=1000 + 8 * i, start="cold" if seed % 2 else "hot",
                         geometry=[2, 4, 4, 4], grid_id="2x4x4x4", beta=5.7,
                         burn_sweeps=1000, plaquette=float(rng.normal(.5, .1)),
                         polyakov_abs=float(abs(field.mean())), link_verification="UNVERIFIED_LINKS",
                         counts_by_cut=[statistics.count_windows(field, 1, cut) for cut in (0., np.pi / 30)]))
    return rows


class AuditTests(unittest.TestCase):
    def test_bundle_tampering_missing_deliverable_and_key_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p1"
            path = thermodynamic_fixture(root)
            audit.verify_bundle(path, KEY, "P1")
            wrong = dict(KEY, point_id="substituted")
            with self.assertRaisesRegex(InputError, "key"):
                audit.verify_bundle(path, wrong, "P1")
            (root / "scale.json").write_text('{"changed":true}')
            with self.assertRaisesRegex(InputError, "Changed raw"):
                audit.verify_bundle(path)
            (root / "scale.json").unlink()
            reseal_fixture(root)
            with self.assertRaisesRegex(InputError, "deliverable"):
                audit.verify_bundle(path)

    def test_matrix_missing_point_duplicate_and_partial_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = thermodynamic_fixture(root / "p1")
            entry = dict(key=KEY, stage="P1", manifest_input="p1")
            cfg = dict(_mode="validation", expected_keys=[KEY], results=[entry],
                       required_stages={"XA_carrier": ["P1", "P2"]})
            result = audit.run(cfg, {"p1": manifest}, root / "audit")
            self.assertEqual(result["metrics"]["partial_rows"], 1)
            with (root / "audit/claim_matrix.csv").open() as file:
                matrix = list(csv.DictReader(file))
            self.assertEqual(matrix[0]["missing_stages"], "P2")
            self.assertEqual(matrix[0]["scientific_acceptance"], "owner_review")
            cfg["expected_keys"].append(dict(KEY, point_id="missing"))
            with self.assertRaisesRegex(InputError, "Missing point"):
                audit.run(cfg, {"p1": manifest}, root / "bad")
            cfg["expected_keys"] = [KEY]
            cfg["results"].append(entry)
            with self.assertRaisesRegex(InputError, "Duplicate result"):
                audit.run(cfg, {"p1": manifest}, root / "bad")

    def test_expected_registry_omission_and_empty_stage_bypass_are_rejected(self):
        software = Path(__file__).resolve().parents[1]
        inputs = dict(model_register=software/'p0_snapshot/model_register.json',
                      decision_rules=software/'p0_snapshot/decision_rules.json')
        registry = json.loads(inputs['model_register'].read_text())
        points = [p for p in registry['points'] if p['role']=='literature_benchmark']
        expected = [dict(claim_id='XB_SU3_cosmology', model_id=p['model_id'],point_id=p['point_id'],
                         thermal_path=p['thermal_path']) for p in points]
        config = dict(_mode='conditional',expected_keys=expected[:-1],results=[],
                      coverage=dict(scope='registered_subset',point_ids=[p['point_id'] for p in points],
                                    claims=['XB_SU3_cosmology']))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(InputError,'differs from frozen P0'):
                audit.run(config, inputs, root/'omitted')
            config['expected_keys']=expected
            config['coverage']=dict(scope='full')
            with self.assertRaisesRegex(OpenInput,'zero independently calibrated'):
                audit.run(config,inputs,root/'empty_physical')
            manifest=thermodynamic_fixture(root/'p1')
            empty=dict(_mode='validation',expected_keys=[KEY],
                       results=[dict(key=KEY,stage='P1',manifest_input='p1')],
                       required_stages={'XA_carrier':[]})
            with self.assertRaisesRegex(InputError,'nonempty'):
                audit.run(empty,dict(p1=manifest),root/'empty_stage')

    def test_independent_cumulant_and_bootstrap_from_primary_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cal = raw_chain("c1", 101, "calibration") + raw_chain("c2", 102, "calibration")
            held = raw_chain("h1", 103, "heldout") + raw_chain("h2", 104, "heldout")
            lock = statistics.freeze_calibration(cal)
            result = statistics.analyze_chains(held, lock, draws=40)
            lattice._standard_outputs(root, cal + held, result, lock)
            manifest = seal_fixture(root, "P3")
            checked = audit.audit_p3(audit.verify_bundle(manifest))
            self.assertEqual(checked["status"], "RECONSTRUCTED")
            for entry in result["estimates"]:
                self.assertAlmostEqual(checked["recomputed"][str(entry["cut_rad"])]["D4"], entry["primary"]["D4"], places=13)
            # A changed summary with a completely new byte manifest still
            # fails independent numeric reconstruction.
            with (root / "ym_connected.csv").open() as file:
                summary = list(csv.DictReader(file))
            summary[0]["D4"] = str(float(summary[0]["D4"]) + .01)
            write_csv(root / "ym_connected.csv", summary)
            reseal_fixture(root)
            with self.assertRaisesRegex(InputError, "mismatch.*D4"):
                audit.audit_p3(audit.verify_bundle(manifest))

    def test_independent_weighted_response_fit_and_uncensored_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            times = np.linspace(0, 20, 81)
            spec = dict(source="analytic diagnostic exponential", operator="known mode", phase="hot",
                        kind="measured", time=times.tolist(), response=np.exp(-times / 2).tolist(),
                        sigma=np.full(len(times), .001).tolist(), fit_window=[1, 12],
                        mode_kind="within_phase", H_s_inv=.3,
                        clock=dict(unit="s", source="manufactured exact clock", origin="derived", seconds_per_time_unit=2))
            response.run(dict(response=spec), {}, root)
            bundle = audit.verify_bundle(seal_fixture(root, "P4", dict(response=spec)))
            result = audit.audit_p4(bundle)
            self.assertEqual(result["status"], "RECONSTRUCTED")
            self.assertAlmostEqual(result["recomputed"]["0"]["tau"], 4., places=10)
            with (root / "relaxation_times.csv").open() as file:
                table = list(csv.DictReader(file))
            table[0]["tau"] = "6"
            write_csv(root / "relaxation_times.csv", table)
            with self.assertRaisesRegex(InputError, "relaxation"):
                audit.audit_p4(bundle)

    def test_mixed_gate_does_not_hide_one_unstable_corner(self):
        base = np.array([[1., 1.01, .99, 1.02, 1.02]] * 3)
        self.assertEqual(audit.mixed_gate(base)["status"], "BELOW_NUMERICAL_FLOOR")
        base[0, 1] *= 1.0001
        self.assertEqual(audit.mixed_gate(base)["status"], "FAIL_CONVERGENCE")
        x = np.array([[1., 1.01, .99, 1.02001, 1.02]] * 3)
        self.assertEqual(audit.mixed_gate(x)["status"], "RESOLVED")

    def test_cmb_refinement_replay_uses_each_actual_spectrum_and_nuisance(self):
        """Manufactured likelihood records test input binding, not Planck."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evaluations = {}
            for level, tag in enumerate(("linx/00@accuracy0", "linx/00")):
                directory = root / "class/linx" / ("00.accuracy-0" if level == 0 else "00")
                directory.mkdir(parents=True)
                spectrum = dict(scope="diagnostic manufactured spectrum", TT=[1.0 + .01 * level])
                record = dict(logL=-100.0 + .001 * level, log_prior=-2.,
                              components={"diagnostic": -100.0 + .001 * level},
                              nuisance={"calibration": 1.0 + .1 * level}, spectra_sha256=canonical_hash(spectrum))
                evaluations[tag] = record
                write_json(directory / "spectra.json", spectrum)
                if level == 1:
                    write_json(directory / "likelihood.json", dict(CMB=record))
            write_json(root / "planck_evaluations.json", dict(evaluations=evaluations))
            rows = [dict(engine="linx", corner="00")]
            gate = dict(status="PASS", logL_by_accuracy=[-100., -99.999],
                        adjacent_delta_logL=[.001], max_delta_logL=.01)
            precision = {"linx/00": gate}
            config = dict(class_refinement=[dict(tol=1e-4), dict(tol=1e-5)], max_cmb_delta_logL=.01)
            batch, saved = audit._cmb_replay_plan(root, rows, precision, config)
            self.assertEqual(set(batch), {"linx/00@accuracy0", "linx/00"})
            self.assertEqual(batch["linx/00@accuracy0"]["nuisance"]["calibration"], 1.0)
            self.assertEqual(batch["linx/00"]["nuisance"]["calibration"], 1.1)
            gate["logL_by_accuracy"][0] = -100.0001
            gate["adjacent_delta_logL"][0] = .0011
            with self.assertRaisesRegex(InputError, "likelihood source"):
                audit._cmb_replay_plan(root, rows, precision, config)
            gate["logL_by_accuracy"][0], gate["adjacent_delta_logL"][0] = -100., .001
            write_json(root / "class/linx/00.accuracy-0/spectra.json", dict(TT=[9.]))
            with self.assertRaisesRegex(InputError, "different raw spectrum"):
                audit._cmb_replay_plan(root, rows, precision, config)

    def test_thirty_archived_abundance_trajectories_reconstruct_and_detect_changed_summary(self):
        """Manufactured archives test the auditor, not native kernel execution."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = dict(time_s=[1., 2., 3.], scale_factor=[1., 1., 1.],
                           H_s_inv=[1., 1., 1.], T_gamma_MeV=[1., .5, .2], n_b_cm3=[1., 1., 1.])
            weak = dict(time_s=[1., 2., 3.], lambda_n_to_p_s_inv=[1., 1., 1.], lambda_p_to_n_s_inv=[2., 2., 2.])
            native_input = dict(canonical=dict(history=history), weak_rates=weak)
            y = np.array([[.12, .58, 1.5e-5, 0, 0, .0749925, 0, 0],
                          [.11, .59, 1.5e-5, 0, 0, .0749925, 0, 0],
                          [.10, .60, 1.5e-5, 0, 0, .0749925, 0, 0]])
            dh, yp = y[-1, 2] / y[-1, 1], 4*y[-1, 5]
            baryon_error = float(np.abs(y @ [1, 1, 2, 3, 3, 4, 7, 7] - 1).max())
            rows, mixed, gates = [], [], {}
            for engine in ('linx', 'primat'):
                for level in range(3):
                    for corner in audit.CORNERS:
                        directory = root/'bbn'/engine/str(level)/corner
                        directory.mkdir(parents=True)
                        np.savez(directory/'trajectory.npz', time_s=history['time_s'], Y=y, species=np.array(audit.SPECIES))
                        fingerprint = dict(input=native_input, engine=engine, policy=dict(rtol=10**(-5-level)))
                        write_json(directory/'input.json', fingerprint)
                        write_json(directory/'observables.json', dict(D_H=dh, Yp=yp, final_Y=y[-1].tolist()))
                        sample = dict(time_s=1., T_gamma_MeV=1., n_b_cm3=1., lambda_n_to_p_s_inv=1., lambda_p_to_n_s_inv=2.)
                        last_sample = dict(sample, time_s=3., T_gamma_MeV=.2)
                        receipt = dict(engine=engine, input_cache_key=canonical_hash(fingerprint), history_reads=2,
                                       actual_kernel={'linx':'LINX.NuclearRates','primat':'PRIMAT._K_LT'}[engine],
                                       history_sha256=audit._bridge_hash(history), weak_rates_sha256=canonical_hash(weak),
                                       first_rhs_input=sample, last_rhs_input=last_sample,
                                       files={p.name:sha256(p) for p in directory.iterdir()})
                        write_json(directory/'receipt.json', receipt)
                        rows.append(dict(engine=engine, level=level, corner=corner, D_H=dh, Yp=yp,
                                         YHe_CMB=yp, max_baryon_error=baryon_error, rtol=10**(-5-level), atol=1e-12))
                for observable in ('D_H','Yp'):
                    gates[f'{engine}/{observable}'] = dict(status='BELOW_NUMERICAL_FLOOR',mixed_residual=[0.,0.,0.])
                    for level in range(3):
                        mixed.append(dict(engine=engine,observable=observable,level=level,mixed_residual=0.,status='BELOW_NUMERICAL_FLOOR'))
            write_csv(root/'abundances.csv',rows)
            write_csv(root/'mixed_response.csv',mixed)
            write_csv(root/'likelihood_grid.csv',[],['engine','corner','logL'])
            write_json(root/'convergence.json',gates)
            write_json(root/'cmb_spectra_manifest.json',dict(state='NOT_EVALUATED',scope='diagnostic fixture'))
            bundle = audit.verify_bundle(seal_fixture(root,'P9'))
            result = audit.audit_p9(bundle,{})
            self.assertEqual(result['native_runs'],30)
            self.assertEqual(result['status'],'PARTIAL')
            self.assertIn('OBSERVATIONAL_LIKELIHOOD_NOT_EVALUATED',result['reasons'])
            rows[0]['D_H'] *= 1.001
            write_csv(root/'abundances.csv',rows)
            with self.assertRaisesRegex(InputError,'D/H'):
                audit.audit_p9(bundle,{})

    def test_rejects_text_only_proof_and_checks_a_real_finite_witness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p2 = root / "p2"
            p2.mkdir()
            identity = dict(real=np.eye(3).tolist(), imag=np.zeros((3, 3)).tolist())
            definition = dict(source="diagnostic deliberately nonconserving Hamiltonian", version="test-1", eps=[1],
                              hamiltonian=dict(source="declared diagnostic law", unit="MeV",
                                               onsite={str(i): (i + 1) ** 2 for i in range(16)}),
                              balance=dict(kind="isolated"), calibration_ids=[], parameter_uncertainty="exact fixture")
            config = dict(law=definition, state_map=dict(source="manufactured identity map", representation="SU3-fundamental",
                                                       operators={str(i): identity for i in range(16)}),
                          preparations=[dict(id="holdout", role="heldout", source="diagnostic preparation", word=[0, 1, 2])], steps=2)
            graph.run(config, {}, p2)
            manifest = seal_fixture(p2, "P2", config)
            witness = dict(schema="R135-necessary-condition-proof-v1", key=KEY,
                           kind="graph_energy_balance_counterexample", law_sha256=canonical_hash(definition),
                           necessary_condition="energy_conservation_for_declared_isolated_graph_law",
                           preparation_id="holdout", step=1, exempt_stages=["P4"])
            proof = root / "proof.json"
            write_json(proof, witness)
            cfg = dict(_mode="validation", expected_keys=[KEY],
                       results=[dict(key=KEY, stage="P2", manifest_input="p2")],
                       required_stages={"XA_carrier": ["P2", "P4"]}, proofs=[dict(proof_input="proof")])
            result = audit.run(cfg, dict(p2=manifest, proof=proof), root / "audit")
            self.assertEqual(result["metrics"]["necessary_conditions_failed"], 1)
            self.assertEqual(result["metrics"]["partial_rows"], 0)
            witness["kind"] = "claimed_by_text"
            write_json(proof, witness)
            with self.assertRaisesRegex(InputError, "No independent checker"):
                audit.run(cfg, dict(p2=manifest, proof=proof), root / "bad")

    def test_energy_flux_and_hubble_landmarks_from_analytic_radiation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            H0 = .05
            total = (H0 * HBAR_MEV_S) ** 2 * 3 / (8 * np.pi * G_NEWTON_MEV_MINUS2)
            rho0 = total * np.array([.5, .2, .15, .1, .05])
            t = np.unique(np.r_[np.linspace(0, 200, 1001), 20, -np.log([.5, .1, .01]) / .03])
            a = np.sqrt(1 + 2 * H0 * t)
            h = H0 / a ** 2
            f = -np.expm1(-.03 * t)
            rho = rho0[None, :] / a[:, None] ** 4
            pressure = rho / 3
            work = rho0[None, :] * (1 - 1 / a[:, None])
            closure = a[:, None] ** 3 * rho - rho0 + work
            scale, latent = total, .1 * total
            allrows, balances, channels = [], {}, {}
            for corner in audit.CORNERS:
                meta = dict(H0_s_inv=H0, t0_s=0, a0=1, latent_heat_MeV4=latent,
                            initial_energy_MeV4=rho0.tolist(), initial_phase_fraction=0,
                            max_relative_sector_balance=float(np.abs(closure).max() / scale),
                            max_relative_total_balance=float(np.abs(closure.sum(axis=1)).max() / scale),
                            events={}, landmarks={})
                for threshold in (.5, .9, .99):
                    meta['events'][str(threshold)] = dict(time_s=float(-np.log(1-threshold)/.03), censored=False)
                for n in (1, 10):
                    time = n / H0
                    meta['landmarks'][str(n)] = dict(time_s=time, phase_fraction=float(np.interp(time, t, f)),
                                                    delivered_energy_over_a0cubed_L={s: 0 for s in audit.SECTORS})
                balances[corner] = meta
                channels[corner] = dict(time_s=t.tolist(), scale_factor=a.tolist(), phase_fraction=f.tolist(),
                                         Q_MeV4_s={s: np.zeros(len(t)).tolist() for s in audit.SECTORS})
                for i in range(len(t)):
                    row = dict(corner=corner, time_s=t[i], scale_factor=a[i], H_s_inv=h[i],
                               phase_fraction=f[i], I=.03*t[i], old_physical_volume=a[i]**3*np.exp(-.03*t[i]))
                    for j, s in enumerate(audit.SECTORS):
                        row.update({f'rho_{s}_MeV4': rho[i,j], f'p_{s}_MeV4':pressure[i,j],
                                    f'Q_{s}_MeV4_s':0, f'E_{s}_comoving_MeV4':0,
                                    f'work_{s}_comoving_MeV4':work[i,j]})
                    allrows.append(row)
            write_csv(root/'phase_history.csv', allrows)
            write_csv(root/'pocket_history.csv', [], ['corner','time_s'])
            write_json(root/'balance.json', dict(corners=balances, uncertainty_ensemble='analytic fixture'))
            write_json(root/'channel_history.json', dict(histories=channels))
            bundle = audit.verify_bundle(seal_fixture(root, 'P7'))
            result = audit.audit_p7(bundle)
            self.assertEqual(result['status'], 'RECONSTRUCTED')
            self.assertLess(result['recomputed']['00']['relative_work_quadrature_error'], 1e-3)
            balances['00']['landmarks']['1']['phase_fraction'] += .02
            write_json(root/'balance.json', dict(corners=balances))
            with self.assertRaisesRegex(InputError, 'phase fraction'):
                audit.audit_p7(bundle)

    def test_uncertainty_quantiles_include_every_raw_draw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ensemble=dict(status='SENSITIVITY_SET',interpretation='sensitivity_set',draw_count=2,
                          quantile_probabilities=[0,.5,1],draws=[],corners={})
            for number,factor in enumerate((.9,1.1)):
                name=f'draw{number}'
                directory=root/'uncertainty'/name;directory.mkdir(parents=True)
                parameters=dict(inputs=dict(factor=factor),config={})
                write_json(directory/'parameters.json',parameters)
                item=dict(id=name,status='COMPLETE',parameters_sha256=canonical_hash(parameters),corners={})
                for corner in audit.CORNERS:
                    records=[dict(time_s=t,phase_fraction=f*factor,old_physical_volume=1-f*factor,
                                  comoving_energy_sources_MeV4=[0.]*5) for t,f in ((0,0),(1,.2),(10,.8))]
                    summary=dict(H0_s_inv=1,t0_s=0,a0=1,latent_heat_MeV4=2,landmarks={})
                    for n,f in (('1',.2),('10',.8)):
                        summary['landmarks'][n]=dict(phase_fraction=f*factor,old_physical_volume=1-f*factor,
                                                     delivered_energy_over_a0cubed_L={s:0. for s in audit.SECTORS})
                    item['corners'][corner]=summary
                    write_json(directory/f'raw_history_{corner}.json',dict(records=records,summary=summary))
                ensemble['draws'].append(item)
            for corner in audit.CORNERS:
                ensemble['corners'][corner]={}
                for n in ('1','10'):
                    rows=[d['corners'][corner]['landmarks'][n] for d in ensemble['draws']]
                    ensemble['corners'][corner][n]={name:np.quantile([r[name] for r in rows],[0,.5,1]).tolist()
                                                   for name in ('phase_fraction','old_physical_volume')}
                    ensemble['corners'][corner][n]['delivered_energy_over_a0cubed_L']={s:[0.,0.,0.] for s in audit.SECTORS}
            self.assertEqual(audit._audit_parameter_intervals(root,ensemble)['status'],'RECONSTRUCTED')
            changed=copy.deepcopy(ensemble)
            changed['corners']['00']['1']['phase_fraction'][1]+=.01
            with self.assertRaisesRegex(InputError,'quantiles'):
                audit._audit_parameter_intervals(root,changed)
            changed=copy.deepcopy(ensemble)
            changed['draws'][0]['status']='FAILED'
            with self.assertRaisesRegex(InputError,'dropped'):
                audit._audit_parameter_intervals(root,changed)


if __name__ == '__main__':
    unittest.main()
