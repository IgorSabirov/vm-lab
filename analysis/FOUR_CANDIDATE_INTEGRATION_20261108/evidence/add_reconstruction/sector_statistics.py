#!/usr/bin/env python3
"""Exact sector statistics for the reconstructed ADD C2 ring backend.

This module counts labelled cyclic bit configurations, not trajectories from
an iid random-number generator. It distinguishes:
  E0: no split vertex and no directed merge edge;
  Q : E0 plus no split motif created by the first sqrt(tau) half-shift.

For an E0 state, Q is the class that remains in the quiet orbit. The result
is specific to the four-bit, two-port, oriented-cycle reconstruction in
add_backend_smoke_v1.py; it is not an ADD theorem for arbitrary graphs.

The four conserved counts are ordered as (a1, b1, a2, b2).
Standard library only.
"""
from __future__ import annotations

import argparse
import functools
import itertools
import json
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

STATES: tuple[tuple[int, int, int, int], ...] = tuple(
    itertools.product((0, 1), repeat=4)
)
SPLIT_STATES = frozenset(((1, 1, 0, 0), (0, 0, 1, 1)))
ALLOWED_STATES = tuple(i for i, s in enumerate(STATES) if s not in SPLIT_STATES)


def is_merge_pair(s: tuple[int, ...], t: tuple[int, ...]) -> bool:
    """Directed old-edge merge motifs for canonical b_i -> a_{i+1}."""
    return (
        s == (1, 0, 0, 0) and t == (0, 1, 0, 0)
    ) or (
        s == (0, 0, 1, 0) and t == (0, 0, 0, 1)
    )


def half_shift_state(s: tuple[int, ...], t: tuple[int, ...]) -> tuple[int, ...]:
    """State at w_i over the directed old edge s_i -> s_{i+1}."""
    return (s[0], t[1], s[2], t[3])


def creates_split(s: tuple[int, ...], t: tuple[int, ...]) -> bool:
    return half_shift_state(s, t) in SPLIT_STATES


def transition_table(quiet: bool) -> tuple[tuple[int, ...], ...]:
    """Allowed pair transitions in E0 (or in Q if quiet=True)."""
    rows: list[tuple[int, ...]] = []
    for i in range(16):
        s = STATES[i]
        row = []
        for j in ALLOWED_STATES:
            t = STATES[j]
            if is_merge_pair(s, t):
                continue
            if quiet and creates_split(s, t):
                continue
            row.append(j)
        rows.append(tuple(row))
    return tuple(rows)


def count_sector(
    length: int,
    particle_vector: Sequence[int],
    *,
    quiet: bool = False,
) -> int:
    """Count E0 or quiet cyclic configurations in a fixed 4-count sector.

    Counts labelled ring configurations s_0,...,s_{L-1}. The last-to-first
    directed transition is included. All arithmetic is exact integer.
    """
    if length < 2:
        raise ValueError("length must be >= 2 for this ring implementation")
    target = tuple(int(x) for x in particle_vector)
    if len(target) != 4 or any(x < 0 or x > length for x in target):
        raise ValueError("particle_vector must contain four integers in [0,L]")

    transitions = transition_table(quiet)
    total = 0

    for start in ALLOWED_STATES:
        first = STATES[start]
        remaining0 = tuple(target[k] - first[k] for k in range(4))
        if any(x < 0 for x in remaining0):
            continue

        @functools.lru_cache(maxsize=None)
        def rec(pos: int, last: int, remaining: tuple[int, ...]) -> int:
            if pos == length:
                return int(
                    remaining == (0, 0, 0, 0)
                    and start in transitions[last]
                )
            result = 0
            for nxt in transitions[last]:
                state = STATES[nxt]
                next_remaining = tuple(
                    remaining[k] - state[k] for k in range(4)
                )
                if min(next_remaining) >= 0:
                    result += rec(pos + 1, nxt, next_remaining)
            return result

        total += rec(1, start, remaining0)

    return total


def count_total_sector(length: int, total_particles: int, *, quiet: bool = False) -> int:
    """Coarse fixed-total-p count; this mixes different conserved 4-vectors."""
    if length < 2:
        raise ValueError("length must be >= 2 for this ring implementation")
    if total_particles < 0 or total_particles > 4 * length:
        raise ValueError("total_particles must be in [0,4L]")
    transitions = transition_table(quiet)
    total = 0
    for start in ALLOWED_STATES:
        remaining0 = total_particles - sum(STATES[start])
        if remaining0 < 0:
            continue
        @functools.lru_cache(maxsize=None)
        def rec(pos: int, last: int, remaining: int) -> int:
            if pos == length:
                return int(remaining == 0 and start in transitions[last])
            result = 0
            for nxt in transitions[last]:
                next_remaining = remaining - sum(STATES[nxt])
                if next_remaining >= 0:
                    result += rec(pos + 1, nxt, next_remaining)
            return result
        total += rec(1, start, remaining0)
    return total


