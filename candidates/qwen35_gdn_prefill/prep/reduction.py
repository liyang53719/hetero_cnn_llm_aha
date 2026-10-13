"""Explicit fixed CPU DEFAULT FP32 sum order on 128 nonnegative squares.

No Torch/NumPy reference calls, FP64, new array, or extra DDR reads. One
caller-owned Scalar and unchanged 128-word head cache. This software schedule
is not yet bound in production Chisel. Four 32-bit phase temporaries can reuse
accumulator(total), inverseNorm(lane_sum), positive(group_sum), temporary.
All are initialized before use; norm/gate phases overwrite their former values.
"""
ASCENDING = 'legacy_ascending128'
CPU_DEFAULT_35B = 'torch_2_10_cpu_default_f32_8lane_4ilp_128'


def sum_squares128(cache, op):
    if len(cache) != 128:
        raise ValueError('fixed128 head cache required')
    total = 0
    for lane in range(8):
        lane_sum = 0
        for group in range(4):
            group_sum = 0
            for t in range(4):
                x = cache[lane + 8 * group + 32 * t]
                temporary = op('mul_ieee_rne', x, x)
                group_sum = temporary if t == 0 else op('add', group_sum, temporary)
            lane_sum = group_sum if group == 0 else op('add', lane_sum, group_sum)
        total = lane_sum if lane == 0 else op('add', total, lane_sum)
    return total
