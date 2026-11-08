"""Finite input and Born-outcome enumeration; floating probabilities stay numerical."""
from dataclasses import replace
from fractions import Fraction
from itertools import product
from .engine import Engine, BranchRequired
from .randomness import exact_histories


def input_distribution(config):
    if config.forced_content is not None:
        return [(list(config.forced_content), Fraction(1))]
    if config.preparation == "independent":
        return [(list(pair), Fraction(1,4)) for pair in product((0,1), repeat=2)]
    if config.preparation.startswith(('bell_','dephased_')):
        from .joint_preparation import instrument_distribution
        return [(x['bits'],Fraction(x['probability'])) for x in instrument_distribution(config.preparation)['outcomes']]
    weights = {}
    for _, pair, weight in exact_histories():
        key = tuple(pair)
        weights[key] = weights.get(key, Fraction(0)) + weight
    return [(list(pair), weight) for pair, weight in sorted(weights.items())]


class FiniteEnumeration:
    """Checkpoint branch boundaries; replay bounded by max_events. No mass cutoff."""
    def __init__(self, config, saved=None, max_nodes=4096):
        self.config, self.max_nodes = config, max_nodes
        self.pending = [dict(content=pair, input_weight=str(weight), weight=float(weight), decisions={})
                        for pair,weight in reversed(input_distribution(config))]
        for branch in self.pending:
            branch['rational_weight']=branch['input_weight'] if config.memory=='classical' and config.preparation in ('correlated','independent') else None
        self.leaves, self.nodes, self.executed_events = [], 0, 0
        self.trace = None
        if saved is not None:
            self.pending, self.leaves = saved["pending"], saved["leaves"]
            self.nodes, self.executed_events = saved["nodes"], saved["executed_events"]
            self.trace = saved.get("trace")

    def advance(self):
        if self.nodes >= self.max_nodes:
            raise RuntimeError("finite enumeration node cap reached; no truncation allowed")
        branch = self.pending.pop()
        engine = Engine(replace(self.config, forced_content=branch["content"]), 0,
                        decisions=branch["decisions"])
        try:
            result = engine.run()
        except BranchRequired as split:
            for choice, probability in reversed(split.options):
                self.pending.append(dict(branch, weight=branch["weight"]*probability,
                    rational_weight=None if branch.get('rational_weight') is None else str(Fraction(branch['rational_weight'])*Fraction(str(probability))),
                    decisions=dict(branch["decisions"], **{split.address:choice})))
        else:
            self.leaves.append(dict(weight=branch["weight"], input_weight=branch["input_weight"],
                                    rational_weight=branch.get('rational_weight'),
                                    decisions=branch["decisions"], result=result))
            if self.trace is None or result["all_functional"]:
                self.trace = engine.snapshot()
        self.nodes += 1
        self.executed_events += engine.processed

    def snapshot(self):
        return dict(pending=self.pending, leaves=self.leaves, nodes=self.nodes,
                    executed_events=self.executed_events, trace=self.trace)

    def result(self):
        if self.pending:
            raise ValueError("enumeration unfinished")
        mass = sum(row["weight"] for row in self.leaves)
        if abs(mass-1) > self.config.thresholds["density_trace_tolerance"]:
            raise ArithmeticError("enumeration probability mass not normalized")
        return dict(outcomes=self.leaves, probability_mass=mass,
                    enumeration_nodes=self.nodes, executed_events=self.executed_events,
                    rational_arithmetic_complete=all(r['rational_weight'] is not None for r in self.leaves),
                    numerical_probabilities=self.config.memory != "classical" or self.config.preparation.startswith(('bell_','dephased_')))
