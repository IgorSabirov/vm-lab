"""Bounded trajectory of the pinned independent F2 reconstruction."""
import importlib.util
import sys
from pathlib import Path

SOURCE = 'analysis/ADD_DICHOTOMY_AUDIT_20261108/source/add_backend_smoke_v1.py'


def run(root, output, config):
    spec = importlib.util.spec_from_file_location('pinned_add_f2', Path(root) / SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = module.sample_trajectory(**config)
    return {'variant': 'ADD_F2', 'operator': 'sqrt_tau(I2(g))',
            'implementation': 'INDEPENDENT_RECONSTRUCTION', 'not_author_code': True,
            'not_NOW_integration': True, 'trajectory': result}
