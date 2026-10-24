"""Explicit owner-level opt-in; this is not a full-M128 numerical admission."""
from ..attention_packed_owner import hooks
from .schedule import ProductionQk16Schedule
from .ordered_work import StrictLaneOps

STATUS = 'TEMP_NOT_FULL_M128_NUMERICALLY_QUALIFIED'


def install(owner, *, ordered_fold=False, ordered_lanes=None):
    if type(ordered_fold) is not bool or (ordered_fold and type(ordered_lanes) is not StrictLaneOps) or (not ordered_fold and ordered_lanes is not None):
        raise ValueError('explicit ordered mode and strict backend must be selected together')
    from ..official_bf16.owners import OfficialAttentionOwner
    if (type(owner) is not OfficialAttentionOwner or not owner.ports()['job_ready'] or
            getattr(owner, 'packed_schedule', None) is not None or
            owner.matrix.owner is not None or owner.scalar.client is not None):
        raise ValueError('selected scheduling requires the exact idle original owner/services')
    schedule = ProductionQk16Schedule(ordered_fold=ordered_fold)
    if ordered_fold:schedule.ordered_lanes = ordered_lanes
    hooks.install(owner, schedule)
    return schedule


def authorize_full_numeric(*args, **kwargs):
    raise ValueError('new selected scheduling mode requires a separately frozen full-M128 qualification')
