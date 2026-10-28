"""Pinned offline job entry; publication is owned by vm-lab-sync."""
import time
ENTRY_MONOTONIC = time.monotonic()
import json
from pathlib import Path
from sqrt_exp.task import execute

if __name__ == '__main__':
    source = Path(__file__).resolve().parent
    config = json.loads(Path(__file__).with_name('config.json').read_text())
    raise SystemExit(execute(config, source, ENTRY_MONOTONIC))
