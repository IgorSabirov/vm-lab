"""CORR environment observations supplement the unchanged E002e runtime."""
from pathlib import Path
from e002e_exp.runtime import environment as kernel_environment


def environment():
    result = kernel_environment()
    try:
        result['process_threads'] = len(list(Path('/proc/self/task').iterdir()))
    except OSError:
        result['process_threads'] = None
    return result
