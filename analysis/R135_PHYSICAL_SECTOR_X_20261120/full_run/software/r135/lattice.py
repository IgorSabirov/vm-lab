"""P3 Wilson SU(3) reference generator, link import and measurement.

Storage convention is (t,x,y,z,mu,a,b), mu=0 temporal, complex128.  All four
directions are periodic.  The action is beta*sum_p(1-ReTr(U_p)/3).

The generator is **random-scan SU(2)-subgroup Metropolis v1**, not the proposed
heatbath/overrelaxation algorithm.  Each elementary transition chooses a link
and one of (01,02,12) uniformly, proposes exp(i*theta*n.sigma) on the left,
with n uniform on S2 and theta uniform on [-width,width], and accepts with
min(1,exp(-Delta S)).  The inverse proposal has the same probability, so
exp(-S(U))*q(U,V)*a(U,V)=exp(-S(V))*q(V,U)*a(V,U).  This proof is independent
of the coupling.  Products of the three subgroups generate SU(3); proposal
width is fixed for a chain (no adaptation using heldout observables).

One sweep is 4*V elementary RANDOM choices with replacement.  Thus a sweep
is a power of one reversible kernel, with an explicitly recorded convention.
This transparent reference algorithm prioritizes auditability, not performance
on the four production lattices.  The output does not assert independent
physical ensembles merely because the sampler can execute.

Action reference: K.G. Wilson, Phys. Rev. D 10, 2445 (1974),
https://doi.org/10.1103/PhysRevD.10.2445.
Acceptance rule: Metropolis et al., J. Chem. Phys. 21, 1087 (1953),
https://doi.org/10.1063/1.1699114.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from . import statistics
from .common import OpenInput, read_json

ALGORITHM = "wilson-su3-random-scan-su2-metropolis-v1"
PAIRS = ((0, 1), (0, 2), (1, 2))
PRODUCTION_GRIDS = ((4, 24, 1), (8, 48, 2), (4, 32, 1), (8, 64, 2))


def _json(path, data):
    Path(path).write_text(json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def _geometry(geometry):
    if len(geometry) != 4 or any(isinstance(n, bool) or int(n) != n or n < 2 for n in geometry):
        raise ValueError("Expected (Nt,Nx,Ny,Nz) with integer extents at least 2")
    return tuple(int(n) for n in geometry)


def dagger(matrix):
    return np.swapaxes(np.conjugate(matrix), -1, -2)


def validate_links(links, tolerance=1e-10):
    u = np.asarray(links)
    if u.ndim != 7 or u.shape[-3:] != (4, 3, 3):
        raise ValueError("Links require shape (Nt,Nx,Ny,Nz,4,3,3)")
    _geometry(u.shape[:4])
    if u.dtype != np.complex128 or not np.isfinite(u).all():
        raise ValueError("Links must be finite complex128 without implicit casting")
    if not np.isfinite(tolerance) or not 0 < tolerance <= 1e-8:
        raise ValueError("Invalid group-check tolerance")
    unitary_error = float(np.max(np.abs(u @ dagger(u) - np.eye(3))))
    determinant_error = float(np.max(np.abs(np.linalg.det(u) - 1)))
    if max(unitary_error, determinant_error) > tolerance:
        raise ValueError(f"Links are outside SU(3): unitary={unitary_error}, det={determinant_error}")
    return dict(unitarity_max_abs=unitary_error, determinant_max_abs=determinant_error,
                tolerance=tolerance, link_count=int(np.prod(u.shape[:4]) * 4))


def haar_su3(rng, shape=()):
    """Complex-Gaussian QR with phase correction, projected to determinant one."""
    shape = tuple(shape)
    z = rng.normal(size=shape + (3, 3)) + 1j * rng.normal(size=shape + (3, 3))
    q, r = np.linalg.qr(z)
    diagonal = np.diagonal(r, axis1=-2, axis2=-1)
    phase = diagonal / np.abs(diagonal)
    q = q * phase[..., None, :]
    # Dividing one column by det maps Haar U(3) to Haar SU(3).
    q[..., :, 0] /= np.linalg.det(q)[..., None]
    return np.asarray(q, dtype=np.complex128)


def initial_links(geometry, start, rng):
    geometry = _geometry(geometry)
    if start == "cold":
        return np.broadcast_to(np.eye(3, dtype=np.complex128), geometry + (4, 3, 3)).copy()
    if start == "hot":
        return haar_su3(rng, geometry + (4,))
    raise ValueError("Start must be cold or hot")


def _shift(site, direction, amount, geometry):
    result = list(site)
    result[direction] = (result[direction] + amount) % geometry[direction]
    return tuple(result)


def staple(links, site, mu):
    """Sum paths from x+mu to x, so local action is -beta/3 ReTr(U_mu V)."""
    geometry = links.shape[:4]
    site = tuple(site)
    x_mu = _shift(site, mu, 1, geometry)
    result = np.zeros((3, 3), dtype=np.complex128)
    for nu in range(4):
        if nu == mu:
            continue
        x_nu = _shift(site, nu, 1, geometry)
        x_minus_nu = _shift(site, nu, -1, geometry)
        x_mu_minus_nu = _shift(x_mu, nu, -1, geometry)
        result += (links[x_mu + (nu,)] @ dagger(links[x_nu + (mu,)]) @
                   dagger(links[site + (nu,)]))
        result += (dagger(links[x_mu_minus_nu + (nu,)]) @ dagger(links[x_minus_nu + (mu,)]) @
                   links[x_minus_nu + (nu,)])
    return result


def plaquette(links):
    """Vectorized normalized mean over all six positive plaquette orientations."""
    total = 0.0
    for mu in range(4):
        for nu in range(mu + 1, 4):
            u_mu = links[..., mu, :, :]
            u_nu = links[..., nu, :, :]
            product = (u_mu @ np.roll(u_nu, -1, axis=mu) @
                       dagger(np.roll(u_mu, -1, axis=nu)) @ dagger(u_nu))
            total += float(np.trace(product, axis1=-2, axis2=-1).real.mean() / 3)
    return total / 6


def plaquette_reference(links):
    """Independent explicit ordered-loop implementation, used for verification."""
    total, count = 0.0, 0
    geometry = links.shape[:4]
    for site in np.ndindex(*geometry):
        for mu in range(4):
            for nu in range(mu + 1, 4):
                # Generic signed path walker independent of vectorized rolls.
                matrix, position = np.eye(3, dtype=complex), site
                for direction, sign in ((mu, 1), (nu, 1), (mu, -1), (nu, -1)):
                    if sign == 1:
                        matrix = matrix @ links[position + (direction,)]
                        position = _shift(position, direction, 1, geometry)
                    else:
                        position = _shift(position, direction, -1, geometry)
                        matrix = matrix @ dagger(links[position + (direction,)])
                if position != site:
                    raise AssertionError("Unclosed plaquette")
                total += float(np.trace(matrix).real / 3)
                count += 1
    return total / count


def wilson_action(links, beta):
    return float(beta * (6 * np.prod(links.shape[:4])) * (1 - plaquette(links)))


def polyakov(links):
    """Ordered temporal product, trace/3 at every spatial site."""
    product = np.broadcast_to(np.eye(3, dtype=np.complex128), links.shape[1:4] + (3, 3)).copy()
    for t in range(links.shape[0]):
        product = product @ links[t, ..., 0, :, :]
    return np.trace(product, axis1=-2, axis2=-1) / 3


def gauge_transform(links, gauge):
    g = np.asarray(gauge)
    if g.shape != links.shape[:4] + (3, 3) or not np.isfinite(g).all():
        raise ValueError("Gauge field has wrong shape or nonfinite entries")
    if np.max(np.abs(g @ dagger(g) - np.eye(3))) > 1e-10 or np.max(np.abs(np.linalg.det(g) - 1)) > 1e-10:
        raise ValueError("Gauge transformation is not SU(3)")
    result = np.empty_like(links)
    for mu in range(4):
        result[..., mu, :, :] = g @ links[..., mu, :, :] @ dagger(np.roll(g, -1, axis=mu))
    return result


def center_transform(links, sector=1, time_slice=0):
    if sector not in (0, 1, 2) or not 0 <= time_slice < links.shape[0]:
        raise ValueError("Invalid center transformation")
    result = links.copy()
    result[time_slice, ..., 0, :, :] *= np.exp(2j * np.pi * sector / 3)
    return result


def su2_proposal(rng, width, pair):
    if not 0 < width <= np.pi or pair not in PAIRS:
        raise ValueError("Invalid symmetric subgroup proposal")
    vector = rng.normal(size=3)
    vector /= np.linalg.norm(vector)
    theta = rng.uniform(-width, width)
    x, y, z = np.sin(theta) * vector
    c = np.cos(theta)
    sub = np.array([[c + 1j * z, y + 1j * x], [-y + 1j * x, c - 1j * z]], dtype=np.complex128)
    result = np.eye(3, dtype=np.complex128)
    result[np.ix_(pair, pair)] = sub
    return result


class WilsonChain:
    """Mutable physical link chain with reproducible restart at sweep boundaries."""

    def __init__(self, geometry, beta, seed, start="cold", proposal_width=0.25):
        self.geometry = _geometry(geometry)
        if not np.isfinite(beta) or beta < 0:
            raise ValueError("Wilson beta must be finite and nonnegative")
        if isinstance(seed, bool) or int(seed) != seed or seed < 0:
            raise ValueError("Nonnegative integer PCG64 seed required")
        if not np.isfinite(proposal_width) or not 0 < proposal_width <= np.pi:
            raise ValueError("Invalid fixed proposal width")
        self.beta = float(beta)
        self.seed = int(seed)
        self.start = start
        self.proposal_width = float(proposal_width)
        self.rng = np.random.Generator(np.random.PCG64(seed))
        self.links = initial_links(self.geometry, start, self.rng)
        self.sweeps = 0
        self.attempted = 0
        self.accepted = 0

    def update(self):
        flat = int(self.rng.integers(4 * np.prod(self.geometry)))
        site = tuple(int(n) for n in np.unravel_index(flat // 4, self.geometry))
        mu = flat % 4
        pair = PAIRS[int(self.rng.integers(3))]
        old = self.links[site + (mu,)]
        proposal = su2_proposal(self.rng, self.proposal_width, pair) @ old
        delta = -self.beta / 3 * np.trace((proposal - old) @ staple(self.links, site, mu)).real
        accepted = math.log(max(float(self.rng.random()), np.finfo(float).tiny)) < min(0.0, -float(delta))
        if accepted:
            self.links[site + (mu,)] = proposal
        self.attempted += 1
        self.accepted += int(accepted)
        return bool(accepted), float(delta)

    def sweep(self, count=1):
        if isinstance(count, bool) or int(count) != count or count < 0:
            raise ValueError("Nonnegative integer number of sweeps required")
        for _ in range(int(count)):
            for __ in range(4 * int(np.prod(self.geometry))):
                self.update()
            self.sweeps += 1
        return self

    def checkpoint(self, directory, name="chain"):
        """Atomic immutable pair, with links digest bound into the metadata."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        data_path, metadata_path = directory / f"{name}.npz", directory / f"{name}.json"
        if data_path.exists() or metadata_path.exists():
            raise ValueError("Checkpoint names are immutable; choose a new sweep/name")
        validate_links(self.links)
        metadata = dict(schema="R135-SU3-checkpoint-v1", algorithm=ALGORITHM,
                        geometry=list(self.geometry), beta=self.beta, seed=self.seed,
                        start=self.start, proposal_width=self.proposal_width,
                        sweeps=self.sweeps, attempted=self.attempted, accepted=self.accepted,
                        rng_state=self.rng.bit_generator.state, numpy_version=np.__version__,
                        storage="t,x,y,z,mu,a,b; temporal mu=0; complex128")
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".npz", delete=False) as stream:
            temp_path = Path(stream.name)
            np.savez(stream, links=self.links)
            stream.flush()
            os.fsync(stream.fileno())
        metadata["links_file"] = data_path.name
        metadata["links_sha256"] = _sha(temp_path)
        metadata["metadata_sha256"] = _canonical(metadata)
        meta_tmp = directory / f".{name}.json.tmp"
        try:
            _json(meta_tmp, metadata)
            os.replace(temp_path, data_path)
            os.replace(meta_tmp, metadata_path)
        finally:
            temp_path.unlink(missing_ok=True)
            meta_tmp.unlink(missing_ok=True)
        return metadata_path

    @classmethod
    def resume(cls, metadata_path):
        metadata_path = Path(metadata_path)
        data = read_json(metadata_path)
        digest = data.pop("metadata_sha256", None)
        if digest != _canonical(data) or data.get("schema") != "R135-SU3-checkpoint-v1" or data.get("algorithm") != ALGORITHM:
            raise ValueError("Invalid or altered Wilson checkpoint metadata")
        name = data["links_file"]
        if Path(name).name != name:
            raise ValueError("Unsafe checkpoint link path")
        path = metadata_path.parent / name
        if path.is_symlink() or _sha(path) != data["links_sha256"]:
            raise ValueError("Checkpoint link data hash mismatch")
        # Reproducibility requires the same NumPy implementation and bit generator.
        if data["numpy_version"] != np.__version__ or data["rng_state"]["bit_generator"] != "PCG64":
            raise ValueError("Checkpoint numerical environment/PRNG differs")
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != {"links"}:
                raise ValueError("Unexpected checkpoint fields")
            links = archive["links"]
        validate_links(links)
        obj = cls(data["geometry"], data["beta"], data["seed"], data["start"], data["proposal_width"])
        if tuple(data["geometry"]) != links.shape[:4]:
            raise ValueError("Checkpoint geometry mismatch")
        obj.links = links
        obj.rng.bit_generator.state = data["rng_state"]
        obj.sweeps, obj.attempted, obj.accepted = data["sweeps"], data["attempted"], data["accepted"]
        if obj.attempted != obj.sweeps * 4 * np.prod(obj.geometry) or not 0 <= obj.accepted <= obj.attempted:
            raise ValueError("Checkpoint is not at a consistent sweep boundary")
        return obj


