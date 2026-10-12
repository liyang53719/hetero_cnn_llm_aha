"""Explicit backend-scoped QKV reduction parameters; no universal K split."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReductionProfile:
    identity: str
    ranges: tuple
    pair_reverse: bool
    source_sha256: str

    def validate(self, logical_k):
        if (type(self.identity) is not str or not self.identity or type(self.ranges) is not tuple or
                len(self.ranges)!=2 or type(self.pair_reverse) is not bool or
                type(self.source_sha256) is not str or len(self.source_sha256)!=64 or
                any(x not in '0123456789abcdef' for x in self.source_sha256)):
            raise ValueError('explicit immutable two-block profile and provenance required')
        end=0
        for span in self.ranges:
            if (type(span) is not tuple or len(span)!=2 or any(type(x) is not int for x in span) or
                    span[0]!=end or not span[0]<span[1]<=logical_k or span[0]%2 or span[1]%2):
                raise ValueError('complete ordered adjacent BF16 pair ranges required')
            end=span[1]
        if end!=logical_k:raise ValueError('profile does not cover original K')


QWEN2_QKV_PROFILE=ReductionProfile(
    'torch210cpu_onednn371_avx512_core_bf16_4t_qkv_k1536',
    ((0,1024),(1024,1536)),True,
    '07008af966dbe4d64b10f75c37e4d19e17159e3708543982a70c8ec996f1d5a5')

