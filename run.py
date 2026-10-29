import time
ENTRY=time.monotonic()
import json
from pathlib import Path
from e002_exp.task import execute
if __name__=='__main__':
    source=Path(__file__).resolve().parent
    raise SystemExit(execute(json.loads((source/'config.json').read_text()),source,ENTRY))
