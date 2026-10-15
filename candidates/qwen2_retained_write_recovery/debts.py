"""Strict read-only classification of a retired Down write descriptor.

No numerical execution, descriptor clearing, or physical state mutation.
The original published debt collector is unchanged.
"""


def retained_write_evidence(owner, physical):
    command = getattr(owner, 'accepted_write', None)
    result = dict(retired=False, descriptor_present=command is not None, reason='no_descriptor')
    if command is None:
        return result
    try:
        ports = owner.ports()
        if (owner.state != 'idle' or owner.write_state != 'idle' or owner.error or
                owner.pending is not None or physical.pending is not None or
                ports['write_command'] is not None or ports['write_data'] is not None or
                ports['write_ack_ready'] or ports.get('reset_required', False)):
            result['reason'] = 'live_writer_or_pending'
            return result
        if (type(command.address) is not int or command.address % 64 or
                type(command.beats) is not int or not 1 <= command.beats <= 16):
            result['reason'] = 'invalid_descriptor'
            return result
        size = command.beats * 64
        if command.address // 1024 != (command.address + size - 1) // 1024:
            result['reason'] = 'burst_boundary'
            return result
        matches = [(name, region) for name, region in physical.regions.items()
                   if region['base'] <= command.address and
                   command.address + size <= region['base'] + region['extent']]
        if len(matches) != 1 or matches[0][0] != 'down':
            result['reason'] = 'not_unique_down_region'
            return result
        _, region = matches[0]
        if region['readonly'] or region.get('virtual', False):
            result['reason'] = 'non_writable_region'
            return result
        addresses = set(range(command.address, command.address + size, 64))
        whole = set(range(region['base'], region['base'] + region['extent'], 64))
        if region['extent'] <= 0 or region['extent'] % 64 or region['written'] != whole or region['acked'] != whole:
            result['reason'] = 'incomplete_write_or_ack_coverage'
            return result
        records = [(cmd, ack) for cmd, ack in region['records'] if cmd == command]
        if len(records) != 1:
            result['reason'] = 'non_unique_ack_record'
            return result
        _, ack = records[0]
        if ack.tag != command.tag or ack.error or ack.nbytes != size:
            result['reason'] = 'ack_identity_status_or_bytes'
            return result
        result.update(retired=True, reason='unique_successful_ack_and_idle_writer',
                      address=command.address, bytes=size, tag=command.tag)
    except (AttributeError, KeyError, TypeError, ValueError):
        result['reason'] = 'malformed_evidence'
    return result


def corrected_debts(original_debts, owner, physical):
    """Replace only the descriptor-presence debt; preserve every other debt."""
    result = dict(original_debts)
    evidence = retained_write_evidence(owner, physical)
    result['accepted_write'] = evidence['descriptor_present'] and not evidence['retired']
    return result, evidence


def debts(x, physical, memory):
    """Drop-in read-only collector for a future explicitly reviewed runner."""
    from candidates.qwen2_live_fullblock_model_m128 import statistics
    original = statistics.debts(x, physical, memory)
    return corrected_debts(original, x.owner, physical)[0]
