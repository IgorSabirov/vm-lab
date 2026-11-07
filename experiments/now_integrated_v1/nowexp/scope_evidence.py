"""Return each prospective design comparison and ancestor promise to actual evidence."""
def collect(mapping,contrasts,controls,commit,config_digest):
    result={}
    for item in mapping['comparisons']:
        observations=[]
        for name in item.get('contrasts',[]):
            value=contrasts.get(name)
            observations.append(dict(kind='contrast',id=name,complete=bool(value and value['status']!='NOT_EVALUABLE'),
                source_commit=commit,config_digest=config_digest,artifact='METRICS.json',
                mean=None if value is None else value['mean'],
                interpretation='Finite candidate comparison, not independent confirmation of its ancestors.'))
        for name in item.get('controls',[]):
            value=controls.get(name)
            observations.append(dict(kind='control',id=name,complete=bool(value and value['technical_pass']),
                source_commit=commit,config_digest=config_digest,artifact='DESIGN_CONTROLS.json'))
        result[item['id']]=observations
    return dict(source_commit=commit,config_digest=config_digest,comparisons=result,scientific_confirmation=False)


def returns(contracts,contrasts,controls):
    rows=[]
    for promise in contracts['promises']:
        name=promise['evidence'];record=dict(promise)
        control=controls.get(name);contrast=contrasts.get(name)
        if control is None and contrast is None:
            record.update(result_status='NOT_EXECUTED',actual=None)
        elif control is not None:
            record.update(result_status='EXECUTED_WITH_BOUNDARIES',actual=control['values'],
                prediction_verdict='TECHNICAL_CONDITION_MET' if control['technical_pass'] else 'TECHNICAL_CONDITION_FAILED')
        else:
            # An executed comparison is not automatically a supported prediction.
            rule=promise.get('numeric_prediction')
            actual=contrast['mean'];half=contrast['nominal_bounded_95_halfwidth']
            verdict='DESCRIPTIVE_NO_DIRECTIONAL_PREDICTION'
            if rule:
                lo,hi=actual-half,actual+half
                verdict='SUPPORTED' if lo>=rule['lower'] and hi<=rule['upper'] else 'REFUTED' if hi<rule['lower'] or lo>rule['upper'] else 'INCONCLUSIVE'
            record.update(result_status='EXECUTED_WITH_BOUNDARIES',actual=actual,interval=[actual-half,actual+half],prediction_verdict=verdict)
        rows.append(record)
    return dict(promises=rows,changes_to_registry_statuses=False,counts_are_not_scientific_productivity=True)
