"""Opt-in QK16 fold/scale micro-model, not a block or hardware cycle model.

Inject the existing strict scalar reference. acc models the core's existing
16 words, not an additional result bank. The borrowed live tile is never copied.
"""
class OrderedVectorFold:
    def __init__(self, scalar, finite, fault_type, *, enabled=False):
        self.enabled = enabled
        self.scalar, self.finite, self.fault_type = scalar, finite, fault_type
        self.state = 'idle'
        self.acc = [0] * 16
        self.faults = [False] * 16  # proposed added 16 sticky fault bits
        self.result = None
        self.committed = []  # observation only, represents existing score SRAM
        self.maximum = 0xff800000
        self.fault_key = None
        self.ack = False
        self.debts = set()
        self.steps = 0  # model transitions, NEVER hardware cycles

    @property
    def ready(self):
        return self.enabled and self.state == 'idle'

    def accept(self, result, count, *, valid=True, initial_max=0xff800000):
        if not valid or not self.ready:
            return False
        if type(count) is not int or not 1 <= count <= 16:
            raise ValueError('active key count must be 1..16')
        if not self.finite(initial_max) and initial_max != 0xff800000:
            raise ValueError('initial maximum must be finite or negative infinity')
        self.result, self.count = result, count
        self.acc[:] = [0] * 16
        self.faults[:] = [False] * 16
        self.committed.clear()
        self.maximum = initial_max
        self.fault_key, self.ack = None, False
        self.debts = {'result', 'done', 'response'}
        self.row, self.key, self.state = 0, 0, 'scan'
        return True

    @staticmethod
    def less(a, b):
        # Existing F32.less finite ordering, including equality of signed zero.
        if (a ^ b) >> 31:
            return bool(a >> 31) and bool((a | b) & 0x7fffffff)
        return (a & 0x7fffffff) > (b & 0x7fffffff) if a >> 31 else a < b

    def _op(self, op, a, b=0):
        return self.scalar.op(self.scalar.client, op, a, b, policy='legacy_scalar')

    def step(self, *, retire_ready=True, ack_ready=True, abort=False):
        self.steps += 1
        if abort and self.state not in ('idle', 'drain'):
            self.state = 'drain'
            return None
        if self.state == 'scan':
            # Scan BEFORE fold, matching each old selected key's whole-vector
            # finite guard. Faulting later keys cannot suppress earlier commits.
            for j in range(self.count):
                if not self.finite(self.result.value[self.row][16*j+self.row]):
                    self.faults[j] = True
            self.row += 1
            if self.row == 16:
                self.row, self.state = 0, 'fold'
        elif self.state == 'fold':
            for j in range(self.count):
                if not self.faults[j]:
                    try:
                        self.acc[j] = self._op('add', self.acc[j], self.result.value[self.row][16*j+self.row])
                    except self.fault_type:
                        self.faults[j] = True
            self.row += 1
            if self.row == 16:
                self.state = 'scale'
        elif self.state == 'scale':
            for j in range(self.count):
                if not self.faults[j]:
                    try:
                        dot = self._op('bf', self.acc[j])
                        if not self.finite(dot):
                            raise self.fault_type('nonfinite materialized dot')
                        score = self._op('bf', self._op('mul', dot, 0x3db504f3))
                        if not self.finite(score):
                            raise self.fault_type('nonfinite materialized score')
                        self.acc[j] = score
                    except self.fault_type:
                        self.faults[j] = True
            self.state = 'retire'
        elif self.state == 'retire' and retire_ready:
            if self.faults[self.key]:
                self.fault_key, self.state = self.key, 'drain'
                return ('fault', self.key)
            score = self.acc[self.key]
            self.committed.append(score)
            if self.less(self.maximum, score):
                self.maximum = score
            event = ('score', self.key, score)
            self.key += 1
            if self.key == self.count:
                self.state = 'ack'
            return event
        elif self.state == 'ack' and ack_ready:
            self.ack = True
            self.state = 'drain'
            return ('consumer_ack',)
        return None

    def drain(self, debt):
        """Abstract client boundary only; not a replacement for client abort FSM.

        Success needs final consumer ACK; fault/abort permits the client to drain
        without one. No new job until all three accepted debts are discharged.
        """
        if self.state != 'drain' or debt not in self.debts:
            raise ValueError('unexpected or premature debt retirement')
        self.debts.remove(debt)
        if debt == 'result':
            self.result = None
        if not self.debts:
            self.state = 'idle'
