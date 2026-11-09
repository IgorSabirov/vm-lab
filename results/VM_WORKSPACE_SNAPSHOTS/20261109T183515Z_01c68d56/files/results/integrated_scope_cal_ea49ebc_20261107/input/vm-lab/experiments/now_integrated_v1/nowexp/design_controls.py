"""Executable cross-cutting controls of the declared integrated design."""
from .history_controls import compare_foliations,compare_internal_slice,correction_and_selection
from .readout_analysis import reconstruction
from .typed_reactions import exhaustive_v1_control
from .joint_preparation import instrument_distribution


def execute(kind,config,seed):
    if kind=='foliation':
        value=compare_foliations(config,seed)
        passed=value['all_equal']
    elif kind=='internal_slice':
        value={'cuts':[compare_internal_slice(config,seed,n) for n in (1,5,12,24,37)]}
        passed=all(x['continuation_equal'] and x['full_final_state_equal'] for x in value['cuts'])
    elif kind=='boundary_selection':
        value=correction_and_selection(config)
        passed=all(abs(x['preparation_mass']-1)<1e-10 for x in value['arms']) and not value['future_boundary_available_to_controller']
    elif kind=='readout':
        value=reconstruction(config)
        # A badly conditioned instrument is a scientific outcome, not a crashed test.
        passed=all(abs(sum(row[i] for row in value['matrix'])-1)<1e-10 for i in (0,1))
    elif kind=='v1_support':
        value=exhaustive_v1_control();passed=value['all_same_support']
    elif kind=='joint_instrument':
        value={p:instrument_distribution(p) for p in ('bell_x','dephased_x','bell_z','dephased_z')}
        passed=all(abs(sum(x['probability'] for x in v['outcomes'])-1)<1e-10 for v in value.values())
    else:raise ValueError('unknown design control: '+kind)
    return dict(kind=kind,technical_pass=passed,values=value,
                scientific_confirmation=False,finished=True)