def measure(links, *, chain_id, config_id, sweep, role, beta, seed=None,
            start=None, stride=1, cuts=(0.0, np.pi / 30), burn_sweeps=0,
            source_sha256=None, verify_gauge=True):
    """Gauge invariant measurements and the complete 81-cell tables."""
    group = validate_links(links)
    field = polyakov(links)
    mean_p = plaquette(links)
    checks = dict(group)
    if verify_gauge:
        # Verification RNG is independent of the chain state and never advances it.
        rng = np.random.Generator(np.random.PCG64(1359001))
        transformed = gauge_transform(links, haar_su3(rng, links.shape[:4]))
        checks["gauge_polyakov_max_abs"] = float(np.max(np.abs(polyakov(transformed) - field)))
        checks["gauge_plaquette_abs"] = abs(plaquette(transformed) - mean_p)
        if max(checks["gauge_polyakov_max_abs"], checks["gauge_plaquette_abs"]) >= 1e-10:
            raise ValueError("Local gauge invariance test failed on imported links")
    geometry = list(links.shape[:4])
    return dict(config_id=str(config_id), chain_id=str(chain_id), role=role,
                sweep=int(sweep), geometry=geometry,
                grid_id="x".join(map(str, geometry)), beta=float(beta), seed=seed,
                start=start, burn_sweeps=int(burn_sweeps), plaquette=mean_p,
                polyakov_abs=float(abs(field.mean())),
                polyakov_mean_real=float(field.mean().real),
                polyakov_mean_imag=float(field.mean().imag),
                link_verification="VERIFIED_LINKS", link_checks=checks,
                source_sha256=source_sha256,
                counts_by_cut=[statistics.count_windows(field, stride, cut) for cut in cuts])


