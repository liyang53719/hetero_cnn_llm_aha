"""Explicit owner-level opt-in; this is not a full-M128 numerical admission."""
from ..attention_packed_owner import hooks
from .schedule import ProductionQk16Schedule

STATUS = 'TEMP_NOT_FULL_M128_NUMERICALLY_QUALIFIED'


def install(owner):
    from ..official_bf16.owners import OfficialAttentionOwner
    if (type(owner) is not OfficialAttentionOwner or not owner.ports()['job_ready'] or
            getattr(owner, 'packed_schedule', None) is not None or
            owner.matrix.owner is not None or owner.scalar.client is not None):
        raise ValueError('selected scheduling requires the exact idle original owner/services')
    schedule = ProductionQk16Schedule()
    hooks.install(owner, schedule)
    return schedule


def authorize_full_numeric(*args, **kwargs):
    raise ValueError('new selected scheduling mode requires a separately frozen full-M128 qualification')
