"""Small schedule/identity guards; no model capture, JVM or C build."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/prepare_qk_norm_rope_owner_fixture.py'
SPEC = importlib.util.spec_from_file_location('owner_fixture', SCRIPT)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


def check_scalar_rows(rows):
    for op, a, b, result, flags in rows:
        operation = fixture.rope.add_rne if op == 0 else fixture.rope.mul_rne
        assert int(op) in (0, 1)
        assert operation(int(a), int(b)) == (int(result), int(flags))


def test_norm_trace_uses_chunk_schedule_and_exact_frozen_nodes():
    x = tuple(0x3F000000 | ((i % 127) << 16) | ((i % 2) << 31) for i in range(256))
    gamma = tuple(0xBC000000 | ((i % 63) << 16) for i in range(256))
    scalar, conversion, frozen = fixture.norm_execution_trace(x, gamma)
    assert scalar.shape == (1290, 5)
    assert conversion.shape == (256, 3)
    assert scalar.dtype == np.dtype('<u4')
    check_scalar_rows(scalar)
    for chunk in range(16):
        start = chunk * 32
        assert np.array_equal(scalar[start:start + 16, 0], np.ones(16))
        assert tuple(scalar[start:start + 16, 1]) == x[chunk * 16:(chunk + 1) * 16]
        assert tuple(scalar[start + 16:start + 31, 3]) == frozen['tree'][chunk * 15:(chunk + 1) * 15]
        assert int(scalar[start + 31, 3]) == frozen['running'][chunk]
    assert list(scalar[512:522, 0]) == [1, 0, 1, 0, 1, 1, 1, 0, 1, 1]
    assert list(scalar[522:, 0]) == [0, 1, 1] * 256
    for word, converted, flags in conversion:
        assert fixture.rope.bf16_convert(int(word)) == (int(converted), int(flags))
    assert tuple(conversion[:, 1]) == frozen['output_bf16']


def test_rope_pairs_have_four_rounded_products_and_preserve_all_tail_bits():
    prefix = [0x3F000000 | ((i % 60) << 16) | ((i % 2) << 31) for i in range(64)]
    # The transport-only tail includes signed zero, NaN and infinity encodings.
    tail = ([0x80000000, 0x7FC10000, 0x7F800000, 0x00800000] * 48)
    trig = [0x3F400000] * 32 + [0x3E800000] * 32
    output, scalar, conversion, full, pairs = fixture.rope_execution_trace(prefix + tail, trig)
    assert scalar.shape == (192, 5)
    assert conversion.shape == (192, 3)
    assert full.shape == (32, 25)
    check_scalar_rows(scalar)
    assert list(scalar[:, 0]) == [1, 1, 1, 1, 0, 0] * 32
    assert list(output[64:]) == tail
    for pair in range(32):
        assert tuple(pairs[pair]) == (prefix[pair], prefix[pair + 32], trig[pair], trig[pair + 32])
        assert scalar[pair * 6 + 4, 1] == conversion[pair * 6, 1]
        assert scalar[pair * 6 + 4, 2] == conversion[pair * 6 + 1, 1] ^ 0x80000000
        assert output[pair] == conversion[pair * 6 + 4, 1]
        assert output[pair + 32] == conversion[pair * 6 + 5, 1]
    for word, converted, flags in conversion:
        assert fixture.rope.bf16_convert(int(word)) == (int(converted), int(flags))


def test_exception_flags_are_rejected_while_inexact_is_preserved():
    with pytest.raises(ValueError, match='NV/DZ/OF/UF'):
        fixture.rope_execution_trace([0x7F7F0000] * 256, [0x7F7F0000] * 64)
    _, scalar, conversion, _, _ = fixture.rope_execution_trace([0x3F010000] * 256, [0x3F010000] * 64)
    assert not np.any(scalar[:, 4] & 0x1E)
    assert np.any(conversion[:, 2] & 1)


def test_all_existing_arithmetic_sources_remain_code_pinned():
    for path, digest in fixture.ORACLE_PINS.items():
        assert fixture.checked(fixture.ROOT / path, digest).is_file()


def test_mutated_evidence_cannot_pass_by_reusing_a_filename(tmp_path):
    path = tmp_path / 'actual_q.bf16le'
    path.write_bytes(bytes.fromhex('803f0040'))
    digest = fixture.file_sha(path)
    fixture.checked(path, digest)
    path.write_bytes(bytes.fromhex('813f0040'))
    with pytest.raises(ValueError, match='hash drift'):
        fixture.checked(path, digest)


def test_existing_output_is_rejected_before_any_expensive_read():
    with pytest.raises(ValueError, match='fresh output directory'):
        fixture.prepare(fixture.ROOT / 'work')
