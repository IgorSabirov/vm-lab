import os
import unittest
from unittest.mock import patch
from run import bind_source

class SourceBinding(unittest.TestCase):
    def test_launcher_marker_resolves_without_mutating_template(self):
        c = {'source_commit': 'FROM_VERIFIED_VM_LAUNCHER'}
        with patch.dict(os.environ, {'VM_SOURCE_COMMIT': 'a'*40}):
            self.assertEqual(bind_source(c)['source_commit'], 'a'*40)
        self.assertEqual(c['source_commit'], 'FROM_VERIFIED_VM_LAUNCHER')
    def test_explicit_matching_sha_accepted(self):
        with patch.dict(os.environ, {'VM_SOURCE_COMMIT': 'a'*40}):
            self.assertEqual(bind_source({'source_commit':'a'*40})['source_commit'], 'a'*40)
    def test_explicit_mismatch_rejected(self):
        with patch.dict(os.environ, {'VM_SOURCE_COMMIT': 'a'*40}):
            with self.assertRaises(ValueError): bind_source({'source_commit':'b'*40})
    def test_missing_launcher_and_unspecified_config_rejected(self):
        for env, config in [('', 'FROM_VERIFIED_VM_LAUNCHER'), ('a'*40, None)]:
            with patch.dict(os.environ, {'VM_SOURCE_COMMIT':env}):
                with self.assertRaises(ValueError): bind_source({'source_commit':config})
