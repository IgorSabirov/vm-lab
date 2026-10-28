"""Pinned GitHub entry point. The sync service, not this task, publishes report/."""
import json
from pathlib import Path
from cont.task import execute


if __name__ == '__main__':
    source = Path(__file__).resolve().parent
    config = json.loads(Path(__file__).with_name('config.json').read_text())
    raise SystemExit(execute(config, source))
