"""SPDX-License-Identifier: GPL-3.0-or-later. Batch access to the original C++ kernel."""
import ctypes as ct
from pathlib import Path
import numpy as np


class SignatureKernel:
    def __init__(self, library):
        self.library = ct.CDLL(str(Path(library).resolve()))
        self.call = self.library.vm_signature_batch
        self.call.argtypes = [ct.POINTER(ct.c_double), ct.c_size_t, ct.c_size_t,
                             ct.POINTER(ct.c_int), ct.POINTER(ct.c_size_t),
                             ct.POINTER(ct.c_double), ct.POINTER(ct.c_uint8)]
        self.call.restype = ct.c_int

    def classify(self, matrices, *, strict=True):
        values = np.ascontiguousarray(matrices, dtype=np.float64)
        if values.ndim == 2:
            values = values[None, :, :]
        if values.ndim != 3 or values.shape[1] != values.shape[2]:
            raise ValueError("Expected a square matrix or a batch of square matrices")
        batch, n, _ = values.shape
        if not 1 <= n <= 256 or not 1 <= batch <= 1000000:
            raise ValueError("Require 1..1000000 matrices of dimension 1..256")
        status = np.empty(batch, dtype=np.intc)
        counts = np.empty((batch, 3), dtype=np.uintp)
        cutoff = np.empty(batch, dtype=np.float64)
        flags = np.empty((batch, 3), dtype=np.uint8)
        code = self.call(values.ctypes.data_as(ct.POINTER(ct.c_double)), batch, n,
                         status.ctypes.data_as(ct.POINTER(ct.c_int)),
                         counts.ctypes.data_as(ct.POINTER(ct.c_size_t)),
                         cutoff.ctypes.data_as(ct.POINTER(ct.c_double)),
                         flags.ctypes.data_as(ct.POINTER(ct.c_uint8)))
        if code:
            raise RuntimeError(f"C++ adapter failed: {code}; no results are usable")
        result = dict(status=status, counts=counts, zero_tolerance=cutoff,
                      reliable=flags[:, 0].astype(bool),
                      symmetry_adjusted=flags[:, 1].astype(bool),
                      numerically_ambiguous=flags[:, 2].astype(bool))
        if strict and not result['reliable'].all():
            indices = np.flatnonzero(~result['reliable'])
            raise ValueError(f"Unreliable classifications at rows {indices[:16].tolist()}; "
                             "use strict=False for diagnostics")
        return result
