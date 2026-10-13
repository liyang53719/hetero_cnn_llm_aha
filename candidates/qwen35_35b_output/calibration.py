"""Schema boundary for an independently frozen actual-norm O calibration."""

def input_record(report):
    p=report.get('input_provenance') if type(report) is dict else None
    if not (type(p) is dict and p.get('stage')=='gated_norm' and
            p.get('actual_owner_output_consumed') is True and
            p.get('reference_input_substitution') is False and
            p.get('all_producer_terminals_successful') is True and
            type(p.get('input')) is dict):
        raise ValueError('O calibration requires nested actual gated_norm input provenance')
    return p['input']
