"""Given flat 1+1 geometry. Contact gates do not edit this geometry."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Worldline:
    x0: float
    v: float = 0.0

    def __post_init__(self):
        if not math.isfinite(self.x0) or not math.isfinite(self.v) or abs(self.v) >= 1:
            raise ValueError("timelike inertial worldline required")

    @property
    def gamma(self):
        return 1 / math.sqrt(1 - self.v**2)

    def x(self, t):
        return self.x0 + self.v * t

    def elapsed(self, t0, t1):
        return (t1 - t0) / self.gamma

    def after(self, t, proper_delay):
        if proper_delay < 0:
            raise ValueError("negative delay")
        return t + self.gamma * proper_delay


def reception(sender, receiver, sent_at, speed=1.0, receiver_delay=0.0, tolerance=None):
    """Earliest intersection with either carrier ray, then receiver-local delay."""
    if not 0 < speed <= 1 or receiver_delay < 0:
        raise ValueError("invalid carrier")
    if tolerance is None:
        from .state import scientific_thresholds
        tolerance = scientific_thresholds()["causal_interval_tolerance"]
    xs = sender.x(sent_at)
    candidates = []
    for direction in (-1, 1):
        velocity = direction * speed
        if abs(velocity - receiver.v) < tolerance:
            continue
        t = (receiver.x0 - xs + velocity * sent_at) / (velocity - receiver.v)
        if t >= sent_at - tolerance:
            candidates.append(max(t, sent_at))
    if not candidates:
        raise ValueError("carrier cannot intercept receiver")
    return receiver.after(min(candidates), receiver_delay)


def boost(t, x, beta):
    g = 1 / math.sqrt(1 - beta**2)
    return g * (t - beta*x), g * (x - beta*t)


def rational_boost(t, x, beta, gamma):
    """Caller provides rational beta,gamma satisfying gamma²(1-beta²)=1."""
    if gamma*gamma*(1-beta*beta) != 1:
        raise ValueError("not a rational Lorentz boost")
    return gamma*(t-beta*x), gamma*(x-beta*t)
