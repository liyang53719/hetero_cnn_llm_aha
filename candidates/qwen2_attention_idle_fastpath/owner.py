"""Dense-only V1: remove one pure ports snapshot and idle wrapper dispatch.

The original dynamic ports method, Tile arbiter and every enclosing Host edge
remain real calls. No arithmetic, bank-resource, scheduling or observer change.
Only source-bound typed debt-free state and a strictly argument-free tick may
specialize. Diagnostics and construction identities are outside modeled state.
"""
from collections import deque
from weakref import WeakKeyDictionary
from candidates.qwen2_resident_matrix.dense_block_reduce.dense_drain import DenseReductionOwner
from candidates.qwen2_resident_matrix.dense_block_reduce import k_window_model as original

_ORIGINAL_TICK = DenseReductionOwner.tick
_PORTS = DenseReductionOwner.ports
_TILE_TYPE = original.window.TileBankModel
_BANK_TYPE = original.down.Banks
_TILE_TICK = _TILE_TYPE.tick
_BANK_BEGIN = _BANK_TYPE.begin_cycle
_TAG_TYPES = (original.window.tiles.Tag, original.window.Tag)
# Bound descriptor table is initialized after the explicit new class below.
_ABSENT = object()
_BOUND = ()
_BOUND_CODES = ()
_SHADOWS = frozenset(('tick', 'ports', '_read_command', '_write_command', '_write_data'))
_TILE_SHADOWS = frozenset(('tick', 'idle', 'leased'))
_BINDINGS = WeakKeyDictionary()
_REQUIRED = frozenset(('state', 'error', 'drain_poison', 'window_request', 'window_result',
    'drain_request', 'drain_result', 'drain_expected', 'drain_phase', 'lease', 'read_active',
    'a_hold', 'a_rmw_pending', 'pending', 'accepted_write', 'final_value', 'fifo', 'write_state',
    'seed_outstanding', 'seed_hold', 'seed_state', 'restoring', 'group_started', 'group_done', 'clock'))
_TILE_REQUIRED = frozenset(('banks', 'poison', 'pending', 'response', 'tags', 'cycle'))


def diagnostics(owner):
    """Independent experiment diagnostics, never owner attributes/counters."""
    b = _BINDINGS.get(owner)
    return dict(fast=0, fallback=0) if b is None else dict(fast=b[3], fallback=b[4])


class DenseIdleOwnerV1(DenseReductionOwner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _BINDINGS[self] = [self.tiles, self.a_banks, self.b_banks, 0, 0]

    def tick(self, *args, **kwargs):
        b = _BINDINGS.get(self)
        if args or kwargs:
            if b is not None:
                b[4] += 1
            return _ORIGINAL_TICK(self, *args, **kwargs)
        d = self.__dict__
        t = d.get('tiles')
        # Identity/type fences are evaluated before accessing typed model state.
        bound = (type(self) is DenseIdleOwnerV1 and b is not None and
                 t is b[0] and d.get('a_banks') is b[1] and d.get('b_banks') is b[2] and
                 type(t) is _TILE_TYPE and _REQUIRED.issubset(d) and _TILE_REQUIRED.issubset(t.__dict__) and
                 type(b[1]) is _BANK_TYPE and type(b[2]) is _BANK_TYPE and
                 t.banks is b[1] and not _SHADOWS.intersection(d) and
                 not _TILE_SHADOWS.intersection(t.__dict__) and
                 'begin_cycle' not in b[1].__dict__ and 'begin_cycle' not in b[2].__dict__ and
                 all(vars(cls).get(name, _ABSENT) is value for cls, name, value in _BOUND) and
                 all(fn.__code__ is code for fn, code in _BOUND_CODES))
        fast = (not args and not kwargs and bound and
                d.get('enable_dense_drain') is True and d.get('enable_k_window') is True and
                d.get('enable_ffn_window') is True and d.get('enable_ffn_tiles') is True and
                d.get('enable_ffn_drain') is True and
                type(d.get('state')) is str and d['state'] == 'idle' and d.get('error') is None and
                d.get('drain_poison') is False and t.poison is False and
                d.get('window_request') is None and d.get('window_result') is None and
                d.get('drain_request') is None and d.get('drain_result') is None and
                d.get('drain_expected') is None and
                type(d.get('drain_phase')) is str and d['drain_phase'] == 'idle' and
                d.get('lease') is None and t.pending is None and t.response is None and
                type(t.tags) is list and len(t.tags) == 3 and
                all(type(tag) in _TAG_TYPES and tag.live is False for tag in t.tags) and
                d.get('read_active') is None and d.get('a_hold') is None and
                d.get('a_rmw_pending') is None and d.get('pending') is None and
                d.get('accepted_write') is None and d.get('final_value') is None and
                type(d.get('fifo')) is deque and not d['fifo'] and
                type(d.get('write_state')) is str and d['write_state'] == 'idle' and
                d.get('seed_outstanding') is False and d.get('seed_hold') is None and
                type(d.get('seed_state')) is str and d['seed_state'] == 'idle' and
                d.get('restoring') is False and
                type(d.get('group_started')) is bool and type(d.get('group_done')) is bool and
                (not d['group_started'] or d['group_done']) and
                type(d.get('clock')) is int and type(t.cycle) is int)
        if not fast:
            if b is not None:
                b[4] += 1
            return _ORIGINAL_TICK(self, *args, **kwargs)
        b[3] += 1
        p = self.ports()
        e = self.tiles.tick(control=None, write=None, read=None,
                            response_ready=True, owner_quiescent=True,
                            dense_reads=None, dense_writes=None)
        if self.tiles.poison or any(word < 768 for word in e['writes'].values()):
            self.lease = None
        self.clock += 1
        # Existing drain_ready occupies its original p position. Reassigning it
        # preserves dict order just as the outer drain wrapper's dict() does.
        return dict(p, tile=e, window_result_fire=False, window_fire=False,
                    a_reads=e['reads'], a_writes=e['writes'], b_reads={}, b_writes={},
                    read_fire=False, read_command_fire=False, step_fire=False,
                    group_fire=False, result_fire=False, response_fire=False,
                    drain_ready=p['drain_ready'], drain_fire=False, drain_result_fire=False)


# Capture presence AND absence at every MRO level, including the new class.
# Thus a newly added inherited override cannot evade source-identity fences.
_BOUND = tuple((cls, name, vars(cls).get(name, _ABSENT))
    for cls in DenseIdleOwnerV1.__mro__
    for name in ('ports', '_read_command', '_write_command', '_write_data'))
_BOUND += tuple((cls, name, vars(cls).get(name, _ABSENT))
    for cls in _TILE_TYPE.__mro__ for name in ('tick', 'idle', 'leased'))
_BOUND += ((_BANK_TYPE, 'begin_cycle', _BANK_BEGIN),)
_BOUND_CODES = tuple((fn, fn.__code__) for fn in {
    value.fget if isinstance(value, property) else value
    for _, _, value in _BOUND if value is not _ABSENT})
