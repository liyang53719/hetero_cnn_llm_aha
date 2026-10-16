"""Bounded raw KV bank-port specification, not RTL simulation.

Uses caller's sole Banks allocation. Validity is cache-owned and may only be
published after matching ACK. soft_reset is a protocol reset request, not a
power/reset-domain reset; accepted SRAM debt cannot be erased by it.
"""


def uint(x, bits, nonzero=False):
    return type(x) is int and int(nonzero) <= x < (1 << bits)


def location(line, *, scratch_enabled=False):
    if type(scratch_enabled) is not bool or not uint(line, 13) or line >= (4192 if scratch_enabled else 4096):
        raise ValueError('raw KV line must be an integer in [0,4096)')
    bank = 2 * (line % 8)
    return bank, bank + 1, line // 8


from candidates.qwen2_resident_matrix.raw_kv.model import Key, Request, Response, Obligations


def valid_key(k, *, scratch_enabled=False):
    return (type(k) is Key and uint(k.owner, 32, True) and
            uint(k.tag, 32, True) and type(scratch_enabled) is bool and
            uint(k.line, 13) and k.line < (4192 if scratch_enabled else 4096) and type(k.write) is bool)


class RawKvPort:
    def __init__(self, banks, *, enabled=False, scratch_enabled=False):
        if type(scratch_enabled) is not bool:
            raise ValueError("scratch profile must be canonical bool")
        self.scratch_enabled = scratch_enabled
        if banks.depth != 1376 or len(banks.words) != 16:
            raise ValueError('existing 16x1376x256 Banks required')
        self.banks = banks
        self.enabled = enabled
        self.owner = None
        self.pending = None  # reserved synchronous SRAM output, not a second SRAM
        self.response = None  # one 512-bit response register + key
        self.poison = False

    @property
    def drained(self):
        return self.pending is None and self.response is None

    @property
    def blocked(self):
        return self.owner is not None

    def tick(self, *, acquire=None, release=None, request=None, ack=None,
             obligations=Obligations(), dense=False, tile=False, clear=False,
             abort=False, soft_reset=False):
        self.banks.begin_cycle()
        out = dict(acquired=False, released=False, accepted=False, acked=False,
                   response=self.response, owner=self.owner, dense_allowed=False,
                   tile_allowed=False, clear_allowed=False)
        conflict = dense or tile or clear
        pre_drained = self.drained
        stop = abort or soft_reset
        if not self.enabled:
            out.update(dense_allowed=True, tile_allowed=True, clear_allowed=True)
            return out
        if stop:
            if self.owner is not None or not pre_drained:
                self.poison = True
            elif soft_reset:
                self.poison = False
        # Accepted debt advances independently of abort/reset and foreign ACKs.
        if self.pending is not None:
            self.response = self.pending
            self.pending = None
        if out['response'] is not None and valid_key(ack, scratch_enabled=self.scratch_enabled) and ack == out['response'].key:
            self.response = None
            out['acked'] = True
        if release is not None:
            if uint(release, 32, True) and release == self.owner and pre_drained:
                self.owner = None
                out['released'] = True
        elif acquire is not None:
            if (uint(acquire, 32, True) and self.owner is None and pre_drained and
                    type(obligations) is Obligations and obligations.drained and
                    not conflict and not stop and not self.poison):
                self.owner = acquire
                out['acquired'] = True
        elif request is not None and pre_drained and not stop and not self.poison:
            if (type(request) is Request and type(request.key) is Key and
                    uint(request.key.owner, 32, True) and request.key.owner == self.owner and
                    uint(request.key.tag, 32, True) and uint(request.key.line, 13) and
                    request.key.line < (4192 if self.scratch_enabled else 4096) and
                    type(request.key.write) is bool and uint(request.data, 512)):
                k = request.key
                lo, hi, word = location(k.line, scratch_enabled=self.scratch_enabled)
                if k.write:
                    self.banks.write(lo, word, request.data & ((1 << 256) - 1))
                    self.banks.write(hi, word, request.data >> 256)
                    data = 0
                else:
                    data = self.banks.read(lo, word) | (self.banks.read(hi, word) << 256)
                self.pending = Response(k, data)
                out['accepted'] = True
        allow = out['owner'] is None and not self.poison and not out['acquired']
        out.update(dense_allowed=allow, tile_allowed=allow, clear_allowed=allow)
        return out
