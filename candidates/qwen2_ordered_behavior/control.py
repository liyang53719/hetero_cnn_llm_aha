"""Software edge composition, NOT Chisel execution or a block/cycle simulator.

Arithmetic is the existing pinned exact OrderedVectorFold scan/fold/scale.
Retirement is separately modeled to retain the selected final index, with
pre-edge client ports and registered poison. No abstract drain-set is used.
"""
class FeedDebts:
    """The three existing accepted-work bits, not a queue or new hardware state."""
    def __init__(self):
        self.memory = self.local = self.scalar = False
        self.tag = None

    @property
    def any(self):
        return self.memory or self.local or self.scalar

    def tick(self, *, busy, memory_accept=None, memory_response=None,
             local_accept=False, local_response=False,
             scalar_accept=False, scalar_response=False):
        old = self.memory, self.local, self.scalar
        old_tag = self.tag
        if busy and memory_accept is not None:
            self.memory, self.tag = True, memory_accept
        if old[0] and memory_response == old_tag:
            self.memory = False
        if busy and local_accept:
            self.local = True
        if old[1] and local_response:
            self.local = False
        if busy and scalar_accept:
            self.scalar = True
        if old[2] and scalar_response:
            self.scalar = False

    def drain_ready(self, *, finish, poisoned, response_tag=None):
        active = finish and poisoned
        return (active and self.memory and response_tag == self.tag,
                active and self.local, active and self.scalar)


class ScalarBorrower:
    """Existing external-Scalar arbitration; valid alone is not ownership."""
    def __init__(self):
        self.busy = False

    def tick(self, *, idle, poisoned=False, request_valid=False,
             scalar_ready=True, result_valid=False, result_ready=False,
             owner_valid=False, elementwise_exclusive=False):
        available = idle and not poisoned and not self.busy
        request_ready = available and scalar_ready
        owner_ready = (idle and not poisoned and not self.busy
                       and not request_valid and not elementwise_exclusive)
        out = dict(request_ready=request_ready,
                   request_fire=request_ready and request_valid,
                   owner_fire=owner_ready and owner_valid,
                   result_fire=self.busy and result_valid and result_ready)
        if out['request_fire']:
            self.busy = True
        if out['result_fire']:
            self.busy = False
        return out

    @staticmethod
    def validate_profile(*, packed=True, official=True, elementwise_loan=False,
                         head_dim=128, owner=True, external_matrix=True):
        if not packed or head_dim != 128 or not owner or not external_matrix or not official:
            raise ValueError('ordered fold requires the selected packed official profile')
        if elementwise_loan:
            raise ValueError('official profile excludes Elementwise loan')


class OrderedController:
    """One QK group consumer, constructed with existing exact arithmetic model.

    The harness must actually start/issue the client before supplying its held
    tile. This is not an owner prefill simulator: DDR gather, Matrix FMA, SRAM,
    downstream softmax/PV and global owner start are outside this model.
    """
    def __init__(self, client, arithmetic, count, tag=1):
        if not 1 <= count <= 16:
            raise ValueError('tail count')
        self.client, self.arithmetic = client, arithmetic
        self.count, self.tag = count, tag
        self.state, self.owned = 'start', False
        self.poisoned, self.committed = False, False
        self.status, self.selected = None, 0
        self.scores, self.maximum = [], 0xff800000
        self.debts = FeedDebts()
        self.events = []  # observation log only, not hardware resource

    @property
    def finished(self):
        return self.state == 'finish' and not self.owned and not self.debts.any

    def tick(self, inputs):
        """All decisions use pre-edge state. Inputs use StreamClient's schema.

        matrix_fault/address_fault are existing combinational core fault inputs;
        no invented external core abort pin. Client receives registered poison.
        """
        i = dict(inputs)
        old_poison = self.poisoned
        old_state = self.state
        i.update(abort=old_poison,
                 result_ready=self.committed and not old_poison,
                 completion_ready=self.owned and (self.committed or old_poison or self.client.poison))
        if self.state == 'start':
            i.update(start_valid=True, start_tag=self.tag, start_count=self.count, start_pv=False)
        p = self.client.peek(i)
        # Feeder boundary carries actual accepted events, not fabricated drain
        # tokens. This slice does not generate DDR addresses/local requests.
        accepts = (i.get('memory_accept'), i.get('local_accept', False),
                   i.get('scalar_accept', False))
        if (accepts[0] is not None or any(accepts[1:])) and (
                self.state != 'feed' or old_poison or p['reset_required']):
            raise ValueError('accepted feed work outside an enabled feeder phase')
        drain = self.debts.drain_ready(finish=self.state == 'finish',
                                      poisoned=old_poison,
                                      response_tag=i.get('memory_response_tag'))
        feed = self.state == 'feed' and not old_poison
        p['feed_drain_ready'] = drain
        self.debts.tick(busy=self.owned, memory_accept=accepts[0],
                        local_accept=accepts[1], scalar_accept=accepts[2],
                        memory_response=(i.get('memory_response_tag')
                            if i.get('memory_response_valid') and (feed or drain[0]) else None),
                        local_response=bool(i.get('local_response_valid') and (feed or drain[1])),
                        scalar_response=bool(i.get('scalar_response_valid') and (feed or drain[2])))
        active = self.state in ('scan', 'fold', 'scale', 'retire')
        if p['result_valid']:
            if 'tile' not in i or i['tile'].value is not p['result_value']:
                raise ValueError('harness tile is not the live client result')
            if active and self.arithmetic.result is not i['tile']:
                raise ValueError('held result object changed before ACK')
        fault = bool(i.get('matrix_fault') or i.get('address_fault'))
        safe = (self.owned and not old_poison and not p['reset_required']
                and not i.get('port_done_valid', False) and p['result_valid'] and not fault)
        event = None
        if p['start_fire']:
            self.owned, self.state = True, 'feed'
        elif self.state == 'feed' and safe:
            if not self.arithmetic.accept(i['tile'], self.count):
                raise ValueError('arithmetic unexpectedly busy')
            self.state = 'scan'
        elif active and safe:
            if self.state != 'retire':
                self.arithmetic.step()
                self.state = self.arithmetic.state
            elif self.arithmetic.faults[self.selected]:
                self.poisoned, self.status, self.state = True, 'Numerical', 'finish'
                event = ('fault', self.selected)
            else:
                score = self.arithmetic.acc[self.selected]
                self.scores.append(score)
                if self.arithmetic.less(self.maximum, score):
                    self.maximum = score
                event = ('score', self.selected, score)
                if self.selected + 1 == self.count:
                    self.committed, self.state = True, 'next'
                else:
                    self.selected += 1
        if p['completion_fire']:
            self.owned = False
            if self.state == 'next':
                self.state = 'finish'  # slice boundary, not whole block completion
        # Same last-connect ordering: transport/protocol fault, then numerical.
        numerical = event is not None and event[0] == 'fault'
        if i.get('matrix_fault'):
            self.poisoned, self.state, self.status = True, 'finish', 'Protocol'
        if i.get('address_fault') and old_state not in ('finish', 'locked'):
            self.poisoned, self.state, self.status = True, 'finish', 'Bounds'
        if (p['reset_required'] or
                (p['completion_fire'] and p['completion_error'])) and old_state not in ('finish', 'locked'):
            self.poisoned, self.state, self.status = True, 'finish', 'Protocol'
        if numerical:
            self.status = 'Numerical'
        self.client.tick(i)
        self.events.append((event, dict(p)))
        return event, p
