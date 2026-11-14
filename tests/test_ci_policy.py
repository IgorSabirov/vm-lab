import ast,base64,importlib.util,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load_module(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path)
 module=importlib.util.module_from_spec(spec)
 spec.loader.exec_module(module)
 return module

mod=load_module('ci_plan','tools/ci_plan.py')
workflow_policy=load_module('workflow_policy','tools/workflow_policy.py')

class Selection(unittest.TestCase):
 def test_docs_cannot_skip_integrity(self):
  self.assertEqual(mod.select(['README.md']),['integrity'])
 def test_workflow_changes_require_all_suites(self):
  self.assertEqual(mod.select(['.github/workflows/development.yml']),list(mod.SUITES))
 def test_package_separation(self):
  self.assertEqual(mod.select(['experiments/X27_PACKAGES_20261110/v051/src/x.py']),['integrity','x27_051'])
  self.assertEqual(mod.select(['infra/github_bridge.py']),['integrity','infra'])
 def test_installer_embeds_exact_reviewed_sources(self):
  tree=ast.parse((ROOT/'infra/install_vm_lab.py').read_text())
  for variable,path in [('BRIDGE_SOURCE','infra/github_bridge.py'),('CONTRACT_SOURCE','infra/run_contract.py')]:
   node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==variable for t in n.targets))
   value=ast.literal_eval(node.value.args[0])
   self.assertEqual(base64.b64decode(value),(ROOT/path).read_bytes())

class RuntimePolicy(unittest.TestCase):
 def _contract(self, filename, rule, **changes):
  workflow={'concurrency':{'group':'bounded-compute','cancel-in-progress':False}}
  triggers={'push':{'branches':[rule['branch']],'paths':[rule['path']]}}
  job={'timeout-minutes':rule['minutes'],'if':workflow_policy.REPOSITORY_GUARD}
  job.update(changes)
  return workflow,triggers,job

 def test_all_four_explicit_execution_jobs_are_allowed(self):
  for filename,rule in workflow_policy.LONG_EXECUTION_ALLOWLIST.items():
   with self.subTest(filename=filename):
    workflow,triggers,job=self._contract(filename,rule)
    workflow_policy.validate_runtime_contract(filename,workflow,triggers,rule['job'],job)

 def test_unlisted_long_job_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'Unapproved job runtime'):
   workflow_policy.validate_runtime_contract(
    'development.yml',{}, {},'tests',{'timeout-minutes':11}
   )

 def test_long_job_cannot_expand_its_trigger(self):
  filename,rule=next(iter(workflow_policy.LONG_EXECUTION_ALLOWLIST.items()))
  workflow,triggers,job=self._contract(filename,rule)
  triggers['pull_request']={}
  with self.assertRaisesRegex(ValueError,'trigger must be exact'):
   workflow_policy.validate_runtime_contract(filename,workflow,triggers,rule['job'],job)

 def test_long_job_requires_repo_guard_and_non_cancelling_concurrency(self):
  filename,rule=next(iter(workflow_policy.LONG_EXECUTION_ALLOWLIST.items()))
  workflow,triggers,job=self._contract(filename,rule,**{'if':"true"})
  with self.assertRaisesRegex(ValueError,'repository-scoped'):
   workflow_policy.validate_runtime_contract(filename,workflow,triggers,rule['job'],job)
  workflow,triggers,job=self._contract(filename,rule)
  workflow['concurrency']['cancel-in-progress']=True
  with self.assertRaisesRegex(ValueError,'must not be cancelled'):
   workflow_policy.validate_runtime_contract(filename,workflow,triggers,rule['job'],job)

if __name__=='__main__':
 unittest.main()
