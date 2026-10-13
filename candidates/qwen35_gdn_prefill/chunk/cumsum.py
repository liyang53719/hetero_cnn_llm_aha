"""Bounded software cumsum on existing FP32 Add, no FP64 candidate math.

At most 64 nonpositive normal FP32/zero inputs, exponent <=120 and span<=18.
The second TwoSum residual must be zero. Unsupported inputs fail closed.
Thirteen one-lane Add issues per accepted input; no production Chisel binding.
"""
from candidates.qwen35_gdn_prefill.rms_owner import ArithmeticFault

LEGACY_CUMSUM = 'legacy_ascending_fp32'
GUARDED_CUMSUM = '35b_guarded_two_sum_fp32_span18_64'

class CumsumDomainFault(ArithmeticFault):
    def __init__(self, reason, index, word, **detail):
        super().__init__('bounded cumsum: ' + reason)
        self.diagnostic = dict(resource='Vector16', operation=GUARDED_CUMSUM,
            reason=reason, index=index, input_word=word, **detail)

class GuardedCumsum:
    """One active head/chunk; create afresh for every chunk or transaction.

    hi+lo is exact after every accepted update. The 48-bit grid bound makes
    pinned CPU binary64 accumulation exact too. Emitted FP32 never feeds back.
    Only two persistent numerical words; metadata and temporary slots still
    need explicit hardware allocation/handshake proof.
    """
    def __init__(self, add):
        self.add = add
        self.hi = self.lo = self.count = 0
        self.emin = self.emax = None
        self.poison = False

    def _reject(self, reason, word, **detail):
        self.poison = True
        raise CumsumDomainFault(reason, self.count, word, **detail)

    def _two_sum(self, a, b):
        s = self.add(a, b)
        bp = self.add(s, a ^ 0x80000000)
        ap = self.add(s, bp ^ 0x80000000)
        br = self.add(b, bp ^ 0x80000000)
        ar = self.add(a, ap ^ 0x80000000)
        return s, self.add(ar, br)

    def step(self, x):
        if self.poison:
            self._reject('poisoned_until_new_chunk', x)
        if type(x) is not int or not 0 <= x < 1 << 32:
            self._reject('not_fp32_word', x)
        if self.count >= 64:
            self._reject('more_than_64_terms', x)
        mag = x & 0x7fffffff
        exponent = (x >> 23) & 255
        emin, emax = self.emin, self.emax
        if mag:
            if not x >> 31 or not 1 <= exponent <= 247:
                self._reject('nonpositive_normal_emax120_or_zero_required', x)
            emin = exponent if emin is None else min(emin, exponent)
            emax = exponent if emax is None else max(emax, exponent)
            if emax - emin > 18:
                self._reject('exponent_span_gt18', x, emin=emin, emax=emax)
        try:
            high, error = self._two_sum(self.hi, x)
            low, discarded = self._two_sum(self.lo, error)
            if discarded & 0x7fffffff:
                self._reject('nonzero_low_residual', x, discarded=discarded,
                             low_before=self.lo, error=error)
            output = self.add(high, low)
        except ArithmeticFault:
            self.poison = True
            raise
        self.hi, self.lo = high, low
        self.emin, self.emax = emin, emax
        self.count += 1
        return output
