import unittest
import uuid
from tools.dependency_evidence import generate


def row(name, requires=()):
    return {'metadata': {'name': name, 'version': '1.0', 'requires_dist': list(requires)}}


class DependencyEvidenceTests(unittest.TestCase):
    def test_serial_is_stable_and_recognized_by_attest_action(self):
        items = [row('b', ['a>=1']), row('a')]
        first, _ = generate({'installed': items})
        second, _ = generate({'installed': list(reversed(items))})
        self.assertEqual(first, second)
        self.assertEqual(uuid.UUID(first['serialNumber']).urn, first['serialNumber'])
        # Pinned actions/attest src/sbom.ts recognizes these three fields.
        self.assertTrue(all(first[x] for x in ('bomFormat', 'serialNumber', 'specVersion')))
        changed, _ = generate({'installed': [row('a')]})
        self.assertNotEqual(first['serialNumber'], changed['serialNumber'])

    def test_markers_and_dependency_links(self):
        bom, missing = generate({'installed': [row('a'), row('b', ['a>=1', 'optional; extra == "test"'])]})
        self.assertEqual(missing, [])
        self.assertEqual(bom['dependencies'][1]['dependsOn'], ['pkg:pypi/a@1.0'])

    def test_missing_runtime_is_reported(self):
        _, missing = generate({'installed': [row('b', ['a>=1'])]})
        self.assertEqual(missing, [{'package': 'b', 'requirement': 'a>=1'}])


if __name__ == '__main__':
    unittest.main()