@dataclass(frozen=True)
class SectorResult:
    length: int
    particle_vector: tuple[int, int, int, int]
    total_particles: int
    e0_configurations: int
    quiet_configurations: int
    p_quiet_given_e0: float | None
    definition: str = "uniform over labelled cyclic configurations in fixed (a1,b1,a2,b2) sector, conditioned on E0"
    scope: str = "reconstructed four-bit oriented-cycle backend; not an author theorem"


def calculate(length: int, particle_vector: Sequence[int]) -> SectorResult:
    pvec = tuple(int(x) for x in particle_vector)
    n_e0 = count_sector(length, pvec, quiet=False)
    n_quiet = count_sector(length, pvec, quiet=True)
    probability = n_quiet / n_e0 if n_e0 else None
    return SectorResult(
        length=length,
        particle_vector=pvec,  # type: ignore[arg-type]
        total_particles=sum(pvec),
        e0_configurations=n_e0,
        quiet_configurations=n_quiet,
        p_quiet_given_e0=probability,
    )


def calculate_total(length: int, total_particles: int) -> dict:
    n_e0 = count_total_sector(length, total_particles, quiet=False)
    n_quiet = count_total_sector(length, total_particles, quiet=True)
    return {
        "length": length,
        "total_particles": total_particles,
        "e0_configurations": n_e0,
        "quiet_configurations": n_quiet,
        "p_quiet_given_e0": n_quiet / n_e0 if n_e0 else None,
        "definition": "uniform over labelled cyclic configurations with fixed total p, conditioned on E0; mixes conserved 4-vectors",
        "scope": "reconstructed four-bit oriented-cycle backend; not an author theorem",
    }


def self_test() -> dict:
    """Small direct brute-force check at L=3 for selected sectors."""
    checks = []
    for target in ((1, 1, 0, 0), (1, 1, 1, 0), (1, 1, 1, 1)):
        brute_e0 = brute_quiet = 0
        for config in itertools.product(STATES, repeat=3):
            if any(s in SPLIT_STATES for s in config):
                continue
            if any(is_merge_pair(config[i], config[(i + 1) % 3]) for i in range(3)):
                continue
            if tuple(sum(s[k] for s in config) for k in range(4)) != target:
                continue
            brute_e0 += 1
            half = [half_shift_state(config[i], config[(i + 1) % 3]) for i in range(3)]
            if not any(s in SPLIT_STATES for s in half):
                brute_quiet += 1
        exact_e0 = count_sector(3, target, quiet=False)
        exact_quiet = count_sector(3, target, quiet=True)
        checks.append({
            "particle_vector": target,
            "brute_e0": brute_e0,
            "transfer_e0": exact_e0,
            "brute_quiet": brute_quiet,
            "transfer_quiet": exact_quiet,
            "pass": (brute_e0 == exact_e0 and brute_quiet == exact_quiet),
        })
    return {"status": "PASS" if all(x["pass"] for x in checks) else "FAIL", "checks": checks}


def parse_vector(s: str) -> tuple[int, int, int, int]:
    try:
        vals = tuple(int(x.strip()) for x in s.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use four comma-separated integers") from exc
    if len(vals) != 4 or any(x < 0 for x in vals):
        raise argparse.ArgumentTypeError("use four nonnegative integers: a1,b1,a2,b2")
    return vals  # type: ignore[return-value]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--L", type=int, default=12, help="ring size")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--particles", type=parse_vector,
        help="fixed counts a1,b1,a2,b2 (four-vector sector)",
    )
    group.add_argument(
        "--total-p", type=int,
        help="fixed total particle number (coarse mixture of four-vectors)",
    )
    parser.add_argument("--self-test", action="store_true", help="brute-force L=3 checks")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return
    if args.total_p is not None:
        result = calculate_total(args.L, args.total_p)
        print(json.dumps(result, indent=2))
    else:
        vector = args.particles if args.particles is not None else (4, 6, 7, 7)
        result = calculate(args.L, vector)
        print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
