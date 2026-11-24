import hashlib
from pathlib import Path
import tempfile
import unittest

from fetch import obtain


class DonorCacheTest(unittest.TestCase):
    def test_cold_fetch_offline_check_and_recovery(self):
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / 'published'
            cache = Path(work) / 'cache'
            data = b'source release'
            source.write_bytes(data)
            item = dict(url=source.as_uri(), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            entry = obtain(cache, item)
            self.assertEqual(entry, obtain(cache, item, offline=True))
            entry.write_bytes(b'x' * len(data))
            with self.assertRaisesRegex(ValueError, 'corrupt'):
                obtain(cache, item, offline=True)
            self.assertEqual(obtain(cache, item).read_bytes(), data)
            entry.unlink()
            source.write_bytes(data + b'unexpected')
            with self.assertRaisesRegex(ValueError, 'exceeds pinned size'):
                obtain(cache, item)
            self.assertEqual(list(cache.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
