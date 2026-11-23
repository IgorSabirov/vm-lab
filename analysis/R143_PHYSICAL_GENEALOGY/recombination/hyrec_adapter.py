"""Thin ctypes caller for the upstream HYREC-2 SWIFT solver.

No cosmological default or BBN interpolation is supplied here. The caller
provides a complete HYREC input file, common H(z) in s^-1, and output nodes.
"""
from __future__ import annotations

import ctypes as ct
from pathlib import Path
import time

import numpy as np


HUBBLE_CALLBACK = ct.CFUNCTYPE(ct.c_double, ct.c_double)
DOUBLE_POINTER = ct.POINTER(ct.c_double)


class HyrecRunner:
    def __init__(self, source_directory, library):
        self.source_directory = Path(source_directory).resolve()
        self.library_path = Path(library).resolve()
        self.library = ct.CDLL(str(self.library_path))
        self.library.r143_set_hubble.argtypes = [HUBBLE_CALLBACK]
        self.library.r143_set_hubble.restype = None
        self.library.r143_probe_hubble.argtypes = [ct.c_double]
        self.library.r143_probe_hubble.restype = ct.c_double
        self.library.r143_hyrec_compute.argtypes = [
            ct.c_char_p, ct.c_char_p, ct.c_double, ct.c_double, ct.c_double,
            ct.c_int, DOUBLE_POINTER, DOUBLE_POINTER, DOUBLE_POINTER,
            DOUBLE_POINTER, ct.c_char_p, ct.c_int,
        ]
        self.library.r143_hyrec_compute.restype = ct.c_int

    def run(self, parameter_file, z, hubble_s, *, dlna=0.004,
            nH0_override=0.0, fHe_override=0.0):
        """Return xe=n_e/n_H and matter temperature in kelvin.

        hubble_s(z) must return physical H(z) in s^-1 at an arbitrary scalar z.
        For identical backgrounds, pass a bound CAMB background function.
        The C adapter is process-global and must be used sequentially.
        """
        z = np.ascontiguousarray(z, dtype=np.float64)
        if z.ndim != 1 or len(z) < 1 or np.any(~np.isfinite(z)):
            raise ValueError("Expected a finite one-dimensional redshift grid")
        if np.any(z < 0) or np.any(z > 8000):
            raise ValueError("HYREC output nodes must be in [0, 8000]")
        exceptions = []

        def get_hubble(value):
            try:
                result = float(hubble_s(value))
                if not np.isfinite(result) or result <= 0:
                    raise ValueError(f"Invalid H({value})={result}")
                return result
            except Exception as exception:
                exceptions.append(exception)
                return float("nan")

        callback = HUBBLE_CALLBACK(get_hubble)
        self.library.r143_set_hubble(callback)
        xe, tm = np.empty_like(z), np.empty_like(z)
        meta = np.empty(10, dtype=np.float64)
        error = ct.create_string_buffer(4096)
        started = time.perf_counter()
        status = self.library.r143_hyrec_compute(
            (str(self.source_directory) + "/").encode(),
            str(Path(parameter_file).resolve()).encode(),
            float(dlna), float(nH0_override), float(fHe_override), len(z),
            z.ctypes.data_as(DOUBLE_POINTER), xe.ctypes.data_as(DOUBLE_POINTER),
            tm.ctypes.data_as(DOUBLE_POINTER), meta.ctypes.data_as(DOUBLE_POINTER),
            error, len(error),
        )
        duration = time.perf_counter() - started
        if exceptions:
            raise RuntimeError("Hubble callback failed") from exceptions[0]
        if status:
            raise RuntimeError(f"HYREC status {status}: {error.value.decode()}")

        # Verify the existing C CAMB bridge's units and callback round-trip,
        # without solving another thermal history.
        probes = np.array([0.0, 10.0, 49.0, 100.0, 500.0, 1100.0, 3000.0, 8000.0])
        direct_h = np.array([get_hubble(v) for v in probes])
        callback_h = np.array([self.library.r143_probe_hubble(v) for v in probes])
        keys = [
            "native_nH0_cm3", "native_fHe", "used_nH0_cm3", "used_fHe",
            "dlna", "internal_grid_size", "hubble_callback_calls", "model_code",
            "integration_zmax", "integration_zmin",
        ]
        metadata = dict(zip(keys, map(float, meta)))
        metadata.update(
            elapsed_seconds=duration, model="HYREC-2 SWIFT",
            H_callback_max_relative_roundtrip=float(np.max(np.abs(callback_h/direct_h - 1))),
            H_callback_probes_z=probes.tolist(),
            H_callback_probes_s_inv=direct_h.tolist(),
        )
        return {"z": z, "xe": xe, "Tm_K": tm, "metadata": metadata}


def write_input(path, *, H0, Tcmb0, Omega_b, Omega_cb, Omega_k, Yp, Neff):
    """Write the official input format for the declared massless-nu baseline.

    All arguments are required. Yp is a helium MASS fraction. Energy injection,
    varying constants, neutrino mass and non-Lambda dark energy are absent.
    """
    values = [
        H0/100.0, Tcmb0, Omega_b, Omega_cb, Omega_k,
        -1.0, 0.0,       # w0, wa
        0.0, 0.0, 0.0, 0.0,  # Nmnu and three masses
        Yp, Neff, 1.0, 1.0,  # YHe, Neff, alpha ratio, electron-mass ratio
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, # annihilation inputs
        1, 0.0,          # on_the_spot (integer), decay
        1.0, 0.0,        # PBH mass and zero abundance
    ]
    # The official reader requires the on_the_spot token to be an integer.
    tokens = [format(v, ".17g") for v in values]
    Path(path).write_text("\n".join(tokens) + "\n")
