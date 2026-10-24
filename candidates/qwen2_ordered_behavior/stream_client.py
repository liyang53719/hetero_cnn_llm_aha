"""Software edge translation of the pinned PackedAttentionStreamClient.scala.

This is NOT Chisel execution, RTL, a Matrix model, or a hardware-equivalence
proof. Outputs are computed from the pre-edge state; tick then applies the
Scala when statements in source order, including last-connect priority.
The result payload remains the caller's live object and is never copied.
Uninitialized descriptor values are None until start.fire, not invented zeros.
"""
from dataclasses import dataclass, fields
from collections.abc import Mapping


@dataclass(frozen=True)
class StreamInputs:
    start_valid: bool = False
    start_tag: int = 0
    start_pv: bool = False
    start_count: int = 0
    port_group_ready: bool = False
    operands_valid: bool = False
    operands_index: int = 0
    operands_a: object = (0,) * 16
    operands_b: object = (0,) * 256
    port_step_ready: bool = False
    port_result_valid: bool = False
    port_result_context: int = 0
    port_result_last: bool = True
    port_result_error: bool = False
    port_result_value: object = None
    result_ready: bool = False
    port_done_valid: bool = False
    port_done_tag: int = 0
    port_done_error: bool = False
    completion_ready: bool = False
    pause: bool = False
    steps_drained: bool = False
    abort: bool = False


_FIELDS = {field.name for field in fields(StreamInputs)}
_BOOLS = {field.name for field in fields(StreamInputs) if field.type is bool}
_WIDTHS = {'start_tag': 32, 'start_count': 8, 'operands_index': 8,
           'port_result_context': 3, 'port_done_tag': 32}


def _inputs(value):
    if value is None:
        value = StreamInputs()
    elif isinstance(value, Mapping):
        # Permit integration harness inputs without making them client ports.
        value = StreamInputs(**{key: item for key, item in value.items()
                                if key in _FIELDS})
    if not isinstance(value, StreamInputs):
        raise TypeError('expected StreamInputs or a mapping')
    for name in _BOOLS:
        if type(getattr(value, name)) is not bool:
            raise ValueError('non-boolean port: ' + name)
    for name, width in _WIDTHS.items():
        word = getattr(value, name)
        if type(word) is not int or not 0 <= word < 1 << width:
            raise ValueError('port word outside declared width: ' + name)
    # Payloads are opaque references. This control model neither materializes
    # the 4096 result words nor claims to validate Matrix arithmetic/layout.
    return value


