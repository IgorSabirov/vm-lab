"""Stage-connection controls; fabricated inputs here make no physical X claim."""
from copy import deepcopy
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135 import backends, history, observations, contracts, thermodynamics
from r135.common import InputError, OpenInput, canonical_hash, read_json, sha256, write_json
from r135.gravitationalwaves import source_artifact
from test_history import fixture
from test_gravitationalwaves import source_definition
from test_observations import history as bbn_history, rates, weak, class_model
from test_contracts import request as stage_request
from test_donor_inputs import analytic_spec

SOFTWARE = Path(__file__).resolve().parents[1]
KEY = dict(claim_id="XB_SU3_cosmology", model_id="XB-pureSU3", point_id="diagnostic-integration",
           thermal_path="exchange_during_transition")


def p8_inputs(root, h):
    channel = {"units": {"time": "s", "temperature": "MeV", "density": "MeV^4", "rate": "s^-1"},
               "key": KEY, "histories": {c: deepcopy(h) for c in observations.CORNERS}}
    write_json(root / "channel.json", channel)
    write_json(root / "rates.json", {"rates": rates(), "reverse_alpha_beta_gamma": [[1.], [0.], [0.]]})
    write_json(root / "weak.json", {"histories": {c: weak() for c in observations.CORNERS}})
    return {"channel_history": root / "channel.json", "nuclear_rates": root / "rates.json", "weak_rates": root / "weak.json"}