def _write_rows(path, rows):
    with Path(path).open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def _load_rows(path):
    with Path(path).open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    statistics.validate_rows(rows)
    return rows


def _load_links(path):
    path = Path(path)
    if path.suffix == ".npy":
        data = np.load(path, allow_pickle=False)
    elif path.suffix == ".npz":
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != {"links"}:
                raise ValueError("Link NPZ must contain only the links array")
            data = archive["links"]
    else:
        raise ValueError("Use documented NPY or NPZ link format; raw archive formats need an explicit converter")
    validate_links(data)
    return data


def import_measurements(config, inputs):
    """Import declared link artifacts or a Polyakov-only archive with its limits."""
    if "ensemble_manifest" not in inputs:
        raise OpenInput("Import requires an ensemble_manifest JSON input")
    manifest = read_json(Path(inputs["ensemble_manifest"]))
    if manifest.get("schema") != "R135-SU3-import-v1" or not manifest.get("source") or not manifest.get("license"):
        raise ValueError("Import requires schema, archive source and license")
    if not manifest.get("chain_history_source"):
        raise ValueError("Independent chain history is required, not just a set of fields")
    rows = []
    for entry in manifest["configurations"]:
        if entry["artifact"] not in inputs:
            raise ValueError(f"Missing source artifact {entry['artifact']}")
        path = Path(inputs[entry["artifact"]])
        digest = _sha(path)
        if entry.get("sha256") != digest:
            raise ValueError("Imported configuration digest disagrees with manifest")
        kwargs = {key: entry[key] for key in ("chain_id", "config_id", "sweep", "role", "beta")}
        kwargs.update(seed=entry.get("seed"), start=entry.get("start"),
                      burn_sweeps=entry.get("burn_sweeps", 0), stride=int(config.get("stride", 1)),
                      cuts=config.get("cuts_rad", [0.0, float(np.pi / 30)]))
        if entry.get("kind", "links") == "links":
            links = _load_links(path)
            row = measure(links, source_sha256=digest, **kwargs)
            if entry.get("plaquette") is not None and abs(row["plaquette"] - entry["plaquette"]) > entry.get("plaquette_tolerance", 1e-10):
                raise ValueError("Imported archive plaquette does not match independent measurement")
        elif entry["kind"] == "polyakov":
            field = np.load(path, allow_pickle=False)
            geometry = entry["geometry"]
            _geometry(geometry)
            if field.shape != tuple(geometry[1:]):
                raise ValueError("Imported Polyakov geometry mismatch")
            if not np.isfinite(entry["plaquette"]):
                raise ValueError("Polyakov-only archive needs source plaquette history")
            row = {key: value for key, value in kwargs.items() if key not in ("stride", "cuts")}
            row.update(geometry=geometry, grid_id="x".join(map(str, geometry)),
                       source_sha256=digest, plaquette=entry["plaquette"],
                       polyakov_abs=float(abs(field.mean())),
                       link_verification="UNVERIFIED_LINKS", link_checks=None,
                       counts_by_cut=[statistics.count_windows(field, kwargs["stride"], cut)
                                      for cut in kwargs["cuts"]])
        else:
            raise ValueError("Unknown archive representation")
        row["archive_source"] = manifest["source"]
        rows.append(row)
    statistics.validate_rows(rows)
    return rows


