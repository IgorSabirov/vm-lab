import ast,base64,importlib.util,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ci_plan',ROOT/'tools/ci_plan.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class Selection(unittest.TestCase):
 def test_docs_cannot_skip_integrity(self):self.assertEqual(mod.select(['README.md']),['integrity'])
 def test_workflow_changes_require_all_suites(self):self.assertEqual(mod.select(['.github/workflows/development.yml']),list(mod.SUITES))
 def test_package_separation(self):
  self.assertEqual(mod.select(['experiments/X27_PACKAGES_20261110/v051/src/x.py']),['integrity','x27_051'])
  self.assertEqual(mod.select(['infra/github_bridge.py']),['integrity','infra'])
 def test_research_evidence_has_an_independent_route(self):
  self.assertEqual(mod.select(['analysis/R141/note.md','reproductions/R141/check.py']),['evidence'])
  self.assertEqual(mod.select(['analysis/E002/result.json']),['evidence','e002'])
  self.assertIn('infra',mod.select(['analysis/R141/note.md','infra/github_bridge.py']))
 def test_copilot_is_diagnostic_only(self):
  import yaml
  dev=yaml.safe_load((ROOT/'.github/workflows/development.yml').read_text())
  advisor=yaml.safe_load((ROOT/'.github/workflows/copilot-advisory-tests.yml').read_text())
  self.assertNotIn('copilot',mod.SUITES)
  self.assertFalse(any('copilot-advisory' in str(job.get('uses','')) for job in dev['jobs'].values()))
  self.assertTrue(any(step.get('run')=='python tools/ci_suite.py copilot' for step in advisor['jobs']['diagnostics']['steps']))
  suite_spec=importlib.util.spec_from_file_location('ci_suite',ROOT/'tools/ci_suite.py')
  suite=importlib.util.module_from_spec(suite_spec);suite_spec.loader.exec_module(suite)
  advisory=set(suite.infra_modules(True));required=set(suite.infra_modules(False))
  self.assertIn('test_research_context.py',advisory)
  self.assertIn('test_run_contract.py',required)
  self.assertFalse(required & advisory)
  self.assertEqual(required | advisory,{p.name for p in (ROOT/'infra').glob('test*.py')})
 def test_installer_embeds_exact_reviewed_sources(self):
  tree=ast.parse((ROOT/'infra/install_vm_lab.py').read_text())
  for variable,path in [('BRIDGE_SOURCE','infra/github_bridge.py'),('CONTRACT_SOURCE','infra/run_contract.py')]:
   node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==variable for t in n.targets))
   value=ast.literal_eval(node.value.args[0]);self.assertEqual(base64.b64decode(value),(ROOT/path).read_bytes())
if __name__=='__main__':unittest.main()
