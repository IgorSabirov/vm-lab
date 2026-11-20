"""Strict serialization, units and errors shared by the numerical stages.

Natural energies are MeV, densities MeV**4, physical time seconds. Conversion
constants are explicit, not fitted to a cosmological energy budget.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

HBAR_MEV_S = 6.582119569e-22
HBARC_MEV_CM = 1.973269804e-11
G_NEWTON_MEV_MINUS2 = 6.70883e-45


class InputError(ValueError):
    """Malformed, incompatible, out-of-domain or unverified input."""


class OpenInput(InputError):
    """A required physical datum or supported numerical closure is absent."""


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"cannot serialize {type(obj).__name__}")


def encoded(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False, default=_json_default) + "\n").encode("utf-8")


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(encoded(obj)).hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _unique(pairs: list) -> dict:
    out = {}
    for k, v in pairs:
        if k in out:
            raise InputError(f"duplicate JSON key: {k}")
        out[k] = v
    return out


def read_json(path: Path) -> Any:
    def reject_constant(value):
        raise InputError(f"non-finite JSON value: {value}")
    with Path(path).open(encoding="utf-8") as src:
        return json.load(src, object_pairs_hook=_unique, parse_constant=reject_constant)


def write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))


def write_csv(path: Path, rows, fieldnames=None) -> None:
    rows = list(rows)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def finite(value: Any, name: str, *, positive=False, nonnegative=False) -> float:
    if isinstance(value, bool):
        raise InputError(f"{name}: boolean is not a number")
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{name}: expected finite number") from exc
    if not math.isfinite(v) or (positive and v <= 0) or (nonnegative and v < 0):
        raise InputError(f"{name}: invalid value {value!r}")
    return v


def require_source(value: dict, name: str) -> str:
    source = value.get("source")
    if not isinstance(source, str) or not source.strip():
        raise OpenInput(f"{name}: an explicit source is required")
    return source


def require_input(inputs: dict, name: str) -> Path:
    if name not in inputs:
        raise OpenInput(f"missing input artifact: {name}")
    return Path(inputs[name])


def file_record(path: Path, root: Path) -> dict:
    return {"path": Path(path).relative_to(root).as_posix(),
            "bytes": Path(path).stat().st_size, "sha256": sha256(path)}