def _generate_group(config, specs, inputs, out, calibration=None):
    rows = []
    geometry = _geometry(config["geometry"])
    for spec in specs:
        chain_id = str(spec["chain_id"])
        if not chain_id or Path(chain_id).name != chain_id or chain_id in (".", ".."):
            raise ValueError("Unsafe or missing chain id")
        role = spec["role"]
        if role not in ("calibration", "heldout"):
            raise ValueError("Unknown chain split")
        if spec.get("checkpoint_input"):
            chain = WilsonChain.resume(inputs[spec["checkpoint_input"]])
            if (chain.geometry != geometry or chain.beta != config["beta"] or chain.seed != spec["seed"]
                    or chain.start != spec["start"] or chain.proposal_width != config.get("proposal_width", 0.25)):
                raise ValueError("Resumed chain differs from requested fixed parameters")
        else:
            chain = WilsonChain(geometry, config["beta"], spec["seed"], spec["start"], config.get("proposal_width", 0.25))
        burn = spec["burn_sweeps"]
        saves = spec["samples"]
        cadence = spec["save_every"]
        for value in (burn, saves, cadence):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("Explicit nonnegative integer chain schedule required")
        if saves < 1 or cadence < 1:
            raise ValueError("Positive samples and save_every required")
        if role == "heldout" and calibration is not None and config.get("enforce_pilot_lengths", True):
            if calibration["tau_max"] is None:
                raise ValueError("Pilot has not resolved a chain length")
            saves = max(saves, int(calibration["heldout_min_saves"]))
            burn = max(burn, math.ceil(20 * calibration["tau_max"] * cadence))
        chain.sweep(max(0, burn - chain.sweeps))
        chain_out = Path(out) / "chains" / chain_id
        chain_out.mkdir(parents=True, exist_ok=True)
        chain_rows = []
        # Every sample stores its links and exact PRNG state; no claims based only
        # on an unrecoverable last field. Interrupted stages may resume a boundary.
        for _ in range(saves):
            chain.sweep(cadence)
            name = f"sweep-{chain.sweeps:012d}"
            checkpoint = chain.checkpoint(chain_out, name)
            links_path = checkpoint.with_suffix(".npz")
            row = measure(chain.links, chain_id=chain_id, config_id=f"{chain_id}:{chain.sweeps}",
                          sweep=chain.sweeps, role=role, beta=chain.beta,
                          seed=chain.seed, start=chain.start, stride=config.get("stride", 1),
                          cuts=config.get("cuts_rad", [0.0, float(np.pi / 30)]), burn_sweeps=burn,
                          source_sha256=_sha(links_path), verify_gauge=(len(chain_rows) == 0))
            row["links_artifact"] = str(links_path.relative_to(out))
            row["checkpoint_artifact"] = str(checkpoint.relative_to(out))
            row["algorithm"] = ALGORITHM
            row["acceptance"] = chain.accepted / chain.attempted
            chain_rows.append(row)
            # Persist the verified prefix before advancing the chain again.
            _write_rows(chain_out / "measurements.jsonl", chain_rows)
        rows.extend(chain_rows)
    statistics.validate_rows(rows)
    return rows


