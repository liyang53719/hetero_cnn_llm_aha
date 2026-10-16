"""Explicit +384-byte six-head panel on the original owner's sole Banks.

Behavioral candidate only. The 96 FP32 words below are an explicitly proposed
new resource, not evidence that legacy denseWeights survive synthesis. The
inherited dv[16] transport is reused; every other field added here is bounded
control metadata. Q/K/V ingress placement and external output writes remain
unmodeled. Full-line bank traffic uses the opt-in scratch route, not new ports.
"""
from dataclasses import dataclass

from ..attention_bank_m128.storage import Scratch as FrozenScratch
from ..attention_bank_scratch.storage import Context, address, valid_context
from ..attention_bank_scratch.port import Key, Request, uint


PANEL_RESOURCE_LEDGER = {
    'scope': 'PROPOSED_BEHAVIORAL_PLUS_384B_PANEL',
    'panel_words': 96,
    'panel_word_bits': 32,
    'panel_payload_bits': 3072,
    'panel_payload_bytes': 384,
    'inherited_transport_words': 16,
    'new_transport_words': 0,
    'additional_payload_words': 0,
    'new_v_stage_words': 0,
    'v_placement_verified': False,
    'legacy_dense_weights_retention_verified': False,
    'physical_register_inventory_verified': False,
    'register_mux_and_control_delta_unmeasured': True,
    'macs_per_cycle_denominator': 4096,
}


@dataclass(frozen=True)
class PanelTag:
    context: Context
    first: int
    count: int
    plane: str


def _all_ready(*flags):
    return all(flag is True for flag in flags)


