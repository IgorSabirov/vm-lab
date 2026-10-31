import unittest
from unittest.mock import patch
import numpy as np
from e002e_exp.compat import gmres, trapezoid

class Compatibility(unittest.TestCase):
    def test_legacy_and_current_gmres_keep_tolerances(self):
        seen = []
        def legacy(A, b, *, tol, atol, **kw):
            seen.append((tol, atol)); return np.array([2.]), 0
        def modern(A, b, *, rtol, atol, **kw):
            seen.append((rtol, atol)); return np.array([2.]), 0
        for fn in (legacy, modern):
            with patch('e002e_exp.compat.scipy_gmres', fn):
                gmres(np.eye(1), np.array([2.]), rtol=1e-12, atol=1e-14)
        self.assertEqual(seen, [(1e-12,1e-14)]*2)
    def test_trapezoid_nonuniform_grid_and_axis(self):
        x = np.array([0., .1, .7, 1.]); y=np.stack([x, 2*x],axis=1)
        np.testing.assert_allclose(trapezoid(y,x,axis=0),[.5,1.],atol=1e-15)
