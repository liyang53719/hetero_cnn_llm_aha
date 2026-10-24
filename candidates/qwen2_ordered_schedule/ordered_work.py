"""Strict 16-lane work protocol for the real selected Attention generator.

No ScalarService, native import, result tile copy or clock/latency claim.
A caller supplies reviewed FP32 lane operations; no permissive fallback exists.
The work's acc/fault arrays model the selected core's reused acc[16]+16 bits.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LaneResult:
    value: int
    flags: int = 0  # NV,DZ,OF,UF,NX, matching HardFloat bit positions


@dataclass(frozen=True)
class OrderedRetired:
    work: object
    key: int
    score: int | None
    maximum: int
    error: bool


class StrictLaneOps:
    """Existing primitive callbacks, explicitly separate from scalar requests.

    add/mul return LaneResult; bf returns an FP32-container BF16 word. Callbacks
    must provide strict RNE/tininess-after-rounding behavior. This adapter masks
    NV/DZ/OF/UF and tests finite; NX alone is accepted. It does not infer flags
    from host floating-point exception state or relax UF like MulIeeeRne.
    """
    def __init__(self, *, add, mul, bf, finite):
        self.add, self.mul, self.bf, self.finite = add, mul, bf, finite
        self.calls = {'add': 0, 'mul': 0, 'bf': 0}  # software observation only

    def primitive(self, operation, a, b):
        if not self.finite(a) or not self.finite(b):
            return LaneResult(0, 0x10)
        if operation not in ('add', 'mul'):
            raise ValueError('only existing FP32 Add/Mul lanes are borrowed')
        self.calls[operation] += 1
        r = getattr(self, operation)(a, b)
        if type(r) is not LaneResult or type(r.value) is not int or not 0 <= r.value < 1 << 32:
            raise ValueError('malformed FP32 lane result')
        if type(r.flags) is not int or not 0 <= r.flags < 32:
            raise ValueError('malformed FP32 flags')
        return r

    def materialize(self, a):
        self.calls['bf'] += 1
        result = self.bf(a)
        if type(result) is not int or not 0 <= result < 1 << 32:
            raise ValueError('malformed BF16 materialization')
        return result

    def fatal(self, result):
        return bool(result.flags & 0x1e) or not self.finite(result.value)


class OrderedFoldWork:
    def __init__(self, result, count, maximum):
        if type(count) is not int or not 1 <= count <= 16:
            raise ValueError('ordered group active keys must be 1..16')
        if (type(maximum) is not int or not 0 <= maximum < 1 << 32 or
                (maximum & 0x7f800000 == 0x7f800000 and maximum != 0xff800000)):
            raise ValueError('initial maximum must be finite or negative infinity')
        self.result, self.count = result, count
        self.acc, self.faults = [0]*16, [False]*16
        self.maximum, self.row, self.key = maximum, 0, 0
        self.state, self.pending, self.accepted = 'scan', None, None


    def consume(self, retired, key):
        """Accept exactly one response actually transferred by this adapter."""
        if type(key) is not int or not 0 <= key < self.count:
            return False
        if (type(retired) is not OrderedRetired or retired is not self.accepted or
                retired.work is not self or type(retired.key) is not int or
                retired.key != key or type(retired.error) is not bool or
                type(retired.maximum) is not int or not 0 <= retired.maximum < 1 << 32 or
                retired.maximum != self.maximum or retired.error != self.faults[key]):
            return False
        expected_state = 'fault' if retired.error else ('complete' if key+1==self.count else 'retire')
        expected_key = key if retired.error else min(key+1,self.count-1)
        if self.state != expected_state or self.key != expected_key:
            return False
        if retired.error:
            if retired.score is not None:return False
        elif (type(retired.score) is not int or not 0 <= retired.score < 1 << 32 or
              retired.score != self.acc[key]):
            return False
        self.accepted = None
        return True


class OrderedFoldAdapter:
    """One explicit progress step; output held until matching owner accepts it.

    The external service still owns result/done/ACK. This adapter NEVER sends
    a consumer ACK, retires a Matrix result, releases an owner or clears debts.
    """
    def __init__(self, lanes, *, observe=None):
        if type(lanes) is not StrictLaneOps:
            raise ValueError('explicit strict lane backend required')
        self.lanes, self.observe = lanes, observe
        self.active = None
        self.events = {'scan':0,'add_stripe':0,'scale':0,'retire':0}

    @staticmethod
    def less(a,b):
        if (a^b)>>31:
            return bool(a>>31) and bool((a|b)&0x7fffffff)
        return (a&0x7fffffff)>(b&0x7fffffff) if a>>31 else a<b

    def tick(self, work, *, result_valid=True, ready=False, abort=False):
        if any(type(x) is not bool for x in (result_valid, ready, abort)):
            raise ValueError('progress controls must be Boolean')
        if type(work) is not OrderedFoldWork:
            raise ValueError('exact ordered work required')
        if (self.active is not None and self.active.state in ('complete','fault')
                and self.active.accepted is None):
            self.active = None
        if self.active is None:
            if work.state in ('complete','fault','cancelled'):
                raise ValueError('cannot reissue a terminal work item')
            self.active = work
        if self.active is not work:
            raise ValueError('cannot replace held ordered work')
        if abort:
            work.state, work.pending, work.accepted = 'cancelled', None, None
            return None
        if work.accepted is not None:
            raise ValueError('owner has not consumed the previous retirement')
        if not result_valid:
            return None
        p = work.pending  # pre-step owner response; held under backpressure
        if p is not None:
            if ready:
                work.pending = None
                work.accepted = p
                if p.error or p.key + 1 == work.count:
                    work.state = 'fault' if p.error else 'complete'
                else:
                    work.key += 1
                    work.state = 'retire'
            return p
        if not result_valid or work.state in ('complete','fault','cancelled'):
            return None
        fp=self.lanes
        if work.state == 'scan':
            self.events['scan'] += 1
            for j in range(work.count):
                if not fp.finite(work.result.value[work.row][16*j+work.row]):
                    work.faults[j]=True
            work.row += 1
            if work.row == 16:work.row,work.state=0,'fold'
        elif work.state == 'fold':
            self.events['add_stripe'] += 1
            for j in range(work.count):
                if not work.faults[j]:
                    r=fp.primitive('add',work.acc[j],work.result.value[work.row][16*j+work.row])
                    if fp.fatal(r):work.faults[j]=True
                    else:work.acc[j]=r.value
            work.row += 1
            if work.row == 16:work.state='scale'
        elif work.state == 'scale':
            self.events['scale'] += 1
            for j in range(work.count):
                if not work.faults[j]:
                    total=work.acc[j];dot=fp.materialize(total)
                    if not fp.finite(dot):
                        work.faults[j]=True
                        continue
                    r=fp.primitive('mul',dot,0x3db504f3)
                    if fp.fatal(r):
                        work.faults[j]=True
                        continue
                    score=fp.materialize(r.value)
                    if not fp.finite(score):work.faults[j]=True
                    else:work.acc[j]=score
                    if self.observe is not None:self.observe('scale',j,total,dot,r.value,score)
            work.state='retire'
        elif work.state == 'retire':
            self.events['retire'] += 1
            j=work.key;score=None if work.faults[j] else work.acc[j]
            if score is not None and self.less(work.maximum,score):work.maximum=score
            work.pending=OrderedRetired(work,j,score,work.maximum,work.faults[j])
            work.state='reply'
        return None
