"""Explicit three-Add left fold on the original two physical FP32 slots.

Only control metadata is added. Inherited tick owns the exact same SRAM
ports, accepted reads, selected response, RMW captures/commits and abort drain.
A sum input remains a sum until an accepted destructive BeginOverwrite revokes
its read capability. No input tag is relabeled as a fresh partial.
"""
from dataclasses import dataclass, field

from ..qwen35_35b_prefill import partial_tiles as base

Control, Read, Write, Response = base.Control, base.Read, base.Write, base.Response
Tag, Overwrite = base.Tag, base.Overwrite
resource_ledger, location = base.resource_ledger, base.location


@dataclass(frozen=True)
class BeginOverwrite(base.BeginOverwrite):
    lhs_phase: str = field(default='partial', kw_only=True)

    def validate(self):
        fields = ('identity', 'ng', 'rows', 'cols', 'lhs_identity', 'rhs_identity',
                  'lhs_slot', 'rhs_slot')
        if (any(type(getattr(self, name)) is not int for name in fields)
                or not all(0 < identity < 1 << 32 for identity in
                           (self.identity, self.lhs_identity, self.rhs_identity))
                or len({self.identity, self.lhs_identity, self.rhs_identity}) != 3
                or not 0 <= self.ng < 1 << 16 or self.ng % 32
                or self.rows not in (16, 128) or self.cols not in (32, 64, 96, 128, 160)
                or (self.lhs_slot, self.rhs_slot) != (0, 1)
                or type(self.lhs_phase) is not str or self.lhs_phase not in ('partial', 'sum')):
            raise ValueError('explicit chained lhs0/rhs1 phases, shape and distinct identities')


@dataclass(frozen=True)
class Lineage:
    """At most seven UInt32 identities, never a tensor or arithmetic result."""
    identity: int
    ng: int
    rows: int
    cols: int
    merges: int
    used_ids: tuple


class ChainedTileBankModel(base.TileBankModel):
    def __init__(self, banks=None):
        super().__init__(banks)
        self.lineage = None

    def _overwrite_error(self, q):
        try:
            if type(q) is not BeginOverwrite:
                return 'explicit chained BeginOverwrite required'
            q.validate()
        except (ValueError, TypeError, AttributeError):
            return 'chained overwrite identity/geometry/phase'
        if self.poison or not self.idle or self.overwrite is not None:
            return 'chained overwrite before bank obligations drained'
        for slot, identity, phase in ((0, q.lhs_identity, q.lhs_phase),
                                      (1, q.rhs_identity, 'partial')):
            tag = self.tags[slot]
            if not (tag.live and tag.sealed and not tag.poisoned and tag.phase == phase
                    and (tag.identity, tag.ng, tag.rows, tag.cols, tag.expected) ==
                    (identity, q.ng, q.rows, q.cols, q.beats)
                    and tag.produced == tag.expected and tag.consumed == 0):
                return 'chained overwrite requires exact sealed unconsumed input leases'
        if q.lhs_phase == 'partial':
            if self.lineage is not None:
                return 'new left fold cannot discard an existing sum lineage'
        else:
            lineage = self.lineage
            if (lineage is None or
                    (lineage.identity, lineage.ng, lineage.rows, lineage.cols) !=
                    (q.lhs_identity, q.ng, q.rows, q.cols) or
                    lineage.merges not in (1, 2)):
                return 'sum lhs is not a current first/second left-fold result'
            if q.identity in lineage.used_ids or q.rhs_identity in lineage.used_ids:
                return 'chained overwrite reuses a consumed partial or sum identity'
        return None

    def accepts_overwrite(self, q):
        """Read-only controller admission check; bank control rechecks at fire."""
        return self._overwrite_error(q) is None

    def _begin_overwrite(self, q):
        if type(q) is base.BeginOverwrite:
            # Upstream QKV/Z retain their exact old partial+partial contract
            # on this same wrapper. They cannot consume a live chained sum.
            if self.lineage is not None:
                self._fault('legacy overwrite cannot discard chained lineage')
                return
            return super()._begin_overwrite(q)
        error = self._overwrite_error(q)
        if error is not None:
            self._fault(error)
            return
        previous = self.lineage
        used = ((q.lhs_identity, q.rhs_identity, q.identity) if previous is None else
                previous.used_ids + (q.rhs_identity, q.identity))
        self.lineage = Lineage(q.identity, q.ng, q.rows, q.cols,
                               1 if previous is None else previous.merges + 1, used)
        self.overwrite = Overwrite(q)
        # Same accepted destructive capability transition as the original
        # two-partial bank. Data remains in place until each real Add RMW.
        self.tags[0] = Tag(q.identity, q.ng, q.rows, q.cols, phase='sum')
        self.tags[1].live = self.tags[1].sealed = False
        self.tags[1].phase = 'rhs'
        self.counters['overwrites'] += 1

    def _control(self, q):
        if isinstance(q, base.BeginOverwrite):
            self._begin_overwrite(q)
            return
        begin = (isinstance(q, base.window.Control) and
                 type(q.op) is int and q.op == 0 and
                 type(q.slot) is int and q.slot in (0, 1))
        if begin and self.lineage is not None and q.slot == 0:
            lhs, rhs = self.tags
            if not (self.lineage.merges == 3 and self.overwrite is None
                    and lhs.phase == 'sum' and lhs.identity == self.lineage.identity
                    and not lhs.live and not lhs.sealed and not lhs.poisoned
                    and lhs.produced == lhs.consumed == lhs.expected
                    and not rhs.live and not rhs.sealed and not rhs.poisoned):
                self._fault('new left fold requires final old sum read/release and free rhs')
                return
        if begin and self.lineage is not None and q.slot == 1:
            if (self.lineage.merges >= 3 or q.identity in self.lineage.used_ids):
                self._fault('fresh rhs identity required before the final third Add')
                return
        super()._control(q)
        if begin and q.slot == 0 and not self.poison:
            # Original begin requires a genuinely free slot. A sealed live
            # sum cannot reach here; normal final read/release must retire it.
            self.lineage = None

    def tick(self, **inputs):
        edge = super().tick(**inputs)
        if edge.get('reset'):
            self.lineage = None
        return edge
