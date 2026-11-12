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
 def test_installer_embeds_exact_reviewed_sources(self):
  tree=ast.parse((ROOT/'infra/install_vm_lab.py').read_text())
  for variable,path in [('BRIDGE_SOURCE','infra/github_bridge.py'),('CONTRACT_SOURCE','infra/run_contract.py')]:
   node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==variable for t in n.targets))
   value=ast.literal_eval(node.value.args[0]);self.assertEqual(base64.b64decode(value),(ROOT/path).read_bytes())
if __name__=='__main__':unittest.main()
