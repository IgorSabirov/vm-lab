"""Regression for omitted size without weakening pinned content integrity."""
import hashlib
import unittest

from materialize_roots import verify_file


class MaterializeTests(unittest.TestCase):
    def setUp(self):
        self.data = b'license fixture\n'
        self.entry = {'path': 'LICENSE.txt',
                      'sha256': hashlib.sha256(self.data).hexdigest()}

    def test_size_optional_with_valid_hash(self):
        verify_file(self.entry, self.data)

    def test_missing_size_does_not_allow_changed_bytes(self):
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            verify_file(self.entry, b'License fixture\n')

    def test_declared_size_still_enforced(self):
        with self.assertRaisesRegex(ValueError, 'size mismatch'):
            verify_file({**self.entry, 'size': len(self.data) + 1}, self.data)
        verify_file({**self.entry, 'size': len(self.data)}, self.data)

    def test_missing_hash_fails_closed(self):
        with self.assertRaises(KeyError):
            verify_file({'path': 'LICENSE.txt', 'size': len(self.data)}, self.data)


if __name__ == '__main__':
    unittest.main()
