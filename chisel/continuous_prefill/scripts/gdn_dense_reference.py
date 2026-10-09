"""Explicit K1024/2048/3584 adapter over the established integer/C FMA oracles.

All K steps form one uninterrupted FP32 accumulator chain. There is exactly
one terminal BF16 RNE per output; no K-chunk BF16 intermediates are permitted.
The original QKV strict-K1024 entry remains unchanged.
"""
from pathlib import Path
import subprocess
import numpy as np
from host_bf16_qkv_reference import (ROOT, integer, require, digest, file_digest,
                                    _compile_matrix)

ALLOWED_K = (1024, 2048, 3584)


def compile_reference(directory):
    return _compile_matrix(Path(directory), source=Path(__file__).with_suffix('.c'))


def projection_trace(activation, weight):
    require(isinstance(weight, np.ndarray) and weight.ndim == 2,
            'native K-major matrix required')
    k, columns = weight.shape
    require(k in ALLOWED_K and columns in (256, 512), 'unsupported block Dense reduction geometry')
    integer.bf16_array(activation, (k,), 'actual A')
    integer.bf16_array(weight, (k, columns), 'actual W')
    if k == 1024:
        return integer.projection_trace(activation, weight)
    acc, aggregate = [0] * columns, [0] * columns
    steps = np.empty((k, columns), dtype='<u4')
    for row in range(k):
        a = int(activation[row]) << 16
        for column in range(columns):
            acc[column], flags = integer.fma_rne(a, int(weight[row, column]) << 16, acc[column])
            aggregate[column] |= flags
        steps[row] = acc
    converted = [integer.rope.bf16_convert(value) for value in acc]
    require(all((word & integer.rope.EXPONENT) != integer.rope.EXPONENT for word, _ in converted),
            'projection overflow/nonfinite boundary')
    return dict(fp32=tuple(acc), steps_fp32=steps, fma_flags=tuple(aggregate),
                bf16=tuple(word >> 16 for word, _ in converted),
                conversion_flags=tuple(flags for _, flags in converted))


def project_and_crosscheck(activation, weight, executable, scratch):
    trace = projection_trace(activation, weight)
    k, columns = weight.shape
    source, target = Path(scratch) / 'matrix_c_inputs.bin', Path(scratch) / 'matrix_c_outputs.bin'
    require(not source.exists() and not target.exists(), 'preserve existing reference scratch')
    np.concatenate((np.array([k, columns], dtype='<u4'), activation.astype('<u4') << 16,
                    weight.reshape(-1).astype('<u4') << 16)).tofile(source)
    subprocess.run([str(executable), str(source), str(target)], check=True, capture_output=True, timeout=120)
    require(target.stat().st_size == 4 * (k + 3) * columns, 'C terminal/trace output size drift')
    actual = np.fromfile(target, dtype='<u4')
    expected = np.concatenate((np.asarray(trace['fp32'], dtype='<u4'),
                               np.asarray(trace['bf16'], dtype='<u4') << 16,
                               np.asarray(trace['fma_flags'], dtype='<u4'), trace['steps_fp32'].reshape(-1)))
    require(np.array_equal(actual, expected), 'independent integer/C long-K FMA/flags/rounding mismatch')
    receipt = dict(k=k, columns=columns, matrix_accumulator_steps=k * columns,
                   bit_mismatches=0, flag_mismatches=0,
                   c_input_sha256=file_digest(source), c_output_sha256=file_digest(target),
                   integer_step_sha256=digest(trace['steps_fp32'].tobytes()),
                   c_step_sha256=digest(actual[3 * columns:].tobytes()),
                   bf16_conversion_flags_independently_checked=False,
                   uninterrupted_fp32_accumulation=True, terminal_bf16_roundings=1)
    receipt['pass'] = True
    result = {key: np.asarray(trace[name], dtype=dtype).tobytes()
              for key, name, dtype in (('fp32', 'fp32', '<u4'), ('bf16', 'bf16', '<u2'), ('fma_flags', 'fma_flags', '<u4'))}
    source.unlink();target.unlink()
    return result, receipt
