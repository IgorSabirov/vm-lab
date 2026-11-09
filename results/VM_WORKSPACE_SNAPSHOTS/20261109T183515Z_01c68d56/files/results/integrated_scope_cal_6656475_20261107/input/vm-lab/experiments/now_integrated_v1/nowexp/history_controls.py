"""Whole-history controls using the same engine, resources and read instruments.

Coordinate reordering is not a change of physical worldlines. Conditioning on
a final event is an analysis operation, never a controller input.
"""
import copy
from dataclasses import replace
import math

from .engine import Engine, canonical_hash
from .kinematics import boost
from .enumeration import FiniteEnumeration


class FoliatedEngine(Engine):
    def __init__(self, config, seed, beta=0., decisions=None):
        if not math.isfinite(beta) or abs(beta)>=1:
            raise ValueError('timelike coordinate frame required')
        self.frame_beta=beta
        super().__init__(config,seed,decisions)

    def pop_event(self):
        def key(event):
            t=event['t'];x=self.lines[event['owner']].x(t)
            return boost(t,x,self.frame_beta)[0],event['owner'],event['phase'],event['id']
        event=min(self.queue,key=key)
        self.queue.remove(event)
        return event

    def snapshot(self):
        data=super().snapshot();data['coordinate_frame_beta']=self.frame_beta
        return data

    @classmethod
    def restore(cls,data):
        obj=Engine.restore(data)
        obj.__class__=cls
        obj.frame_beta=data['coordinate_frame_beta']
        return obj


def local_event_projection(engine):
    """Observer-local records; no global order or intermediate global totals."""
    answer={name:[] for name in engine.lines}
    for item in engine.log:
        if item['kind']!='event':continue
        event=item['event'];owner=event['owner']
        answer[owner].append(dict(id=event['id'],kind=event['kind'],
            proper=event['t']/engine.lines[owner].gamma,
            parents=sorted(event['parents']),local=copy.deepcopy(item['local'])))
    return answer


def compare_foliations(config,seed,betas=(-.8,-.3,0.,.3,.8)):
    results=[];reference=None
    for beta in betas:
        engine=FoliatedEngine(config,seed,beta)
        outcome=engine.run()
        local=local_event_projection(engine)
        physical=dict(profile=outcome['profile'],balance=outcome['material_and_credit_balance'],
                      local=local,source_alive=engine.source_alive)
        fingerprint=canonical_hash(physical)
        if reference is None:reference=fingerprint
        results.append(dict(beta=beta,local_and_final_hash=fingerprint,
                            equal_to_reference=fingerprint==reference,
                            event_order=[x['event']['id'] for x in engine.log if x['kind']=='event']))
    return dict(all_equal=all(x['equal_to_reference'] for x in results),frames=results,
                interpretation='Same physical worldlines, local clocks, interventions and event-indexed randomness; changed coordinate-time scheduler.')


def compare_internal_slice(config,seed,cut_events):
    engine=Engine(config,seed);engine.run(stop_after=cut_events)
    checkpoint=engine.snapshot()
    first=engine.run()
    resumed=Engine.restore(checkpoint);second=resumed.run()
    return dict(cut_events=cut_events,checkpoint_hash=canonical_hash(checkpoint),
        continuation_equal=canonical_hash(first)==canonical_hash(second),
        full_final_state_equal=canonical_hash(engine.snapshot())==canonical_hash(resumed.snapshot()),
        history_probability_inferred=False,
        interpretation='Equality conditional on the same complete cut; no probability or actual origin of that cut is inferred.')


def correction_and_selection(config,max_nodes=4096):
    """A shared preparation law, K intervention, and explicitly normalized selection."""
    arms=[]
    for enabled in (False,True):
        job=FiniteEnumeration(replace(config,corrector=enabled),max_nodes=max_nodes)
        while job.pending:job.advance()
        leaves=job.result()['outcomes']
        denominator=sum(x['weight'] for x in leaves if x['result']['final_function'])
        numerator=sum(x['weight']*x['result']['parent_function'] for x in leaves
                      if x['result']['final_function'])
        unconditional_parent=sum(x['weight']*x['result']['parent_function'] for x in leaves)
        arms.append(dict(corrector=enabled,preparation_mass=sum(x['weight'] for x in leaves),
            future_event_mass=denominator,parent_and_future_mass=numerator,
            parent_given_future=None if denominator==0 else numerator/denominator,
            unconditional_parent=unconditional_parent,
            unconditional_future=denominator,nodes=job.nodes,
            selection_changes_controller=False))
    return dict(arms=arms,causal_future_effect=arms[1]['unconditional_future']-arms[0]['unconditional_future'],
        future_boundary_available_to_controller=False,
        interpretation='Postselection reweights completed histories with its denominator; only K changes the executed local intervention. Not a physical future-to-past mechanism or PW realization.')
