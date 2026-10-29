import time
from pathlib import Path
import json
from e002b_exp.task import execute

if __name__ == "__main__":
    entry = time.monotonic()
    source = Path(__file__).resolve().parent
    config = json.loads(Path(__file__).with_name("config.json").read_text())
    raise SystemExit(execute(config, source, entry))