class PR160IntegrationTests(unittest.TestCase):
    def test_new_donor_bindings_check_real_parent_receipts_and_diagnostic_mode(self):
        args = deepcopy(fixture())
        initial = deepcopy(args[5])
        initial['a0'] = initial.pop('scale_factor')
        initial['eta_b'] = initial.pop('eta_b_gamma')
        initial['phase'] = 'hot'
        initial['neutrinos'] = {'kind': 'thermal', 'T_MeV': initial['T_nu_MeV']}
        scale = {'anchor': {'value': 1., 'sigma': 0., 'unit': 'MeV', 'origin': 'diagnostic', 'source': 'control'},
                 'ratio': {'value': 1., 'sigma': 0., 'unit': '1', 'origin': 'diagnostic', 'source': 'control'}}
        configurations = {'P1': {'eos': args[1], 'scale': scale, 'initial_history': initial},
                          'P5': {'nucleation': args[2], 'wall': args[3]},
                          'P6': {'model': args[4]}}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for stage, config in configurations.items():
                req = stage_request(stage, config)
                write_json(root / (stage + '.json'), req)
                receipt = contracts.execute(stage, root / (stage + '.json'), root / stage)
                self.assertEqual(receipt['result']['software_status'], 'PASS')
            # Content-schema checks occur later in the numerical stage. Here
            # real produced files/receipts exercise only the producer binding.
            cases = [('P5', 'donor_inputs', root / 'P1/eos_bundle.json'),
                     ('P6', 'donor_inputs', root / 'P1/eos_bundle.json'),
                     ('P7', 'number_changing_model', root / 'P6/collision_model.json'),
                     ('P7', 'gw_source', root / 'P5/gw_source.json')]
            for stage, name, path in cases:
                with self.subTest(stage=stage, name=name):
                    req = stage_request(stage)
                    req['inputs'] = [{'name': name, 'path': str(path), 'sha256': sha256(path)}]
                    contracts.validate_request(req, stage, root)
                    wrong_key = deepcopy(req)
                    wrong_key['key']['point_id'] = 'another-preparation-with-the-same-mass'
                    with self.assertRaisesRegex(InputError, 'another stage/model/point/path/claim'):
                        contracts.validate_request(wrong_key, stage, root)
                    promoted = deepcopy(req)
                    promoted['mode'] = 'conditional'
                    # Isolate the parent-mode contract from the unrelated
                    # uncommitted-worktree attestation check in this test.
                    with patch('r135.contracts.source_matches_commit', return_value=True):
                        with self.assertRaisesRegex(InputError, 'diagnostic history cannot be promoted'):
                            contracts.validate_request(promoted, stage, root)
            wrong_stage = stage_request('P5')
            path = root / 'P6/collision_model.json'
            wrong_stage['inputs'] = [{'name': 'donor_inputs', 'path': str(path), 'sha256': sha256(path)}]
            with self.assertRaisesRegex(InputError, 'another stage/model/point/path/claim'):
                contracts.validate_request(wrong_stage, 'P5', root)

    def test_zero_temperature_cannot_silently_disable_bound_3to2(self):
        args = list(deepcopy(fixture()))
        mass = 1000.
        coefficient = (4 * math.pi / 3) ** 6 / ((4 * math.pi) ** 3 * mass ** 5)
        number = {'schema': 'R135-FMS-NDA-3to2-v1', 'N': 3, 'B': 1., 'm0_MeV': mass,
                  'source': 'diagnostic sourced-domain control', 'coefficient_MeV_minus5': coefficient,
                  'T_X_range_MeV': [1., 100.],
                  'low_momentum_applicability': {'source': 'control', 'maximum_T_X_over_m0': .1,
                                                  'T_X_range_MeV': [1., 100.]},
                  'kinetic_equilibrium': {'source': 'control', 'rate_kind': 'momentum_relaxation',
                     'required_ratio': 10., 'minimum_rate_over_H': 100., 'minimum_rate_over_chemical_rate': 100.}}
        args[0]['relic'] = {'id': 'scalar', 'source': 'diagnostic gas', 'mass_MeV': mass,
                            'kinetic_model': 'relativistic_MB', 'excluded_from_phase_eos': True,
                            'cannibal_MeV_minus5': coefficient, 'number_changing_model': number}
        args[5].update(relic_n_MeV3=1e-12, relic_T_MeV=0.)
        model = history.CoupledModel(*args)
        with self.assertRaisesRegex(OpenInput, 'positive kinetic temperature'):
            model.evaluate(0., model.y0, '00')
        state = model.y0.copy()
        state[6] = state[5] * history.relic_energy_per_particle(.5, mass)
        with self.assertRaisesRegex(OpenInput, 'low-momentum 3<->2 domain'):
            model.evaluate(0., state, '00')
        state[5:7] = 0.
        derivative, _ = model.evaluate(0., state, '00')
        self.assertEqual(derivative[5], 0.)

    def test_entropy_delegate_rejects_a_silently_ignored_pressure_offset(self):
        spec = analytic_spec()
        baseline = thermodynamics.PhaseEOS(spec).at(2.)
        self.assertAlmostEqual(baseline['p_MeV4'], 3.)
        for field, value in [('pressure_offset_MeV4', 1.),
                             ('pressure_offset_sigma_MeV4', .1),
                             ('pressure_offset_source', 'would change the source anchor')]:
            with self.subTest(field=field), self.assertRaisesRegex(InputError, 'common pressure anchor'):
                thermodynamics.PhaseEOS({**spec, field: value})

    def test_resolved_free_particles_and_GW_are_additive_not_double_counted(self):
        args = list(deepcopy(fixture()))
        args[0]["kinetic_species"] = [{"name": "free-test", "sector": "free", "source": "diagnostic cells",
            "statistics": "fermion", "degeneracy": 1, "q_edges_MeV": [0., .1, 1.],
            "initial_occupation": [.1, .01], "operator": {"kind": "collisionless"}}]
        args[0]["gw_source"] = source_definition()
        model = history.CoupledModel(*args)
        state = model.y0.copy()
        state[model.gw.slice] = 1e-9
        derivative, row = model.evaluate(.5 * model.H0, state, "00")
        kinetic_rho, kinetic_pressure, _ = model.kinetic.moments(state, model.a0)
        gw_rho, gw_pressure = model.gw.moments(state)
        self.assertEqual(state[4], 0.)
        self.assertEqual(derivative[4], 0.)
        self.assertAlmostEqual(row["rho"][3], kinetic_rho[3] + gw_rho)
        self.assertAlmostEqual(row["pressure"][3], kinetic_pressure[3] + gw_pressure)
        self.assertGreater(row["gw"]["Q_GW_MeV4_s"], 0.)
        self.assertAlmostEqual(row["Q"][0] + row["Q"][3], 0., places=14)
        self.assertGreater(np.linalg.norm(derivative[model.gw.slice]), 0.)

    def test_P5_source_identity_and_checksum_are_checked_before_P7(self):
        args = deepcopy(fixture())
        config = {**args[0], "_key": KEY, **dict(zip(
            ("eos_bundle", "nucleation_definition", "wall_transport", "collision_model", "initial_history"), args[1:]))}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            declared = source_artifact(source_definition(), KEY)
            declared["point_id"] = "another-point"
            write_json(root / "source.json", declared)
            with self.assertRaisesRegex(InputError, "another point_id"):
                history.run(config, {"gw_source": root / "source.json"}, root / "bad-point")
            declared = source_artifact(source_definition(), KEY)
            declared["definition"]["power_MeV4_s_per_logq"][1][0] *= 2
            write_json(root / "source.json", declared)
            with self.assertRaisesRegex(InputError, "checksum"):
                history.run(config, {"gw_source": root / "source.json"}, root / "bad-hash")

    def test_P6_NDA_cannot_change_mass_units_or_MB_applicability(self):
        mass = 1000.
        coefficient = (4 * math.pi / 3) ** 6 / ((4 * math.pi) ** 3 * mass ** 5)
        model = {"schema": "R135-FMS-NDA-3to2-v1", "N": 3, "B": 1., "m0_MeV": mass,
                 "source": "manufactured scalar control", "coefficient_MeV_minus5": coefficient,
                 "T_X_range_MeV": [1., 100.],
                 "low_momentum_applicability": {"source": "control only", "maximum_T_X_over_m0": .1,
                                                 "T_X_range_MeV": [1., 100.]},
                 "kinetic_equilibrium": {"source": "control only", "rate_kind": "momentum_relaxation",
                    "required_ratio": 10., "minimum_rate_over_H": 100., "minimum_rate_over_chemical_rate": 100.}}
        relic = {"mass_MeV": mass, "kinetic_model": "relativistic_MB", "cannibal_MeV_minus5": coefficient}
        history.validate_number_changing_binding(relic, model)
        with self.assertRaisesRegex(InputError, "mass differs"):
            history.validate_number_changing_binding({**relic, "mass_MeV": 1.}, model)
        with self.assertRaisesRegex(InputError, "normalization"):
            history.validate_number_changing_binding({**relic, "cannibal_MeV_minus5": coefficient * 1e15}, model)
        with self.assertRaises(OpenInput):
            history.validate_number_changing_binding({**relic, "kinetic_model": "pressureless"}, model)

    def test_P8_retains_BBN_when_native_GW_scalar_mapping_is_open(self):
        h = bbn_history()
        # Only the CMB-boundary guard is exercised here, not a GW solution.
        h["gw"] = {"rho_GW_MeV4": [1e-10] * 3}
        cfg = {"_mode": "validation", "_key": KEY, "common_initial_abundances": [.2, .8, 0, 0, 0, 0, 0, 0],
               "class": class_model()}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inputs = p8_inputs(root, h)
            output = root / "p8"; output.mkdir()
            result = observations.run(cfg, inputs, output)
            self.assertEqual(result["metrics"]["prepared_histories"], 5)
            self.assertEqual(result["metrics"]["open_CMB_histories"], 5)
            bbn = read_json(output / "bbn_inputs.json")
            self.assertEqual(bbn["source_P7_file_sha256"], sha256(inputs["channel_history"]))
            self.assertTrue(all(v["status"] == "OPEN_INPUT" for v in read_json(output / "class_inputs.json")["histories"].values()))
            self.assertEqual(bbn["histories"]["00"]["canonical"]["history"]["H_s_inv"], h["H_s_inv"])

    def test_P9_GW_requires_identical_BBN_source_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inputs = p8_inputs(root, bbn_history())
            bbn = {"source_P7_file_sha256": "a" * 64}
            with self.assertRaisesRegex(InputError, "identical"):
                backends.prepare_gw_response({"_key": KEY}, inputs, bbn, root)
            bbn["source_P7_file_sha256"] = sha256(inputs["channel_history"])
            answer = backends.prepare_gw_response({"_key": KEY}, inputs, bbn, root)
            self.assertTrue(all(r["status"] == "OPEN_INPUT" for r in answer["histories"].values()))
            self.assertTrue(all("Omega_GW_today_per_logf" not in r for r in answer["histories"].values()))

    def test_P9_open_CMB_keeps_all_30_completed_BBN_calls(self):
        calls = []
        class Pair:
            def solve(self, prepared, engine, tolerance, out):
                calls.append((engine, str(out)))
                return {"D_H": 2.527e-5, "Yp": .245, "YHe_CMB": .244, "max_baryon_error": 0.,
                        **tolerance}, {"cache_reused": False}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_json(root / "bbn.json", {"schema": "R135-bbn-inputs-v1", "histories": {
                c: {"initial_abundances": [.2, .8, 0, 0, 0, 0, 0, 0]} for c in observations.CORNERS}})
            write_json(root / "class.json", {"histories": {
                c: {"status": "OPEN_INPUT", "missing": ["uncomputed perturbations"]} for c in observations.CORNERS}})
            cfg = {"_mode": "validation", "refinement": [{"rtol": r, "atol": r / 100} for r in (1e-6, 1e-7, 1e-8)]}
            with patch("r135.backends.NativePair", Pair):
                result = backends.run(cfg, {"bbn_inputs": root / "bbn.json", "class_inputs": root / "class.json",
                    "data_release_lock": SOFTWARE / "p0_snapshot/data_release_lock.json"}, root / "p9")
            self.assertEqual(len(calls), 30)
            self.assertEqual(result["software_status"], "PASS")
            self.assertEqual(result["evidence_status"], "INCONCLUSIVE")
            self.assertEqual(read_json(root / "p9/cmb_spectra_manifest.json")["state"], "OPEN_INPUT")
            self.assertTrue((root / "p9/abundances.csv").is_file())

    def test_ACT_SPT_task_uses_producer_tau_and_requires_high_ell_lensed_Cl(self):
        cfg = {"external_cmb": {"cache": "/unused-in-contract-test", "variants": ["ACT_DR6_CMBONLY"],
                                "spt_tau_prior": "omit"}}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spectra = {"ell": list(range(2, 9001)), "unit": "microK^2", "convention": "Cl", "lensed": True,
                       "TT": [1.] * 8999, "EE": [.5] * 8999, "TE": [.1] * 8999}
            path = root / "spectra.json"; write_json(path, spectra)
            receipt = {"spectra_sha256": sha256(path), "input": {"parameters": {"tau_reio": .054}}}
            write_json(root / "receipt.json", receipt)
            request = backends.external_cmb_request(cfg, {"linx/00": {"path": str(path), "sha256": sha256(path)}})
            self.assertEqual(request["spectra"]["linx/00"]["cosmology"], {"tau_reio": .054})
            spectra["lensed"] = False; write_json(path, spectra)
            with self.assertRaises((InputError, OpenInput)):
                backends.external_cmb_request(cfg, {"linx/00": {"path": str(path), "sha256": sha256(path)}})


if __name__ == "__main__":
    unittest.main()
