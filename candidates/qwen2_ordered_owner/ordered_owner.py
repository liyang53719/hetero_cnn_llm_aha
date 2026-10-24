"""Opt-in ordered work hooks for the original software Attention owner/client.

No new arithmetic service, Matrix backend, cache or result tile. This module
advances one work step from actual owner.tick, not by swallowing generator yield.
"""
from .ordered_work import OrderedFoldWork, OrderedFoldAdapter, StrictLaneOps
from ..ffn_public.prefix_owners import PrefixFault


def initialize(owner):
    owner.ordered_work = None
    lanes = getattr(owner.packed_schedule, 'ordered_lanes', None)
    enabled = bool(getattr(owner.packed_schedule, 'ordered_fold', False))
    if enabled and type(lanes) is not StrictLaneOps:
        raise ValueError('ordered owner requires an explicit strict lane backend')
    owner.ordered_adapter = OrderedFoldAdapter(lanes) if enabled else None


def action(owner, work):
    if type(work) is not OrderedFoldWork:
        return False
    if owner.ordered_adapter is None:
        raise PrefixFault('Protocol', 'ordered work without opt-in owner adapter')
    if owner.ordered_work is not None and owner.ordered_work is not work:
        raise PrefixFault('Protocol', 'ordered work replacement before retirement')
    check_held(owner, work)
    owner.ordered_work, owner.state = work, 'ordered_fold'
    return True


def check_held(owner, work):
    if type(work) is not OrderedFoldWork:
        raise PrefixFault('Protocol', 'missing ordered work')
    client = owner.matrix_client
    if (client is None or client.active is not client.packed or
            client.packed.state != 'held' or not client.packed._delivered or
            client.write_debts or client.packed.poison or owner.matrix.reset_required or
            owner.ordered_adapter.lanes is not owner.packed_schedule.ordered_lanes or
            client.held_tag != work.result.tag or
            client.packed._held is not work.result.service_result or
            owner.matrix.result is not work.result.service_result or
            work.result.value is not owner.matrix.result.value):
        raise PrefixFault('Protocol', 'ordered work lost the actual held client result')


def fault(owner):
    work = getattr(owner, 'ordered_work', None)
    if work is not None:
        owner.ordered_adapter.tick(work, abort=True)
        owner.ordered_work = None


def pre_client(owner, ports, done_override):
    """Observe actual pre-edge service terminal before any client/work action.

    done_override only replaces an existing terminal payload in PackedClient;
    it is NOT a valid signal when service.done is absent. This hook does not
    clear a foreign terminal or invent a matching debt retirement.
    """
    if owner.ordered_adapter is None or owner.state in ('drain','finish','locked'):
        return
    client = owner.matrix_client
    if client is None or client.active is not client.packed or not client.packed.active:
        return
    done = owner.matrix.done
    if done is not None:
        seen = done if done_override is None else done_override
        tag = client.packed.tag
        matching = (getattr(seen,'tag',None),getattr(seen,'ticket',None),getattr(seen,'epoch',None)) == (tag.group,tag.ticket,tag.epoch)
        if client.packed.state != 'wait_done' or owner.matrix.result is not None or not matching:
            owner._fault('Protocol', 'unexpected or foreign ordered QK terminal')
            ports.update(memory=None, matrix=None, response=None)
            return
    work = owner.ordered_work
    if work is not None:
        try:
            check_held(owner, work)
        except PrefixFault as error:
            owner._fault(error.status, error.detail)
            ports.update(memory=None, matrix=None, response=None)


def result_error(owner, result):
    """Fail before resuming generator on errored client result/retirement."""
    if (owner.ordered_adapter is None or owner.matrix_client is None or
            owner.matrix_client.active is not owner.matrix_client.packed):
        return False
    if owner.poison or getattr(result,'error',False) or owner.matrix_client.ports()['reset_required']:
        owner._fault('Protocol','ordered client returned an error before generator resume')
        return True
    return False


def post_client(owner, ports):
    # Both pre-edge and current state must agree: no same-edge work creation,
    # fault/reset, accepted response or client transition can sneak a score in.
    if ports['state'] != 'ordered_fold' or owner.state != 'ordered_fold' or owner.poison:
        return
    work = owner.ordered_work
    try:
        check_held(owner, work)
        if owner.matrix.reset_required or owner.matrix_client.ports()['reset_required']:
            owner._fault('Protocol', 'ordered client quarantined')
            return
        response = owner.ordered_adapter.tick(work, ready=True)
        if response is not None:
            owner.ordered_work = None
            owner._advance(response)
    except PrefixFault as error:
        owner._fault(error.status, error.detail)
    except ValueError as error:
        owner._fault('Protocol', str(error))
