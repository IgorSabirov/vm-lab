"""Fixed entrypoint: configuration is supplied by a hash-bound section plan."""
import json
import os
from pathlib import Path
from infra.adapters import add_f2, serbian_signature


def main():
    plan = json.loads(Path(os.environ['SECTION_PLAN']).read_text())
    root = Path(os.environ['SOURCE_ROOT']); out = Path(os.environ['SECTION_OUTPUT'])
    raw = {'add_f2': add_f2, 'serbian_signature': serbian_signature}[plan['adapter']].run(root, out, plan['config'])
    (out/'RAW.json').write_text(json.dumps(raw, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