class PackedAttentionStreamEdge:
    STATES = ('idle', 'opening', 'issuing', 'awaitResult', 'awaitDone',
              'draining', 'reply', 'locked')

    def __init__(self, enabled=False):
        if type(enabled) is not bool:
            raise ValueError('enabled must be a static Boolean')
        self.enabled = enabled
        self.reset()

    def reset(self):
        """Explicit global-reset observation; not operational abort/drain."""
        self.state, self.index, self.poison = 'idle', 0, False
        self.tag = self.pv = self.count = None

    def peek(self, inputs=None):
        i = _inputs(inputs)
        # Disabled branch mirrors the module's unconditional wire defaults.
        p = dict(state=self.state, index=self.index, poison=self.poison,
                 start_ready=False, operands_ready=False, result_valid=False,
                 result_value=i.port_result_value,
                 result_bits=dict(value=i.port_result_value,
                                  context=i.port_result_context,
                                  last=i.port_result_last,
                                  error=i.port_result_error),
                 port_group_valid=False,
                 port_group_bits=dict(tag=0, opcode=0, slice_mask=0),
                 port_step_valid=False,
                 port_step_bits=dict(a=(0,) * 16, b=(0,) * 256, context=0,
                                     clear=False, last=False,
                                     finish=False, emit=False),
                 port_result_ready=False, port_done_ready=False,
                 port_abort=False, completion_valid=False,
                 completion_tag=0, completion_error=False,
                 pause_granted=False, reset_required=False)
        if self.enabled:
            active = self.state in ('issuing', 'awaitResult', 'awaitDone',
                                    'draining')
            final_index = (None if self.pv is None else
                           (((self.count - 1) & 0xff) if self.pv else 7))
            matching_done = self.tag is not None and i.port_done_tag == self.tag
            bad_result = (i.port_result_context != 0 or
                          not i.port_result_last or i.port_result_error)
            legal_index = i.operands_index == self.index
            can_offer = (self.state == 'issuing' and not i.pause and
                         not i.abort and not self.poison and
                         not i.port_result_valid and not i.port_done_valid)
            last = None if final_index is None else self.index == final_index
            p.update(
                start_ready=self.state == 'idle' and not i.abort,
                port_group_valid=self.state == 'opening' and not i.abort,
                port_group_bits=dict(tag=self.tag,
                    opcode=None if self.pv is None else (0x24 if self.pv else 0x23),
                    slice_mask=None if self.pv is None else (0x0f if self.pv else 0xff)),
                port_step_valid=can_offer and i.operands_valid and legal_index,
                port_step_bits=dict(a=i.operands_a, b=i.operands_b, context=0,
                                   clear=self.index == 0, last=last,
                                   finish=last, emit=last),
                operands_ready=can_offer and (i.port_step_ready if legal_index else True),
                pause_granted=(self.state == 'issuing' and i.pause and
                    i.steps_drained and not i.abort and not self.poison and
                    not i.port_result_valid and not i.port_done_valid),
                result_valid=(self.state == 'awaitResult' and i.port_result_valid
                    and not bad_result and not i.abort and not self.poison),
                port_result_ready=(self.state == 'draining' or
                    (self.state == 'awaitResult' and (bad_result or i.result_ready)
                     and not i.abort)),
                port_done_ready=self.state in ('awaitDone', 'draining') and matching_done,
                port_abort=self.state == 'draining' or (active and i.abort),
                completion_valid=self.state == 'reply',
                completion_tag=self.tag,
                completion_error=self.poison or i.abort,
                reset_required=self.poison)
        p['completion_bits'] = dict(tag=p['completion_tag'],
                                    error=p['completion_error'])
        p.update(start_fire=i.start_valid and p['start_ready'],
                 port_group_fire=p['port_group_valid'] and i.port_group_ready,
                 operands_fire=i.operands_valid and p['operands_ready'],
                 port_step_fire=p['port_step_valid'] and i.port_step_ready,
                 result_fire=p['result_valid'] and i.result_ready,
                 port_result_fire=i.port_result_valid and p['port_result_ready'],
                 port_done_fire=i.port_done_valid and p['port_done_ready'],
                 completion_fire=p['completion_valid'] and i.completion_ready)
        p['success_accepted'] = p['completion_fire'] and not p['completion_error']
        return p

    def tick(self, inputs=None):
        i = _inputs(inputs)
        p = self.peek(i)
        if not self.enabled:
            return p
        # Every condition reads OLD registers. Assigning next_* in the same
        # textual order as Scala preserves its last-connect priority.
        old = self.state
        active = old in ('issuing', 'awaitResult', 'awaitDone', 'draining')
        matching_done = self.tag is not None and i.port_done_tag == self.tag
        bad_result = (i.port_result_context != 0 or
                      not i.port_result_last or i.port_result_error)
        final_index = (None if self.pv is None else
                       (((self.count - 1) & 0xff) if self.pv else 7))
        next_state, next_poison, next_index = old, self.poison, self.index
        next_tag, next_pv, next_count = self.tag, self.pv, self.count

        if p['start_fire']:
            next_tag, next_pv, next_count = i.start_tag, i.start_pv, i.start_count
            next_index = 0
            legal = (i.start_tag != 0 and i.start_count != 0 and
                     i.start_count <= (128 if i.start_pv else 16))
            if legal:
                next_state = 'opening'
            else:
                next_poison, next_state = True, 'reply'
        if p['port_group_fire']:
            next_state = 'issuing'
        if p['operands_fire']:
            if i.operands_index != self.index:
                next_poison, next_state = True, 'draining'
            elif self.index == final_index:
                next_state = 'awaitResult'
            else:
                next_index = (self.index + 1) & 0xff
        if p['port_result_fire'] and old == 'awaitResult':
            if bad_result:
                next_poison, next_state = True, 'draining'
            else:
                next_state = 'awaitDone'
        if p['port_done_fire']:
            if i.port_done_error:
                next_poison = True
            next_state = 'reply'
        if p['completion_fire']:
            next_state = 'locked' if self.poison or i.abort else 'idle'
        if old == 'reply' and i.abort:
            next_poison = True
        if active and ((i.port_result_valid and old not in ('awaitResult', 'draining')) or
                       (i.port_done_valid and (not matching_done or
                                              old not in ('awaitDone', 'draining')))):
            next_poison = True
            next_state = 'reply' if p['port_done_fire'] else 'draining'
        if i.abort and old not in ('idle', 'reply', 'locked'):
            next_poison = True
            next_state = 'reply' if old == 'opening' or p['port_done_fire'] else 'draining'

        self.state, self.poison, self.index = next_state, next_poison, next_index
        self.tag, self.pv, self.count = next_tag, next_pv, next_count
        return p
