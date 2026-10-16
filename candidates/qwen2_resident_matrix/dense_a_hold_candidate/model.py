"""Default-off A operand reuse on the frozen cold Down/FFN-window owner.

This is an executable bank/control candidate, not RTL or an arithmetic oracle.
Only the operand gather changes. Existing DMA, B layout, seed, result and tile
controllers remain inherited. A synchronous response has a reserved FIFO slot;
the Python pending word tuple represents its RAM wire, not extra payload SRAM.
"""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def check_sources():
    sources = json.loads((HERE / 'source_pins.json').read_text())['sources']
    for name, digest in sources.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError('frozen A-hold source drift: ' + name)
    return sources


check_sources()
_path = HERE.parent / 'ffn_window/model.py'
_spec = importlib.util.spec_from_file_location('a_hold_frozen_window', _path)
window = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = window
_spec.loader.exec_module(window)
down = window.down
Job, PrefixWorkspace = down.Job, down.PrefixWorkspace
ReadBeat, MatrixResult, MatrixDone = down.ReadBeat, down.MatrixResult, down.MatrixDone
WriteAck, SeedAck = down.WriteAck, down.SeedAck
FfnWindowRequest = window.FfnWindowRequest


class DenseAHoldModel(window.FfnWindowOwnerModel):
    """Queue4 baseline, or Queue3 plus one 128xBF16 (256 B) hold.

    The hold is filled only on context0's synchronous response. Subsequent
    contexts issue B-only reads, then copy the hold into their PRIVATE FIFO
    packets at response capture. Last-context capture releases the hold even
    if older packets remain stalled. No packet points at mutable shared A.

    Local invalidation during accepted work poisons and drains that work.
    Only a coordinated backend reset permits recovery from a fault. Neither
    a local reset nor a generation change erases accepted physical debt.
    """
    def __init__(self, workspace=None, *, enable_a_hold=False,
                 enable_ffn_window=False, enable_ffn_tiles=False):
        if type(enable_a_hold) is not bool:
            raise ValueError('enable_a_hold must be an explicit Boolean')
        self.enable_a_hold = enable_a_hold
        self.FIFO_DEPTH = 3 if enable_a_hold else 4
        super().__init__(workspace, enable_ffn_window=enable_ffn_window,
                         enable_ffn_tiles=enable_ffn_tiles)

    def _reset(self):
        super()._reset()
        self.hold_words = self.hold_key = None
        self.hold_generation = 0
        self.hold_counts = Counter()

    def _invalidate_hold(self, reason, *, advance=False):
        if not self.enable_a_hold:
            return
        self.hold_words = self.hold_key = None
        self.hold_counts['invalidate_' + reason] += 1
        if advance:
            if self.hold_generation == 0xffffffff:
                self._fault('A-hold generation exhausted; coordinated reset required')
                return
            self.hold_generation += 1

    def _fault(self, reason):
        self._invalidate_hold('fault')
        super()._fault(reason)

    def _window(self):
        self._invalidate_hold('group_or_a_fence', advance=True)
        if self.error:
            return
        super()._window()

    def _begin_execute(self):
        self._invalidate_hold('window_execute', advance=True)
        if self.error:
            return
        super()._begin_execute()

    def _issue_read(self):
        if not self.enable_a_hold:
            return super()._issue_read()
        # The frozen scheduler can compute can_issue before a DMA fault on
        # this edge. Never turn that stale decision into a new RAM request.
        if self.error:
            return
        k, context = self.issue_k, self.issue_context
        key = (self.hold_generation, k)
        if context and (self.hold_key != key or self.hold_words is None):
            self._fault('B-only gather without matching live A hold')
            return
        if context == 0:
            local_k = k - self.chunk_start
            awords = tuple(self.a_banks.read((local_k & 15) ^ group,
                          (local_k // 16) * 8 + group) for group in range(8))
            self.hold_counts['a_gathers'] += 1
        else:
            awords = None
            self.hold_counts['b_only_gathers'] += 1
        half = (k // 128) & 1
        bwords = tuple(self.b_banks.read(*down.b_address(half, k, context, nh))
                       for nh in range(2))
        self.pending = (k, context, awords, bwords, key)
        self.hold_counts['operand_reads'] += 1
        self.issue_context += 1
        if self.issue_context == self.contexts:
            self.issue_context = 0
            self.issue_k += 1
            if self.issue_k % 128 == 0 or self.issue_k == self.chunk_end:
                self.ready[half] = False

    def _operand_response(self, pending):
        if not self.enable_a_hold:
            return super()._operand_response(pending)
        k, context, awords, bwords, key = pending
        # A response accepted before a same-edge fault must still retire its
        # reserved credit, but may not resurrect a hold or feed Matrix.
        bad = self.error is not None or key != (self.hold_generation, k)
        if context == 0:
            if awords is None or len(awords) != 8:
                bad = True
            if not bad:
                self.hold_words, self.hold_key = awords, key
                self.hold_counts['hold_captures'] += 1
        elif self.hold_key != key or self.hold_words is None:
            bad = True
        if bad:
            self._fault('invalidated or mismatched synchronous A-hold response')
            # This is a discarded protocol placeholder, never a Matrix input.
            # The frozen drain removes one accepted FIFO entry each edge.
            awords = (0,) * 8
        elif context:
            awords = self.hold_words
            self.hold_counts['hold_uses'] += 1
        packet = super()._operand_response((k, context, awords, bwords))
        if context + 1 == self.contexts:
            self._invalidate_hold('last_context_capture')
        return packet

    def tick(self, **inputs):
        if not self.enable_a_hold:
            return super().tick(**inputs)
        before = self.state
        reserved = len(self.fifo) + int(self.pending is not None)
        if reserved > self.FIFO_DEPTH:
            raise RuntimeError('reserved synchronous response exceeds Queue3')
        if inputs.get('invalidate_lease'):
            self._invalidate_hold('lease')
            if before not in ('idle', 'finish', 'locked'):
                # Invalidate is not permission to reread changed A in the
                # middle of an already accepted ordered Matrix group.
                inputs = dict(inputs, abort=True)
        if inputs.get('abort') or inputs.get('local_reset'):
            self._invalidate_hold('abort_or_local_reset')
        reads_before = self.hold_counts['operand_reads']
        event = super().tick(**inputs)
        if inputs.get('coordinated_reset'):
            return event
        # A job's setup edge cannot issue an operand read. Window admission
        # similarly precedes tile begin, A load/fence and _begin_execute.
        if event.get('window_fire') or (before == 'idle' and self.state == 'clear'):
            self._invalidate_hold('setup', advance=True)
        elif before == 'execute' and self.state == 'clear':
            self._invalidate_hold('chunk', advance=True)
        if self.error:
            self._invalidate_hold('poisoned_edge')
        # Existing DMA A-load and clear paths own their bank edges exclusively.
        # Upper FFN tile writes do not invalidate a disjoint lower input lease.
        if self.job is not None:
            input_limit = (self.chunk_end - self.chunk_start) // 16 * 8
            if any(word < input_limit for word in event.get('a_writes', {}).values()):
                self._invalidate_hold('input_write')
        event['operand_read'] = self.hold_counts['operand_reads'] != reads_before
        event['hold_valid_after'] = self.hold_words is not None
        event['hold_generation_after'] = self.hold_generation
        event['reserved_after'] = len(self.fifo) + int(self.pending is not None)
        if event['reserved_after'] > 3:
            raise RuntimeError('Queue3 response credit was not reserved')
        return event
