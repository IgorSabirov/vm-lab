#!/usr/bin/env python3
"""
R125-multi: bounded multi-token causal resource pilot.

This is not a full distributed engine.
It checks the minimum v3 race:
  - shared sender budget;
  - acceptance lease vs quarantine/return;
  - causal loss notification;
  - node destruction without instant remote cleanup;
  - return capacity at sender;
  - negative controls for known defects.

Exact arithmetic: fractions.Fraction.
No NumPy, no BLAS, no GPU, no network.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import os
import platform
import resource
import time
from dataclasses import dataclass, field
from fractions import Fraction as F
from typing import Any, Dict, List, Optional, Tuple


# Local event phases.
# EXPIRE first, so arrival at deadline is stale.
PH_EXPIRE = 0
PH_ARRIVE = 1
PH_PROCESS = 2

TERMINAL_SENDER_STATES = {
    "DELIVERED",
    "RETURNED",
    "LOST",
    "EXPIRED_ACK",
    "REJECTED",
}


@dataclass
class SenderToken:
    dest: str
    demand: F
    phi: F = F(0)
    state: str = "PENDING"
    ack_deadline: F = F(0)
    return_reserved: F = F(0)


@dataclass
class ReceiverToken:
    reserved: F = F(0)
    deadline: F = F(0)
    state: str = "NONE"


@dataclass
class Node:
    x: F
    cap: F
    stock: F = F(0)
    escrow: F = F(0)
    quarantine: F = F(0)
    destroyed: bool = False
    tokens: Dict[str, Any] = field(default_factory=dict)


class Sim:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

        self.V = Node(x=F(0), cap=cfg.get("cap_V", F(1)))
        self.W = {
            "W1": Node(x=F(-1), cap=cfg.get("cap_W", F(1, 2))),
            "W2": Node(x=F(1), cap=cfg.get("cap_W", F(1, 2))),
        }

        self.initial_total: F = cfg.get("initial_stock", F(3, 4))
        self.V.stock = self.initial_total

        self.transit_out: Dict[str, F] = {}
        self.transit_return: Dict[str, F] = {}

        self.lost: F = F(0)
        self.consumed: F = F(0)
        self.injected: F = F(0)

        self.queue: List[Tuple[F, int, int, str, Dict[str, Any]]] = []
        self.seq: int = 0

        self.violations: set[str] = set()
        self.probes: Dict[str, F] = {}
        self.classification: Dict[str, str] = {}
        self.event_count: int = 0

        # Requests are generated at receivers at t=0 and arrive at V at req_delay.
        requests = cfg.get(
            "requests",
            [
                ("r1", "W1", F(1, 2)),
                ("r2", "W2", F(1, 2)),
            ],
        )

        for token, dest, demand in requests:
            self.V.tokens[token] = SenderToken(dest=dest, demand=F(demand))
            self.put(
                cfg.get("req_delay", F(1)),
                PH_ARRIVE,
                "req_arrive",
                {"token": token, "dest": dest},
            )

        # Allocation happens after all same-time request arrivals.
        self.put(
            cfg.get("alloc_time", F(1)),
            PH_PROCESS,
            "allocate",
            {},
        )

        # External injections into V, used for return-capacity tests.
        for t, amount in cfg.get("injections", []):
            self.put(F(t), PH_ARRIVE, "inject", {"amount": F(amount)})

        # Optional in-transit loss.
        if cfg.get("loss_token"):
            self.put(
                F(cfg["loss_time"]),
                PH_ARRIVE,
                "loss_event",
                {"token": cfg["loss_token"]},
            )

        # Optional node destruction.
        if cfg.get("destroy_dest"):
            self.put(
                F(cfg["destroy_time"]),
                PH_ARRIVE,
                "destroy_node",
                {"dest": cfg["destroy_dest"]},
            )

        # Probes: local reads at specified times.
        for probe in cfg.get("probes", []):
            kind = probe[0]
            t = F(probe[-1])
            if kind == "W_reserved":
                _, token, dest, _ = probe
                payload = {"probe": "W_reserved", "token": token, "dest": dest}
            elif kind == "V_inflight":
                _, token, _ = probe
                payload = {"probe": "V_inflight", "token": token, "dest": None}
            elif kind == "V_return_reserved":
                _, token, _ = probe
                payload = {"probe": "V_return_reserved", "token": token, "dest": None}
            else:
                raise ValueError(f"unknown probe {kind}")

            label = self._probe_label(payload)
            payload["label"] = label
            self.put(t, PH_ARRIVE, "probe", payload)

    def _probe_label(self, payload: Dict[str, Any]) -> str:
        kind = payload["probe"]
        token = payload.get("token")
        dest = payload.get("dest")
        if dest:
            return f"{kind}:{token}@{dest}"
        return f"{kind}:{token}"

    def put(self, t: F, phase: int, kind: str, payload: Dict[str, Any]) -> None:
        self.seq += 1
        order = -self.seq if self.cfg.get("reverse", False) else self.seq
        heapq.heappush(self.queue, (F(t), phase, order, kind, payload))

    def snapshot(self) -> Dict[str, F]:
        return {
            "V_stock": self.V.stock,
            "V_escrow": self.V.escrow,
            "W1_stock": self.W["W1"].stock,
            "W1_quarantine": self.W["W1"].quarantine,
            "W2_stock": self.W["W2"].stock,
            "W2_quarantine": self.W["W2"].quarantine,
            "transit_out": sum(self.transit_out.values(), F(0)),
            "transit_return": sum(self.transit_return.values(), F(0)),
            "lost": self.lost,
            "consumed": self.consumed,
            "injected": self.injected,
        }

    def audit(self) -> None:
        total = (
            self.V.stock
            + self.V.escrow
            + self.W["W1"].stock
            + self.W["W1"].quarantine
            + self.W["W2"].stock
            + self.W["W2"].quarantine
            + sum(self.transit_out.values(), F(0))
            + sum(self.transit_return.values(), F(0))
            + self.lost
            + self.consumed
        )

        expected = self.initial_total + self.injected

        if total != expected:
            self.violations.add("resource_balance")

        vals = [
            self.V.stock,
            self.V.escrow,
            self.W["W1"].stock,
            self.W["W1"].quarantine,
            self.W["W2"].stock,
            self.W["W2"].quarantine,
            self.lost,
            self.consumed,
            self.injected,
            *self.transit_out.values(),
            *self.transit_return.values(),
        ]
        if any(v < 0 for v in vals):
            self.violations.add("nonnegative")

        v_return_reserved = sum(
            (t.return_reserved for t in self.V.tokens.values()),
            F(0),
        )
        v_used = self.V.stock + self.V.escrow + v_return_reserved
        if v_used > self.V.cap:
            self.violations.add("capacity_V")

        for name, w in self.W.items():
            reserved = sum((rt.reserved for rt in w.tokens.values()), F(0))
            used = w.stock + w.quarantine + reserved
            if used > w.cap:
                self.violations.add(f"capacity_{name}")

    def run(self) -> Dict[str, Any]:
        while self.queue:
            t, _phase, _order, kind, payload = heapq.heappop(self.queue)
            self.event_count += 1
            self.handle(t, kind, payload)
            self.audit()

        return self.summary()

    def handle(self, now: F, kind: str, p: Dict[str, Any]) -> None:
        cfg = self.cfg
        defect = cfg.get("defect")

        lease = F(cfg.get("lease", F(3)))
        ack_wait = F(cfg.get("ack_wait", F(3)))
        offer_delay = F(cfg.get("offer_delay", F(1)))
        ack_delay = F(cfg.get("ack_delay", F(1)))
        cargo_delay = F(cfg.get("cargo_delay", F(1)))
        return_delay = F(cfg.get("return_delay", F(1)))
        notice_delay = F(cfg.get("notice_delay", F(1, 2)))

        if kind == "req_arrive":
            token = p["token"]
            tstate = self.V.tokens.get(token)
            if tstate is None:
                return
            if tstate.state == "PENDING":
                # Request is now causally available to V.
                pass
            return

        if kind == "allocate":
            pending = [
                tid
                for tid, t in self.V.tokens.items()
                if t.state == "PENDING"
            ]
            if not pending:
                return

            D = sum((self.V.tokens[tid].demand for tid in pending), F(0))

            if defect == "independent_spend":
                # Defect: each edge is checked against the original stock,
                # not against the remaining aggregate stock.
                original = self.V.stock
                for tid in sorted(pending):
                    t = self.V.tokens[tid]
                    if original >= t.demand:
                        t.phi = t.demand
                        self.V.stock -= t.phi
                        self.V.escrow += t.phi
                        t.state = "WAIT_ACK"
                        t.ack_deadline = now + ack_wait
                        if defect != "no_expiry":
                            self.put(
                                t.ack_deadline,
                                PH_EXPIRE,
                                "expire_ack",
                                {"token": tid},
                            )
                        self.put(
                            now + offer_delay,
                            PH_ARRIVE,
                            "offer_arrive",
                            {"token": tid, "dest": t.dest, "amount": t.phi},
                        )
                return

            if D == 0:
                factor = F(0)
            else:
                factor = min(F(1), self.V.stock / D)

            for tid in sorted(pending):
                t = self.V.tokens[tid]
                phi = t.demand * factor
                t.phi = phi

                if phi == 0:
                    t.state = "REJECTED"
                    self.classification[tid] = "NO_RESOURCE"
                    continue

                self.V.stock -= phi
                self.V.escrow += phi
                t.state = "WAIT_ACK"
                t.ack_deadline = now + ack_wait

                if defect != "no_expiry":
                    self.put(
                        t.ack_deadline,
                        PH_EXPIRE,
                        "expire_ack",
                        {"token": tid},
                    )

                self.put(
                    now + offer_delay,
                    PH_ARRIVE,
                    "offer_arrive",
                    {"token": tid, "dest": t.dest, "amount": phi},
                )

            return

        if kind == "offer_arrive":
            token = p["token"]
            dest = p["dest"]
            amount = F(p["amount"])
            w = self.W[dest]
            t = self.V.tokens.get(token)

            if t is None or amount == 0:
                return

            if w.destroyed:
                self.put(
                    now + notice_delay,
                    PH_ARRIVE,
                    "reject_notice_V",
                    {"token": token},
                )
                self.classification[token] = "REJECTED_DESTROYED"
                return

            rt = w.tokens.setdefault(token, ReceiverToken())
            if rt.state != "NONE":
                return

            other_reserved = sum(
                (x.reserved for tid, x in w.tokens.items() if tid != token),
                F(0),
            )
            available = w.cap - (w.stock + w.quarantine + other_reserved)

            if amount <= available:
                rt.reserved = amount
                rt.deadline = now + lease
                rt.state = "RESERVED"

                if defect != "no_expiry":
                    self.put(
                        rt.deadline,
                        PH_EXPIRE,
                        "expire_accept",
                        {"token": token, "dest": dest},
                    )

                self.put(
                    now + ack_delay,
                    PH_ARRIVE,
                    "ack_arrive",
                    {"token": token},
                )

                if cfg.get("duplicates", False):
                    # Duplicate ACK notifications. Correct handler must be idempotent.
                    self.put(
                        now + ack_delay,
                        PH_ARRIVE,
                        "ack_arrive",
                        {"token": token},
                    )
                    self.put(
                        now + 10,
                        PH_ARRIVE,
                        "ack_arrive",
                        {"token": token},
                    )
            else:
                rt.state = "REJECTED"
                self.put(
                    now + notice_delay,
                    PH_ARRIVE,
                    "reject_notice_V",
                    {"token": token},
                )
                self.classification[token] = "REJECTED_CAPACITY"

            return

        if kind == "ack_arrive":
            token = p["token"]
            t = self.V.tokens.get(token)
            if t is None:
                return

            amount = t.phi
            valid = (t.state == "WAIT_ACK") and (now < t.ack_deadline)

            if defect == "late_ack":
                # Defect: accept ACK even after local ACK deadline.
                valid = t.state in ("WAIT_ACK", "EXPIRED_ACK")

            if not valid:
                return

            self.V.escrow -= amount
            t.state = "IN_FLIGHT"

            if defect != "no_return_reserve":
                t.return_reserved = amount

            self.transit_out[token] = amount

            self.put(
                now + cargo_delay,
                PH_ARRIVE,
                "cargo_arrive",
                {"token": token, "dest": t.dest},
            )

            return

        if kind == "expire_ack":
            token = p["token"]
            t = self.V.tokens.get(token)
            if t is None or t.state != "WAIT_ACK":
                return

            self.V.escrow -= t.phi
            self.V.stock += t.phi
            t.state = "EXPIRED_ACK"
            t.return_reserved = F(0)
            self.classification.setdefault(token, "NO_SEND")
            return

        if kind == "expire_accept":
            token = p["token"]
            dest = p["dest"]
            w = self.W[dest]
            rt = w.tokens.get(token)
            if rt is None or rt.state != "RESERVED":
                return

            rt.reserved = F(0)
            rt.state = "EXPIRED"
            return

        if kind == "cargo_arrive":
            token = p["token"]
            dest = p["dest"]
            amount = self.transit_out.get(token, F(0))

            if amount == 0:
                return

            w = self.W[dest]
            t = self.V.tokens.get(token)
            rt = w.tokens.get(token)

            if t is None:
                return

            if w.destroyed:
                self.transit_out[token] = F(0)
                self.lost += amount
                self.classification[token] = "DESTROYED_LOST"

                if rt is not None and rt.state == "RESERVED":
                    rt.reserved = F(0)
                    rt.state = "DESTROYED"

                self.put(
                    now + notice_delay,
                    PH_ARRIVE,
                    "loss_notice_V",
                    {"token": token},
                )
                return

            if (
                rt is not None
                and rt.state == "RESERVED"
                and now < rt.deadline
                and rt.reserved >= amount
            ):
                self.transit_out[token] = F(0)
                rt.reserved -= amount
                w.stock += amount
                rt.state = "ARRIVED_VALID"
                self.classification[token] = "VALID"

                self.put(
                    now + notice_delay,
                    PH_ARRIVE,
                    "valid_notice_V",
                    {"token": token},
                )
                return

            # Stale or unauthorized arrival.
            self.transit_out[token] = F(0)

            if defect == "drop_stale":
                # Defect: cargo disappears from accounting.
                self.classification[token] = "DROP_STALE"
                return

            if defect == "stale_accept":
                # Defect: accept stale cargo as if it were valid.
                if rt is None:
                    rt = w.tokens.setdefault(token, ReceiverToken())
                w.stock += amount
                rt.state = "STALE_ACCEPTED"
                self.classification[token] = "INVALID_STALE_ACCEPT"
                self.put(
                    now + notice_delay,
                    PH_ARRIVE,
                    "valid_notice_V",
                    {"token": token},
                )
                return

            if rt is None:
                rt = w.tokens.setdefault(token, ReceiverToken())

            other_reserved = sum(
                (x.reserved for tid, x in w.tokens.items() if tid != token),
                F(0),
            )
            available = w.cap - (w.stock + w.quarantine + other_reserved)

            if amount <= available:
                w.quarantine += amount
                rt.state = "QUARANTINED"
                self.classification[token] = (
                    "STALE_AUTHORIZED"
                    if t.state == "IN_FLIGHT"
                    else "UNAUTHORIZED"
                )

                # Move from quarantine into return transit at the same local time,
                # but after arrival processing.
                self.put(
                    now,
                    PH_PROCESS,
                    "return_depart",
                    {"token": token, "dest": dest, "amount": amount},
                )
            else:
                # Explicit overflow policy: count as lost and flag violation.
                self.lost += amount
                rt.state = "LOST_OVERFLOW"
                self.classification[token] = "OVERFLOW"
                self.violations.add("capacity_overflow")

                self.put(
                    now + notice_delay,
                    PH_ARRIVE,
                    "loss_notice_V",
                    {"token": token},
                )

            return

        if kind == "return_depart":
            token = p["token"]
            dest = p["dest"]
            amount = F(p["amount"])
            w = self.W[dest]
            rt = w.tokens.get(token)

            if rt is None:
                return

            if w.quarantine >= amount:
                w.quarantine -= amount
                self.transit_return[token] = amount
                rt.state = "RETURNING"

                self.put(
                    now + return_delay,
                    PH_ARRIVE,
                    "return_arrive",
                    {"token": token},
                )
            else:
                self.violations.add("quarantine_underflow")
                self.lost += amount
                rt.state = "LOST_QUARANTINE_UNDERFLOW"
                self.put(
                    now + notice_delay,
                    PH_ARRIVE,
                    "loss_notice_V",
                    {"token": token},
                )

            return

        if kind == "return_arrive":
            token = p["token"]
            amount = self.transit_return.pop(token, F(0))

            if amount == 0:
                return

            t = self.V.tokens.get(token)
            if t is None:
                return

            if t.return_reserved >= amount:
                t.return_reserved -= amount
            else:
                self.violations.add("return_reserve_underflow")

            self.V.stock += amount
            t.state = "RETURNED"
            return

        if kind == "valid_notice_V":
            token = p["token"]
            t = self.V.tokens.get(token)
            if t is None:
                return
            if t.state == "IN_FLIGHT":
                t.state = "DELIVERED"
                t.return_reserved = F(0)
            return

        if kind == "loss_notice_V":
            token = p["token"]
            t = self.V.tokens.get(token)
            if t is None:
                return
            if t.state in ("IN_FLIGHT", "WAIT_ACK"):
                t.state = "LOST"
                t.return_reserved = F(0)
            return

        if kind == "loss_notice_W":
            token = p["token"]
            dest = p["dest"]
            w = self.W[dest]
            rt = w.tokens.get(token)
            if rt is None:
                return
            if rt.state == "RESERVED":
                rt.reserved = F(0)
                rt.state = "LOST"
            return

        if kind == "reject_notice_V":
            token = p["token"]
            t = self.V.tokens.get(token)
            if t is None:
                return
            if t.state == "WAIT_ACK":
                self.V.escrow -= t.phi
                self.V.stock += t.phi
                t.state = "REJECTED"
                t.return_reserved = F(0)
            return

        if kind == "inject":
            amount = F(p["amount"])
            return_reserved = sum(
                (t.return_reserved for t in self.V.tokens.values()),
                F(0),
            )
            used = self.V.stock + self.V.escrow + return_reserved
            available = self.V.cap - used

            if amount <= available:
                self.V.stock += amount
                self.injected += amount
            else:
                # Rejected injection: no resource enters the system.
                self.violations.add("injection_rejected")
            return

        if kind == "loss_event":
            token = p["token"]
            amount = self.transit_out.get(token, F(0))
            if amount == 0:
                return

            t = self.V.tokens.get(token)
            if t is None:
                return

            dest = t.dest
            w = self.W[dest]

            self.transit_out[token] = F(0)
            self.lost += amount
            self.classification[token] = "LOST"

            if defect == "instant_release":
                # Defect: remote receiver loses reservation instantly.
                rt = w.tokens.get(token)
                if rt is not None and rt.state == "RESERVED":
                    rt.reserved = F(0)
                    rt.state = "LOST"
            else:
                self.put(
                    now + notice_delay,
                    PH_ARRIVE,
                    "loss_notice_W",
                    {"token": token, "dest": dest},
                )

            self.put(
                now + notice_delay,
                PH_ARRIVE,
                "loss_notice_V",
                {"token": token},
            )

            return

        if kind == "destroy_node":
            dest = p["dest"]
            w = self.W[dest]
            w.destroyed = True

            # Local reservations at destroyed node are gone locally.
            for rt in w.tokens.values():
                if rt.state == "RESERVED":
                    rt.reserved = F(0)
                    rt.state = "DESTROYED"

            # If physical stock/quarantine existed at destroyed node,
            # count it as lost. Not exercised by the minimal P12 scenario.
            if w.stock > 0 or w.quarantine > 0:
                self.lost += w.stock + w.quarantine
                w.stock = F(0)
                w.quarantine = F(0)

            return

        if kind == "probe":
            probe_kind = p["probe"]
            token = p.get("token")
            dest = p.get("dest")
            label = p["label"]

            value = F(0)

            if probe_kind == "W_reserved":
                w = self.W[dest]
                rt = w.tokens.get(token)
                if rt is not None:
                    value = rt.reserved
            elif probe_kind == "V_inflight":
                t = self.V.tokens.get(token)
                if t is not None and t.state == "IN_FLIGHT":
                    value = t.phi
            elif probe_kind == "V_return_reserved":
                t = self.V.tokens.get(token)
                if t is not None:
                    value = t.return_reserved

            self.probes[label] = value
            return

        raise ValueError(f"unknown event kind: {kind}")

    def summary(self) -> Dict[str, Any]:
        for token in self.V.tokens:
            self.classification.setdefault(token, "NO_EVENT")

        all_sender_terminal = all(
            t.state in TERMINAL_SENDER_STATES
            for t in self.V.tokens.values()
        )

        all_transit_zero = (
            all(v == 0 for v in self.transit_out.values())
            and all(v == 0 for v in self.transit_return.values())
        )

        all_receiver_clean = True
        for w in self.W.values():
            if w.stock < 0 or w.quarantine < 0:
                all_receiver_clean = False
            for rt in w.tokens.values():
                if rt.reserved != 0:
                    all_receiver_clean = False
                if rt.state in ("RESERVED", "QUARANTINED", "RETURNING"):
                    all_receiver_clean = False

        obligations_closed = (
            self.V.escrow == 0
            and all_sender_terminal
            and all_transit_zero
            and all_receiver_clean
        )

        return {
            "final": {
                "V_stock": self.V.stock,
                "V_escrow": self.V.escrow,
                "W1_stock": self.W["W1"].stock,
                "W1_quarantine": self.W["W1"].quarantine,
                "W2_stock": self.W["W2"].stock,
                "W2_quarantine": self.W["W2"].quarantine,
                "transit_out": sum(self.transit_out.values(), F(0)),
                "transit_return": sum(self.transit_return.values(), F(0)),
                "lost": self.lost,
                "consumed": self.consumed,
                "injected": self.injected,
            },
            "classification": dict(self.classification),
            "probes": dict(self.probes),
            "violations": sorted(self.violations),
            "obligations_closed": obligations_closed,
            "event_count": self.event_count,
            "sender_tokens": {
                tid: {
                    "dest": t.dest,
                    "demand": t.demand,
                    "phi": t.phi,
                    "state": t.state,
                    "return_reserved": t.return_reserved,
                }
                for tid, t in self.V.tokens.items()
            },
            "receiver_tokens": {
                dest: {
                    tid: {
                        "reserved": rt.reserved,
                        "deadline": rt.deadline,
                        "state": rt.state,
                    }
                    for tid, rt in w.tokens.items()
                }
                for dest, w in self.W.items()
            },
        }


def run_scenario(**kwargs: Any) -> Dict[str, Any]:
    return Sim(kwargs).run()


def environment() -> Dict[str, Any]:
    def read(path: str) -> Optional[str]:
        try:
            return open(path, "r", encoding="utf-8").read().strip()
        except OSError:
            return None

    try:
        code_hash = hashlib.sha256(open(__file__, "rb").read()).hexdigest()
    except OSError:
        code_hash = None

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in open("/proc/cpuinfo", "r", encoding="utf-8").read().splitlines()
                if line.startswith("model name")
            ),
            None,
        )
        if os.path.exists("/proc/cpuinfo")
        else None,
        "cgroup_cpu_max": read("/sys/fs/cgroup/cpu.max"),
        "cgroup_memory_max": read("/sys/fs/cgroup/memory.max"),
        "cgroup_memory_current": read("/sys/fs/cgroup/memory.current"),
        "libraries": "stdlib only; Fraction; no BLAS; no NumPy",
        "code_sha256": code_hash,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="CHECKS_MULTI.json", help="JSON output path")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    start = time.perf_counter()

    tests: Dict[str, Any] = {}

    # 1. Base successful multi-token delivery.
    base = run_scenario(lease=F(3), ack_wait=F(3))
    tests["base_valid"] = base
    assert base["violations"] == [], base["violations"]
    assert base["obligations_closed"] is True
    assert base["classification"] == {"r1": "VALID", "r2": "VALID"}
    assert base["final"]["V_stock"] == F(0)
    assert base["final"]["W1_stock"] == F(3, 8)
    assert base["final"]["W2_stock"] == F(3, 8)
    assert base["final"]["lost"] == F(0)

    # 2. Permutation invariance for simultaneous requests.
    perm_forward = run_scenario(lease=F(3), ack_wait=F(3), reverse=False)
    perm_reverse = run_scenario(lease=F(3), ack_wait=F(3), reverse=True)
    tests["permutation"] = {
        "forward": perm_forward,
        "reverse": perm_reverse,
    }
    assert perm_forward["classification"] == perm_reverse["classification"]
    assert perm_forward["final"] == perm_reverse["final"]
    assert perm_forward["violations"] == []
    assert perm_reverse["violations"] == []

    # 3. Stale authorized arrival: lease expires before cargo arrival.
    stale = run_scenario(lease=F(3, 2), ack_wait=F(3))
    tests["stale_return"] = stale
    assert stale["violations"] == [], stale["violations"]
    assert stale["obligations_closed"] is True
    assert stale["classification"] == {
        "r1": "STALE_AUTHORIZED",
        "r2": "STALE_AUTHORIZED",
    }
    assert stale["final"]["V_stock"] == F(3, 4)
    assert stale["final"]["W1_stock"] == F(0)
    assert stale["final"]["W2_stock"] == F(0)
    assert stale["final"]["lost"] == F(0)

    # 4. Remote loss: receiver reservation must survive until causal notice.
    loss = run_scenario(
        lease=F(10),
        ack_wait=F(3),
        loss_token="r1",
        loss_time=F(7, 2),
        probes=[
            ("W_reserved", "r1", "W1", F(18, 5)),  # t=3.6
            ("V_inflight", "r1", F(18, 5)),
            ("V_return_reserved", "r1", F(18, 5)),
        ],
    )
    tests["remote_loss"] = loss
    assert loss["violations"] == [], loss["violations"]
    assert loss["obligations_closed"] is True
    assert loss["classification"]["r1"] == "LOST"
    assert loss["classification"]["r2"] == "VALID"
    assert loss["probes"]["W_reserved:r1@W1"] == F(3, 8)
    assert loss["probes"]["V_inflight:r1"] == F(3, 8)
    assert loss["probes"]["V_return_reserved:r1"] == F(3, 8)
    assert loss["final"]["lost"] == F(3, 8)
    assert loss["final"]["W2_stock"] == F(3, 8)

    # 5. Destroy node: sender must not instantly learn remote destruction.
    destroy = run_scenario(
        lease=F(10),
        ack_wait=F(3),
        destroy_dest="W1",
        destroy_time=F(7, 2),
        probes=[
            ("V_inflight", "r1", F(18, 5)),
            ("V_return_reserved", "r1", F(18, 5)),
        ],
    )
    tests["destroy_node"] = destroy
    assert destroy["violations"] == [], destroy["violations"]
    assert destroy["obligations_closed"] is True
    assert destroy["classification"]["r1"] == "DESTROYED_LOST"
    assert destroy["classification"]["r2"] == "VALID"
    assert destroy["probes"]["V_inflight:r1"] == F(3, 8)
    assert destroy["probes"]["V_return_reserved:r1"] == F(3, 8)
    assert destroy["final"]["lost"] == F(3, 8)

    # 6. Negative control N2: independent edge spend.
    n2 = run_scenario(defect="independent_spend")
    tests["N2_independent_spend"] = n2
    assert "nonnegative" in n2["violations"], n2["violations"]

    # 7. Negative control N5: stale cargo disappears.
    n5 = run_scenario(lease=F(3, 2), defect="drop_stale")
    tests["N5_drop_stale"] = n5
    assert "resource_balance" in n5["violations"], n5["violations"]

    # 8. Negative control: stale accepted as valid.
    n_stale_accept = run_scenario(lease=F(3, 2), defect="stale_accept")
    tests["N_stale_accept"] = n_stale_accept
    assert n_stale_accept["classification"]["r1"] == "INVALID_STALE_ACCEPT"
    assert n_stale_accept["classification"]["r2"] == "INVALID_STALE_ACCEPT"

    # 9. Negative control: instant remote release on loss.
    n_instant = run_scenario(
        lease=F(10),
        ack_wait=F(3),
        loss_token="r1",
        loss_time=F(7, 2),
        defect="instant_release",
        probes=[
            ("W_reserved", "r1", "W1", F(18, 5)),
        ],
    )
    tests["N_instant_release"] = n_instant
    assert n_instant["probes"]["W_reserved:r1@W1"] == F(0)

    # 10. Negative control: late ACK causes negative escrow.
    n_late_ack = run_scenario(ack_wait=F(1), defect="late_ack")
    tests["N_late_ack"] = n_late_ack
    assert "nonnegative" in n_late_ack["violations"], n_late_ack["violations"]

    # 11. Negative control: no expiry leaves obligations open.
    n_no_expiry = run_scenario(ack_wait=F(1), lease=F(1), defect="no_expiry")
    tests["N_no_expiry"] = n_no_expiry
    assert n_no_expiry["obligations_closed"] is False

    # 12. Return capacity positive: sender reserves space for expected return.
    ret_pos = run_scenario(
        lease=F(3, 2),
        ack_wait=F(3),
        injections=[(F(16, 5), F(1, 4))],  # t=3.2, inject 1/4
    )
    tests["return_capacity_positive"] = ret_pos
    assert ret_pos["violations"] == [], ret_pos["violations"]
    assert ret_pos["obligations_closed"] is True
    assert ret_pos["final"]["V_stock"] == F(1)
    assert ret_pos["final"]["injected"] == F(1, 4)
    assert ret_pos["classification"] == {
        "r1": "STALE_AUTHORIZED",
        "r2": "STALE_AUTHORIZED",
    }

    # 13. Return capacity negative: no return reservation allows overflow.
    ret_neg = run_scenario(
        lease=F(3, 2),
        ack_wait=F(3),
        injections=[(F(16, 5), F(1))],
        defect="no_return_reserve",
    )
    tests["return_capacity_negative"] = ret_neg
    assert "capacity_V" in ret_neg["violations"], ret_neg["violations"]

    compute_seconds = time.perf_counter() - start
    peak_rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    result = {
        "scope": "R125-multi bounded multi-token pilot; not full P1-P10/N1-N10 suite",
        "environment": environment(),
        "compute_seconds": compute_seconds,
        "peak_rss_kib": peak_rss_kib,
        "tests_passed": True,
        "tests": tests,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, default=str, ensure_ascii=False, indent=2)
        f.write("\n")

    if not args.quiet:
        print(
            json.dumps(
                {
                    "compute_seconds": compute_seconds,
                    "peak_rss_kib": peak_rss_kib,
                    "tests_passed": True,
                    "out": args.out,
                },
                default=str,
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
