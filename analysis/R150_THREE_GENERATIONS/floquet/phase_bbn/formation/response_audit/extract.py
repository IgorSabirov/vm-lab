"""Reproduce the ten Python cells in the supplied Markdown transcript."""
from hashlib import sha256
from pathlib import Path
import os
import re
import subprocess
import sys


def replay(source, destination):
    expected = "c078827e5790dca3541cecdbde0de033213eb641e40c06014195b39f33bd6bca"
    payload = source.read_bytes()
    if sha256(payload).hexdigest() != expected:
        raise ValueError("Cell boundaries apply only to the archived transcript.")
    destination.mkdir(exist_ok=True, parents=True)
    lines = payload.decode().replace("\u00a0", " ").splitlines()
    starts = [0, 114, 246, 408, 534, 736, 888, 1042, 1214, 1350]
    for number, start in enumerate(starts, 1):
        end = next(k for k in range(start, len(lines))
                   if lines[k].strip() in (r"\# Result", "# Result"))
        code = re.sub(r"\\([*#@_:.~\[\]=])", r"\1", "\n".join(lines[start:end]))
        script = destination / f"cell_{number:02}.py"
        script.write_text(code.strip() + "\n")
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                                env={**os.environ, "OPENBLAS_NUM_THREADS": "1"})
        script.with_suffix(".txt").write_text(result.stdout + result.stderr)
        print(number, result.returncode, (result.stderr.splitlines() or ["OK"])[-1])
    print("source", expected)


if __name__ == "__main__":
    replay(Path(sys.argv[1]), Path(sys.argv[2]))
