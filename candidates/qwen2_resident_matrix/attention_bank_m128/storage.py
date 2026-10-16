"""Packet score commits on the original owner's sole Banks allocation.

All probability RMW, validity, transport, and addressing remain inherited.
The old whole-row write_scores implementation is unmodified.
"""
from ..attention_bank_scratch.storage import Scratch as FrozenScratch, address, Context, valid_context
from ..attention_bank_scratch.port import uint
from ..attention_bank_multirow.profile import EventSink


class Scratch(FrozenScratch):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.events = EventSink('scratch.events')

    def write_score_packet(self, context, head, first, words):
        self.require(context)
        if (type(head) is not int or not 0 <= head < 6 or
                type(first) is not int or not 0 <= first < context.keys or
                first % 16 or first != self.score_written[head] or
                type(words) is not tuple or len(words) != min(16, context.keys-first) or
                any(not uint(word, 32) for word in words)):
            raise ValueError('score packet sequence')
        beat = sum(word << (32*lane) for lane, word in enumerate(words))
        self.transfer(context, address('score', head, first)[0], write=True, data=beat)
        # transfer checks the matching ACK and poison before returning.
        self.score_written[head] = first+len(words)
