"""Cold-M128 necessary architecture bounds, NOT measured performance or numeric acceptance.
Assumes original BF16 expert weights, original aggregate routing counts, and at most
one 64-byte external read beat/cycle. Includes complete-block nonpadding Matrix
MAC numerator, while all other phases remain in the block cycle denominator.
No weights, route IDs, model outputs, or external dependencies are used.
"""
import json
from fractions import Fraction

def result(name, macs, experts):
    weight_bytes = experts * 3 * 2048 * 512 * 2
    cycles_lower = weight_bytes // 64
    bound = Fraction(macs, 4096 * cycles_lower)
    return {'name': name, 'numerator_macs_or_upper': macs, 'routed_weight_bytes_lower': weight_bytes,
            'cycles_lower_at_one_64B_read_per_cycle': cycles_lower,
            'utilization_upper_fraction': [bound.numerator, bound.denominator],
            'utilization_upper_percent': float(bound * 100),
            'necessary_read_beats_for_80pct': float(Fraction(4, 5) / bound),
            'necessary_read_beats_for_90pct': float(Fraction(9, 10) / bound)}

common = 128*2048*256 + 128*8*3*2048*512 + 128*3*2048*512 + 128*2048
p3 = common + 128*(8192*2048 + 4096*2048 + 64*2048 + 2048*4096)
p4 = common + 128*(8192*2048 + 2*512*2048 + 2048*4096) + 2*16*256*(128*129//2)
assert (p3, p4) == (8002994176, 7248543744)
print(json.dumps({'status': 'NECESSARY_BOUND_NOT_MEASURED', 'results': [
    result('P3_complete_block_strict_Matrix', p3, 226),
    result('P4_complete_block_strict_Matrix', p4, 218),
    result('P3_optional_GDN_conv_upper_extension', p3+335020032+4145152, 226)
]}, indent=2))