def _standard_outputs(out, all_rows, analysis, calibration):
    out = Path(out)
    heldout = [row for row in all_rows if row["role"] == "heldout"]
    _write_rows(out / "heldout_counts.jsonl", heldout)
    _write_rows(out / "measurements.jsonl", all_rows)
    _json(out / "mixing.json", analysis)
    if calibration is not None:
        _json(out / "calibration.json", calibration)
    fields = ["grid_id", "chain_id", "config_id", "role", "sweep", "beta", "start", "seed",
              "plaquette", "polyakov_abs", "link_verification", "source_sha256", "links_artifact", "checkpoint_artifact"]
    with (out / "ensemble_manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in fields} for row in all_rows)
    with (out / "ym_connected.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["grid_id", "cut_rad", "D4", "ci95_low", "ci95_high", "classification",
                  "lower_plaquette_cut", "upper_plaquette_cut", "low_windows", "high_windows", "reasons"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in analysis.get("estimates", []):
            primary = row["primary"]
            interval = primary["interval95"] or [None, None]
            writer.writerow(dict(grid_id=analysis["grid_id"], cut_rad=row["cut_rad"], D4=primary["D4"],
                                 ci95_low=interval[0], ci95_high=interval[1], classification=row["classification"],
                                 lower_plaquette_cut=calibration["lower_cut"], upper_plaquette_cut=calibration["upper_cut"],
                                 low_windows=(primary["low"] or {}).get("windows", 0),
                                 high_windows=(primary["high"] or {}).get("windows", 0),
                                 reasons=";".join(row["reasons"])))


def run(config, inputs, out):
    """P3 stage entry point.

    Operations: generate_calibration, generate_heldout, generate_analyze,
    import (links/Polyakov), analyze (saved measurements).  A generation
    request supplies an explicit schedule for each independent chain.
    generate_analyze freezes cuts after calibration and before generating any
    heldout field.  It never lengthens a chain after looking at heldout D4.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    operation = config.get("operation", "analyze")
    calibration = None
    if "calibration" in inputs:
        calibration = read_json(Path(inputs["calibration"]))
        statistics.verify_calibration(calibration)
    if operation in ("generate_calibration", "generate_heldout", "generate_analyze"):
        specs = config.get("chains", [])
        if not specs or len({str(c["chain_id"]) for c in specs}) != len(specs):
            raise ValueError("Distinct chain specifications required")
        if len({c["seed"] for c in specs}) != len(specs):
            raise ValueError("Distinct chain seeds required")
        calibrators = [c for c in specs if c["role"] == "calibration"]
        held = [c for c in specs if c["role"] == "heldout"]
        if len(calibrators) + len(held) != len(specs):
            raise ValueError("Unknown chain roles")
        if operation == "generate_calibration" and held:
            raise ValueError("Calibration operation cannot inspect heldout chains")
        if operation == "generate_heldout" and calibrators:
            raise ValueError("Heldout operation must use an already frozen calibration")
        rows = []
        if calibrators:
            if calibration is not None:
                raise ValueError("Refusing to replace a frozen calibration in-place")
            rows = _generate_group(config, calibrators, inputs, out)
            calibration = statistics.freeze_calibration(rows)
            _json(out / "calibration.json", calibration)
        if held:
            if calibration is None:
                raise OpenInput("Generate heldout chains only after freezing the independent calibration")
            if not calibration["stable"] and config.get("_mode", "validation") != "validation":
                # Preserve the pilot and its exact failed criterion, without
                # opening confirmatory chains using an unresolved plan.
                held = []
            else:
                rows += _generate_group(config, held, inputs, out, calibration)
    elif operation == "import":
        rows = import_measurements(config, inputs)
    elif operation == "analyze":
        if "measurements" not in inputs:
            raise OpenInput("P3 analyze requires measurements input")
        rows = _load_rows(inputs["measurements"])
    else:
        raise ValueError("Unknown P3 operation")
    statistics.validate_rows(rows)
    heldout = [row for row in rows if row["role"] == "heldout"]
    calibrators = [row for row in rows if row["role"] == "calibration"]
    if calibration is None and calibrators:
        if heldout:
            raise ValueError("Imported heldout data requires a previously frozen calibration artifact")
        calibration = statistics.freeze_calibration(calibrators)
    if heldout:
        if calibration is None:
            raise OpenInput("Frozen calibration is missing")
        settings = config.get("analysis", {})
        analysis = statistics.analyze_chains(
            heldout, calibration, cuts=config.get("cuts_rad", [0.0, float(np.pi / 30)]),
            draws=int(settings.get("bootstrap_draws", 4000)), seed=int(settings.get("bootstrap_seed", 13590)),
            equivalence_band=float(settings.get("equivalence_band", 1e-3)),
            min_ess=float(settings.get("min_ess", 100)), min_blocks=int(settings.get("min_blocks", 20)),
            independent_plaquette=config.get("independent_plaquette"))
    else:
        analysis = dict(schema="R135-P3-statistics-v1", scientific_status="INCONCLUSIVE",
                        estimates=[], reasons=["CALIBRATION_ONLY_NO_HELDOUT_RESULT"],
                        mixing={} if calibration is None else calibration["mixing"])
    _standard_outputs(out, rows, analysis, calibration)
    limitations = sorted(set(analysis.get("reasons", []) +
                             [reason for row in analysis.get("estimates", []) for reason in row["reasons"]]))
    return dict(software_status="PASS", evidence_status=analysis["scientific_status"],
                metrics=dict(configurations=len(rows), heldout_configurations=len(heldout),
                             independent_chains=len(set(row["chain_id"] for row in rows)),
                             algorithm=ALGORITHM if operation.startswith("generate") else "declared_archive",
                             grid_id=rows[0]["grid_id"]), limitations=limitations)
