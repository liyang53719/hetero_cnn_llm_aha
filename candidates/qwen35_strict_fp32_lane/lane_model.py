"""Integer semantic/protocol MODEL, not execution of Scala or HardFloat.

Exact signed integer significands and powers of two model the two shared FMA
passes. This module does not import the independent Fraction reference. RNE
flags follow unbounded-exponent precision rounding for tininess-after; they
intentionally do not copy the old vector16.cpp delivered-exponent shortcut.
"""
from dataclasses import dataclass

MASK = (1 << 32) - 1
SIGN = 1 << 31
INF = 0x7f800000


def finite(u):
    return (u & INF) != INF


def _decode(u):
    if type(u) is not int or not 0 <= u <= MASK or not finite(u):
        raise ValueError("finite binary32 raw word required")
    sign = u >> 31
    e, f = (u >> 23) & 255, u & 0x7fffff
    n, power = ((1 << 23) | f, e - 150) if e else (f, -149)
    return (-n if sign else n), power, sign


def _nearest(n, discard):
    """Round a nonnegative integer divided by 2**discard; return inexact."""
    if discard <= 0:
        return n << -discard, False
    q, r = divmod(n, 1 << discard)
    half = 1 << (discard - 1)
    return q + int(r > half or (r == half and q & 1)), r != 0


def _round(n, power, zero_sign=0):
    if n == 0:
        return zero_sign << 31, 0
    sign, n = (SIGN if n < 0 else 0), abs(n)
    # Independent of the delivered subnormal quantum: round to precision first
    # with an unrestricted exponent, as required by the original HardFloat.
    discard = n.bit_length() - 24
    sig, unbounded_inexact = _nearest(n, discard)
    unit = power + discard
    if sig >= 1 << 24:
        sig >>= 1
        unit += 1
    exponent = unit + 23
    if exponent > 127:
        return sign | INF, 5
    if exponent >= -126:
        return sign | ((exponent + 127) << 23) | (sig & 0x7fffff), int(unbounded_inexact)
    sub, inexact = _nearest(n, -149 - power)
    # sub==2**23 represents minnormal. It can STILL carry UF|NX because the
    # precision-rounded, unrestricted-exponent value above was tiny.
    assert sub <= 1 << 23
    flags = (1 | 2) if inexact else 0
    return sign | sub, flags


def mul(a, b):
    an, ae, sa = _decode(a)
    bn, be, sb = _decode(b)
    return _round(an * bn, ae + be, sa ^ sb)


def add(a, b):
    an, ae, sa = _decode(a)
    bn, be, sb = _decode(b)
    e = min(ae, be)
    return _round((an << (ae - e)) + (bn << (be - e)), e, sa & sb)


def fma(a, b, c):
    an, ae, sa = _decode(a)
    bn, be, sb = _decode(b)
    cn, ce, sc = _decode(c)
    pn, pe, ps = an * bn, ae + be, sa ^ sb
    e = min(pe, ce)
    exact = (pn << (pe - e)) + (cn << (ce - e))
    zs = ps if pn == 0 and cn == 0 and ps == sc else 0
    return _round(exact, e, zs)


@dataclass(frozen=True)
class Request:
    tag: int
    mode: int
    a: int
    b: int
    acc: int

    def __post_init__(self):
        for name in ("tag", "a", "b", "acc"):
            if type(getattr(self, name)) is not int or not 0 <= getattr(self, name) <= MASK:
                raise ValueError(name)
        if type(self.mode) is not int or not 0 <= self.mode < 4:
            raise ValueError("mode")


def blank_response():
    return dict(tag=0, mode=0, status=0, product=0, productValid=False,
                value=0, valueValid=False, accCommit=False, mulFlags=0,
                mulFlagsValid=False, addFlags=0, addFlagsValid=False,
                fmaFlags=0, fmaFlagsValid=False, passesCompleted=0)


class LaneModel:
    """Pre-edge Decoupled model; arithmetic is software at modeled Round only.

    injected_round is solely for explicit protocol fault/legacy propagation
    fixtures, not evidence that hardware produced the injected result.
    """
    def __init__(self, injected_round=None):
        self.injected_round = injected_round
        self.reset()

    def reset(self):
        self.state = "idle"
        self.job = None
        self.reply = blank_response()
        self.add_pass = False
        self.operands = None
        self.stage_enables = dict(pre=0, mul=0, post=0, round=0)
        self.round_inputs = []

    def signals(self, resetting=False):
        return dict(request_ready=self.state == "idle" and not resetting,
                    result_valid=self.state == "reply" and not resetting,
                    busy=self.state != "idle" and not resetting,
                    result=dict(self.reply))

    def tick(self, request=None, result_ready=False, resetting=False):
        before = self.signals(resetting)
        if resetting:
            self.reset()
            return before
        if self.state == "idle":
            if request is None:
                return before
            if not isinstance(request, Request):
                raise TypeError("Request required")
            self.job = request
            self.reply = blank_response()
            self.reply.update(tag=request.tag, mode=request.mode)
            self.add_pass = False
            if request.mode > 1:
                self.reply["status"] = 1
                self.state = "reply"
            elif request.mode == 0 and ((request.a | request.b) >> 16):
                self.reply["status"] = 2
                self.state = "reply"
            elif request.mode == 1 and not all(map(finite, (request.a, request.b, request.acc))):
                self.reply["status"] = 3
                self.state = "reply"
            else:
                self.state = "pre"
        elif self.state == "pre":
            self.stage_enables["pre"] += 1
            j = self.job
            if j.mode == 0:
                self.operands = (j.a << 16, j.b << 16, j.acc)
            elif self.add_pass:
                self.operands = (self.reply["product"], 0x3f800000, j.acc)
            else:
                self.operands = (j.a, j.b, (j.a ^ j.b) & SIGN)
            self.state = "mul"
        elif self.state == "mul":
            self.stage_enables["mul"] += 1
            self.state = "post"
        elif self.state == "post":
            self.stage_enables["post"] += 1
            self.state = "round"
        elif self.state == "round":
            self.stage_enables["round"] += 1
            self.round_inputs.append(self.operands)
            if self.injected_round is None:
                value, flags = fma(*self.operands)
            else:
                value, flags = self.injected_round(self.operands, self.add_pass, self.job.mode)
            if not 0 <= value <= MASK or not 0 <= flags < 32:
                raise ValueError("malformed simulated Round response")
            fatal = bool(flags & 30) or not finite(value)
            if self.job.mode == 0:
                self.reply.update(value=value, valueValid=True, fmaFlags=flags,
                                  fmaFlagsValid=True, passesCompleted=1, accCommit=True)
                self.state = "reply"
            elif not self.add_pass:
                self.reply.update(product=value, productValid=True, mulFlags=flags,
                                  mulFlagsValid=True, passesCompleted=1)
                if fatal:
                    self.reply["status"] = 4
                    self.state = "reply"
                else:
                    self.add_pass = True
                    self.state = "pre"
            else:
                self.reply.update(value=value, valueValid=True, addFlags=flags,
                                  addFlagsValid=True, passesCompleted=2,
                                  accCommit=not fatal, status=5 if fatal else 0)
                self.state = "reply"
        elif self.state == "reply":
            if result_ready:
                self.state = "idle"
        else:
            raise AssertionError(self.state)
        return before