class Scratch(FrozenScratch):
    """Exclusive whole-job register lease plus a separately tagged 96-word panel.

    Only matching, clean bank ACKs publish head-valid bits and write prefixes.
    Softmax replaces consumed scores in place. PV retains a panel until every
    accepted key step has drained; there is no normalized-probability writeback.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.panel_words = [0] * 96
        self.resource_ledger = dict(PANEL_RESOURCE_LEDGER)
        self.lease_active = False
        self.phase = 'idle'
        self.panel_tag = None
        self.panel_load_valid = 0  # six head-valid bits, never payload
        self.panel_commit_valid = 0
        self.panel_key = 0
        self.selected_key = None
        self.softmax_first = 0
        self.pv_first = 0
        self.pv_retired = 0
        self._route = None  # one admitted full-line route; control only

    def _bank_drained(self):
        return self.active is None and self.staging is None and self.parent.raw.drained

    def _invalidate_panel(self):
        # Invalidating a view does not allocate or clear another payload array.
        self.panel_tag = None
        self.panel_load_valid = 0
        self.panel_commit_valid = 0
        self.panel_key = 0
        self.selected_key = None

    def require(self, context):
        super().require(context)
        if not self.lease_active or self.parent.raw.owner != self.owner_id:
            raise ValueError('panel register lease missing')
        if self.abort_requested:
            raise ValueError('panel aborted')

    def acquire(self, *, matrix_drained=True, scalar_drained=True, joined_drained=True):
        if self.lease_active or not _all_ready(matrix_drained, scalar_drained, joined_drained):
            raise ValueError('register lease requires all compute debts drained')
        super().acquire()
        self.lease_active = True
        self.phase = 'ready'

    def begin(self, query, kv_head, keys):
        if not self.lease_active or self.phase not in ('ready', 'complete') or self.panel_tag is not None:
            raise ValueError('previous panel context not retired')
        context = super().begin(query, kv_head, keys)
        self.phase = 'qk'
        self.softmax_first = self.pv_first = self.pv_retired = 0
        self._invalidate_panel()
        return context

    def legacy_clear(self):
        """Model the old full-vector clear hazard, including phase/request gaps."""
        if self.lease_active or not self._bank_drained():
            raise ValueError('whole-vector clear denied during register lease')
        self.panel_words[:] = [0] * 96
        self._invalidate_panel()

    def foreign_borrower_allowed(self):
        return (not self.lease_active and self._bank_drained() and
                not self.parent.poison and not self.parent.raw.poison)

    def transfer(self, context, line, *, write=False, data=0):
        """Serialize a permitted full beat; dv capture precedes its matching ACK.

        Additional ACK-edge context/abort checks close the publication window
        between the inherited edge callback and a caller's validity update.
        """
        self.require(context)
        if (self._route != (line, write) or type(line) is not int or
                not 4096 <= line < 4192 or type(write) is not bool or not uint(data, 512)):
            raise ValueError('unrouted panel bank transfer')
        if not self._bank_drained():
            raise ValueError('scratch transaction debt')
        if not write and line not in self.initialized:
            raise ValueError('unwritten scratch beat')
        if self.tag == 0xffffffff:
            raise ValueError('tag exhaustion')
        self.tag += 1
        key = Key(self.owner_id, self.tag, line, write)
        self.active = (context, key)
        if not self.tick(request=Request(key, data))['accepted']:
            self.active = None
            raise ValueError('scratch request rejected')
        self.counts['write_requests' if write else 'read_requests'] += 1
        self.tick()  # synchronous bank capture; cannot ACK on this edge
        held = self.parent.raw.response
        if held is None or held.key != key:
            raise ValueError('missing scratch response')
        for _ in range(self.stalls):
            self.tick()
            if self.parent.raw.response is not held:
                raise ValueError('scratch response changed')
        if not write:
            self.staging = held.data  # inherited dv[16], not a second panel
        out = self.tick(ack=key)
        if not out['acked']:
            raise ValueError('scratch ACK rejected')
        self.counts['acks'] += 1
        self.active = None
        if (self.abort_requested or self.parent.raw.poison or self.parent.poison or
                context != self.context or not self.lease_active):
            self.staging = None
            raise ValueError('accepted scratch retired poisoned/stale')
        if write:
            self.initialized.add(line)
        return held.data

    def write_score_packet(self, context, head, first, words):
        self.require(context)
        if self.phase != 'qk' or self.panel_tag is not None or self._route is not None:
            raise ValueError('score write outside QK')
        # Validate coordinates before temporarily granting the transfer route.
        line, _ = address('score', head, first)
        self._route = (line, True)
        try:
            super().write_score_packet(context, head, first, words)
        finally:
            self._route = None

    def write_scores(self, *args, **kwargs):
        raise ValueError('panel candidate requires packet score commits')

    def read_word(self, *args, **kwargs):
        raise ValueError('panel candidate requires full-beat panel reads')

    def write_probability(self, *args, **kwargs):
        raise ValueError('panel candidate has no per-word RMW or normalized writeback')

    def qk_complete(self, context, *, matrix_drained, scalar_drained, joined_drained):
        self.require(context)
        if (self.phase != 'qk' or not self._bank_drained() or
                not _all_ready(matrix_drained, scalar_drained, joined_drained) or
                any(prefix != context.keys for prefix in self.score_written)):
            raise ValueError('QK score/Matrix/joined/scalar completion fence')
        self.phase = 'softmax'

    def _load_panel(self, context, first, plane):
        self.require(context)
        phase = 'softmax' if plane == 'score' else 'pv'
        expected = self.softmax_first if plane == 'score' else self.pv_first
        if (self.phase != phase or self.panel_tag is not None or not self._bank_drained() or
                type(first) is not int or first != expected or not 0 <= first < context.keys or first % 16):
            raise ValueError('panel load sequence/overwrite/debt')
        self._invalidate_panel()
        self.panel_tag = PanelTag(context, first, min(16, context.keys-first), plane)
        for head in range(6):
            line, _ = address(plane, head, first)
            self._route = (line, False)
            try:
                self.transfer(context, line)
                # transfer returned only after matching clean ACK; the sole
                # inherited dv beat is copied to its 16 panel destinations.
                for lane in range(16):
                    self.panel_words[16*head+lane] = ((self.staging >> (32*lane)) & 0xffffffff
                                                     if lane < self.panel_tag.count else 0)
                self.panel_load_valid |= 1 << head
                self.counts['panel_load_head_acks'] += 1
            finally:
                self.staging = None
                self._route = None
        self.counts['score_panels_loaded' if plane == 'score' else 'weight_panels_loaded'] += 1

    def load_score_panel(self, context, first):
        self._load_panel(context, first, 'score')

    def _key(self, context, key, plane):
        self.require(context)
        tag = self.panel_tag
        if (tag is None or tag.context != context or tag.plane != plane or self.panel_load_valid != 63 or
                type(key) is not int or key != tag.first+self.panel_key or not tag.first <= key < tag.first+tag.count or
                self.selected_key is not None or not self._bank_drained()):
            raise ValueError('panel key validity/order/debt')
        self.selected_key = key
        return tuple(self.panel_words[16*head+self.panel_key] for head in range(6))

    def read_scores(self, context, key):
        return self._key(context, key, 'score')

    def write_weights(self, context, key, words):
        self.require(context)
        tag = self.panel_tag
        if (self.phase != 'softmax' or tag is None or tag.plane != 'score' or tag.context != context or
                type(key) is not int or key != self.selected_key or key != tag.first+self.panel_key or
                type(words) is not tuple or len(words) != 6 or any(not uint(word, 32) for word in words) or
                not self._bank_drained()):
            raise ValueError('panel weight overwrite/order')
        for head in range(6):
            self.panel_words[16*head+self.panel_key] = words[head]
        self.panel_key += 1
        self.selected_key = None
        self.counts['panel_weight_key_packets'] += 1

    def commit_weight_panel(self, context):
        self.require(context)
        tag = self.panel_tag
        if (self.phase != 'softmax' or tag is None or tag.context != context or tag.plane != 'score' or
                self.panel_load_valid != 63 or self.panel_key != tag.count or self.selected_key is not None or
                self.panel_commit_valid or not self._bank_drained() or
                any(prefix != tag.first for prefix in self.weight_written)):
            raise ValueError('raw weight panel commit fence')
        for head in range(6):
            line, _ = address('prob', head, tag.first)
            # A combinational 16-word store view of the one panel. Tail lanes
            # are zero; there is no bank read and no per-word RMW transport.
            beat = sum(self.panel_words[16*head+lane] << (32*lane) for lane in range(tag.count))
            self._route = (line, True)
            try:
                self.transfer(context, line, write=True, data=beat)
                self.weight_written[head] = tag.first+tag.count
                self.panel_commit_valid |= 1 << head
                self.counts['raw_weight_head_commits'] += 1
            finally:
                self._route = None
        self.softmax_first = tag.first+tag.count
        self.counts['weight_panels_committed'] += 1
        self._invalidate_panel()

    def begin_pv(self, context, *, reciprocal_acked, scalar_drained):
        self.require(context)
        if (self.phase != 'softmax' or self.panel_tag is not None or not self._bank_drained() or
                not _all_ready(reciprocal_acked, scalar_drained) or
                any(prefix != context.keys for prefix in self.weight_written)):
            raise ValueError('raw weights/reciprocal completion fence')
        self.phase = 'pv'

    def load_weight_panel(self, context, first):
        self._load_panel(context, first, 'prob')

    def read_weights(self, context, key):
        return self._key(context, key, 'prob')

    def retire_pv_key(self, context, key, *, matrix_drained):
        self.require(context)
        tag = self.panel_tag
        if (self.phase != 'pv' or tag is None or tag.plane != 'prob' or tag.context != context or
                type(key) is not int or self.selected_key != key or key != self.pv_retired or
                matrix_drained is not True or not self._bank_drained()):
            raise ValueError('PV key accepted-step drain fence')
        self.panel_key += 1
        self.pv_retired += 1
        self.selected_key = None
        if self.panel_key == tag.count:
            self.pv_first = tag.first+tag.count
            self._invalidate_panel()

    def end_context(self, context, *, matrix_drained, scalar_drained, joined_drained, outputs_acked):
        """outputs_acked is the inherited joined-result/output-consumption ACK.

        No external output write transaction is implemented by this model.
        """
        self.require(context)
        if (self.phase != 'pv' or self.panel_tag is not None or self.pv_retired != context.keys or
                not self._bank_drained() or
                not _all_ready(matrix_drained, scalar_drained, joined_drained, outputs_acked)):
            raise ValueError('panel context accepted debt/output retirement fence')
        self.phase = 'complete'

    def abort(self):
        # Invalidate capabilities immediately, but leave accepted bank debt and
        # the raw owner lease intact so the matching response can still drain.
        super().abort()
        self._invalidate_panel()

    def release(self, *, matrix_drained=True, scalar_drained=True, joined_drained=True):
        poisoned = self.abort_requested or self.parent.raw.poison or self.parent.poison
        if (not self.lease_active or not self._bank_drained() or
                not _all_ready(matrix_drained, scalar_drained, joined_drained) or
                (not poisoned and self.phase not in ('ready', 'complete'))):
            raise ValueError('register lease release before context/debt completion')
        super().release()
        self.lease_active = False
        self.phase = 'idle'
        self._invalidate_panel()
