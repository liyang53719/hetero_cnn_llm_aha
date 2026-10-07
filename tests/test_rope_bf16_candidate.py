"""Bit patterns, independent C evidence, and policy boundaries for candidate."""
from pathlib import Path
import platform
import random
import shutil
import subprocess

import pytest

from heteronpu import rope_hardware_oracle as old
from heteronpu.rope_rounding_ablation import trace_pair
from heteronpu.rope_bf16_candidate import (
    COLUMNS, NATIVE_WITNESS, NV, DZ, OF, UF, NX,
    add_rne, bf16_convert, converter_inputs, mul_rne, pair_trace, synthetic_pairs,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('operation,a,b,expected,flags', [
    (add_rne, 0x3F800000, 0x33800000, 0x3F800000, NX),
    (add_rne, 0x3F800001, 0x33800000, 0x3F800002, NX),
    (add_rne, 0x3F800000, 0xBF800000, 0, 0),
    (add_rne, 0x80000000, 0x80000000, 0x80000000, 0),
    (add_rne, 0x80000000, 0, 0, 0),
    (add_rne, 0x7F7FFFFF, 0x72800000, 0x7F7FFFFF, NX),
    (add_rne, 0x7F7FFFFF, 0x73000000, 0x7F800000, OF | NX),
    (add_rne, 0xFF7FFFFF, 0xF3000000, 0xFF800000, OF | NX),
    (add_rne, 0x7F000000, 0x7F000000, 0x7F800000, OF | NX),
    (mul_rne, 0x80000000, 0x3F800000, 0x80000000, 0),
    (mul_rne, 1, 0x3F000000, 0, UF | NX),
    (mul_rne, 3, 0x3F000000, 2, UF | NX),
    (mul_rne, 0x80000001, 0x3F000000, 0x80000000, UF | NX),
    (mul_rne, 0x00800000, 0x3F000000, 0x00400000, 0),
    (mul_rne, 0x00800000, 0x3F7FFFFF, 0x00800000, UF | NX),
    (mul_rne, 0x00800001, 0x3F7FFFFE, 0x00800000, NX),
    (mul_rne, 0x7F7FFFFF, 0x3F800000, 0x7F7FFFFF, 0),
    (mul_rne, 0x7F7FFFFF, 0x3F800001, 0x7F800000, OF | NX),
    (mul_rne, 0xFF7FFFFF, 0x40000000, 0xFF800000, OF | NX),
    (mul_rne, 0x3F800001, 0x3F800001, 0x3F800002, NX),
])
def test_fp32_directed(operation, a, b, expected, flags):
    assert operation(a, b) == (expected, flags)


@pytest.mark.parametrize('operation', [mul_rne, add_rne])
@pytest.mark.parametrize('nan,flags', [
    (0x7FC00000, 0), (0xFFC00000, 0), (0x7FFFFFFF, 0),
    (0xFFFFFFFF, 0), (0x7F800001, NV), (0xFF800001, NV),
    (0x7FBFFFFF, NV), (0xFFBFFFFF, NV),
])
@pytest.mark.parametrize('other', [0, 0x80000000, 0x3F800000, 0x7F800000, 0xFF800000, 0x7FC12345])
def test_fp32_canonical_nan_both_operands(operation, nan, flags, other):
    assert operation(nan, other) == (0x7FC00000, flags)
    assert operation(other, nan) == (0x7FC00000, flags)


@pytest.mark.parametrize('operation,a,b,expected,flags', [
    (mul_rne, 0x7F800000, 0, 0x7FC00000, NV),
    (mul_rne, 0xFF800000, 0x80000000, 0x7FC00000, NV),
    (mul_rne, 0x7F800000, 0xBF800000, 0xFF800000, 0),
    (mul_rne, 0xFF800000, 0xBF800000, 0x7F800000, 0),
    (mul_rne, 0xFF800000, 0x7F800000, 0xFF800000, 0),
    (add_rne, 0x7F800000, 0xFF800000, 0x7FC00000, NV),
    (add_rne, 0x7F800000, 0x7F800000, 0x7F800000, 0),
    (add_rne, 0xFF800000, 0xFF800000, 0xFF800000, 0),
    (add_rne, 0xFF800000, 0x3F800000, 0xFF800000, 0),
])
def test_fp32_infinity(operation, a, b, expected, flags):
    assert operation(a, b) == operation(b, a) == (expected, flags)


@pytest.mark.parametrize('word,expected,flags', [
    (0, 0, 0), (0x80000000, 0x80000000, 0),
    (0x3F807FFF, 0x3F800000, NX), (0x3F808000, 0x3F800000, NX),
    (0x3F808001, 0x3F810000, NX), (0x3F818000, 0x3F820000, NX),
    (0xBF808000, 0xBF800000, NX), (0xBF818000, 0xBF820000, NX),
    (1, 0, UF | NX), (0x80000001, 0x80000000, UF | NX),
    (0x00008000, 0, UF | NX), (0x00008001, 0x00010000, UF | NX),
    (0x00010000, 0x00010000, 0), (0x00018000, 0x00020000, UF | NX),
    (0x007F7FFF, 0x007F0000, UF | NX),
    (0x007F8000, 0x00800000, NX), (0x007FFFFF, 0x00800000, NX),
    (0x807F8000, 0x80800000, NX), (0x00800000, 0x00800000, 0),
    (0x7F7F0000, 0x7F7F0000, 0), (0x7F7F7FFF, 0x7F7F0000, NX),
    (0x7F7F8000, 0x7F800000, OF | NX), (0x7F7FFFFF, 0x7F800000, OF | NX),
    (0xFF7F8000, 0xFF800000, OF | NX),
    (0x7F800000, 0x7F800000, 0), (0xFF800000, 0xFF800000, 0),
    (0x7FC00000, 0x7FC00000, 0), (0xFFC00000, 0x7FC00000, 0),
    (0x7FFFFFFF, 0x7FC00000, 0), (0xFFC00001, 0x7FC00000, 0),
    (0x7F800001, 0x7FC00000, NV), (0xFF800001, 0x7FC00000, NV),
    (0x7FBFFFFF, 0x7FC00000, NV),
])
def test_converter_boundary_and_flags(word, expected, flags):
    assert bf16_convert(word) == (expected, flags)


def test_binary32_and_converter_tininess_are_deliberately_different():
    assert mul_rne(0x00800000, 0x3F7FFFFF) == (0x00800000, UF | NX)
    assert bf16_convert(0x007F8000) == (0x00800000, NX)
    assert bf16_convert(0x007F7FFF) == (0x007F0000, UF | NX)
    assert bf16_convert(0x007F0000) == (0x007F0000, 0)


@pytest.mark.parametrize('bad', [-1, 2**32, True, 1.0, None, '00000000'])
def test_malformed_word_rejected(bad):
    with pytest.raises((ValueError, TypeError)):
        bf16_convert(bad)
    for operation in (mul_rne, add_rne):
        for operands in ((bad, 0), (0, bad)):
            with pytest.raises((ValueError, TypeError)):
                operation(*operands)
    for port in range(4):
        inputs = [0, 0, 0x3F800000, 0]
        inputs[port] = bad
        with pytest.raises((ValueError, TypeError)):
            pair_trace(*inputs)


def test_finite_compatibility_with_frozen_oracle_and_ablation():
    rng = random.Random(7391)
    for _ in range(2000):
        a, b = (rng.getrandbits(32) for _ in range(2))
        if a & 0x7F800000 == 0x7F800000 or b & 0x7F800000 == 0x7F800000:
            continue
        for operation, previous in ((mul_rne, old.mul_rne), (add_rne, old.add_rne)):
            try:
                expected = previous(a, b)
            except ValueError as error:
                assert 'overflow' in str(error)
                assert operation(a, b)[1] == OF | NX
            else:
                assert operation(a, b) == expected
    for _ in range(300):
        inputs = tuple((rng.randrange(2) << 31) | (rng.randrange(90, 155) << 23)
                       | rng.randrange(1 << 23) for _ in range(4))
        actual = pair_trace(*inputs)
        prior = trace_pair(*inputs, 'both_bf16')
        assert actual[:12] == prior[:12]
        assert actual[16:22] == prior[12:18]


def test_native_witness_complete_trace_and_flags():
    trace = pair_trace(*NATIVE_WITNESS)
    assert len(trace) == len(COLUMNS) == 25
    assert len(set(COLUMNS)) == 25
    assert trace == (
        0xBF920000, 0xBE7D2000, 0xBD005200, 0xC1100000,
        0, 0, 0, 0,
        0xBF920000, 0xBE7D0000, 0xBD000000, 0xC1100000,
        0, NX, NX, 0,
        0xBF64C000, 0xC1108000, 0, 0,
        0xBF650000, 0xC1100000, NX, NX, NX,
    )
    assert trace[20:22] == old.native_bf16_pair(*NATIVE_WITNESS)
    assert tuple(old.bf16_rne_word(x) for x in old.pair_rne(*NATIVE_WITNESS)[:2]) == (0xBF650000, 0xC1110000)


def test_no_implicit_fma_or_input_bf16_preconversion():
    trace = pair_trace(0x3F800001, 0x3F800000, 0x3F7FFFFE, 0x3F800000)
    assert trace[:4] == (0x3F800000, 0x3F800000, 0x3F800001, 0x3F7FFFFE)
    assert trace[4:8] == (NX, 0, 0, 0)
    assert trace[16] == 0  # Fused exact product-minus-one would be -2^-46.
    assert trace[12:16] == (0, 0, NX, NX)


@pytest.mark.parametrize('inputs,expected', [
    ((0x80000000, 0, 0x3F800000, 0x3F800000), (0x80000000, 0)),
    ((0, 0x80000000, 0x3F800000, 0x3F800000), (0, 0)),
    ((1, 3, 0x3F000000, 0x3F000000), (0, 0)),
    ((0x3F800000, 0x3F800000, 0x3F800000, 0x3F800000), (0, 0x40000000)),
])
def test_signed_zero_and_operation_order(inputs, expected):
    assert pair_trace(*inputs)[20:22] == expected


def test_aggregate_includes_each_real_stage_flag():
    flag_columns = (*range(4, 8), *range(12, 16), 18, 19, 22, 23)
    for inputs in synthetic_pairs():
        trace = pair_trace(*inputs)
        expected = 0
        for column in flag_columns:
            assert not (trace[column] & DZ)
            expected |= trace[column]
        assert trace[24] == expected
        for column in (*range(8, 12), 20, 21):
            assert not (trace[column] & 0xFFFF)
    # Conversion overflow can itself create invalid on a subsequent inf-inf.
    trace = pair_trace(0x7F7F8000, 0x7F7F8000, 0x3F800000, 0x3F800000)
    assert trace[4:8] == (0, 0, 0, 0)
    assert trace[12:16] == (OF | NX,) * 4
    assert trace[16] == 0x7FC00000 and trace[18] == NV
    assert trace[20:22] == (0x7FC00000, 0x7F800000)
    assert trace[22:24] == (0, 0)
    assert trace[24] == NV | OF | NX


def test_synthetic_corpus_coverage_and_reproducibility():
    rows = synthetic_pairs()
    assert rows == synthetic_pairs() and len(rows) == 13618
    assert rows[0] == NATIVE_WITNESS
    for port in range(4):
        assert {(row[port] >> 23) & 255 for row in rows} == set(range(256))
    words = converter_inputs()
    assert words == converter_inputs() and len(words) == 331776
    for index, high in enumerate(range(65536)):
        assert words[index * 5:index * 5 + 5] == tuple(
            (high << 16) | low for low in (0, 0x7FFF, 0x8000, 0x8001, 0xFFFF))


@pytest.fixture(scope='module')
def c_reference(tmp_path_factory):
    compiler = shutil.which('gcc')
    if compiler is None:
        pytest.skip('independent C verification requires gcc')
    executable = tmp_path_factory.mktemp('bf16_candidate_c') / 'reference'
    subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-frounding-math', '-ffp-contract=off', '-fno-fast-math',
                    str(ROOT / 'scripts/rope_bf16_candidate_reference.c'),
                    '-lm', '-o', str(executable)], check=True, capture_output=True, text=True)
    return executable


def _check_c_trace(actual, expected):
    """Only observed FP32 UF deltas at inexact min-normal may differ.

    Aggregate differences are permitted solely when fully explained by these
    exact per-stage differences. Conversion flags and every value are exact.
    This is deliberately not a general underflow or aggregate waiver.
    """
    actual = list(actual)
    assert len(actual) == len(expected) == 25
    operation_flags = {4: 0, 5: 1, 6: 2, 7: 3, 18: 16, 19: 17}
    all_flags = (*range(4, 8), *range(12, 16), 18, 19, 22, 23)
    aggregate = 0
    for column in all_flags:
        aggregate |= actual[column]
    assert actual[24] == aggregate
    for column, result_column in operation_flags.items():
        if actual[column] != expected[column]:
            assert actual[column] ^ expected[column] == UF
            assert actual[column] & NX and expected[column] & NX
            assert actual[result_column] == expected[result_column]
            assert actual[result_column] & 0x7FFFFFFF == 0x00800000
            actual[column] = expected[column]
    actual[24] = 0
    for column in all_flags:
        actual[24] |= actual[column]
    assert tuple(actual) == tuple(expected)


def test_independent_c_self_test(c_reference):
    result = subprocess.run([str(c_reference), '--self-test'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'PASS' in result.stdout


def test_independent_c_all_trace_words_full_domain(c_reference):
    inputs = synthetic_pairs()
    result = subprocess.run([str(c_reference)], input=''.join(
        ' '.join(f'{word:08x}' for word in row) + '\n' for row in inputs),
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    rows = result.stdout.splitlines()
    assert len(rows) == len(inputs)
    for inputs_row, actual in zip(inputs, rows):
        _check_c_trace(tuple(int(word, 16) for word in actual.split()), pair_trace(*inputs_row))


def test_independent_c_all_converter_boundaries_exact(c_reference):
    inputs = converter_inputs()
    result = subprocess.run([str(c_reference), '--converter'],
                            input=''.join(f'{word:08x}\n' for word in inputs),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    actual = result.stdout.splitlines()
    assert len(actual) == len(inputs)
    for word, row in zip(inputs, actual):
        assert tuple(int(token, 16) for token in row.split()) == bf16_convert(word)


@pytest.mark.parametrize('column,mask', [(0, 1), (8, 1), (12, UF), (20, 1), (22, UF), (24, UF)])
def test_c_comparison_rejects_value_converter_and_aggregate_mutations(column, mask):
    trace = pair_trace(*NATIVE_WITNESS)
    bad = list(trace)
    bad[column] ^= mask
    with pytest.raises(AssertionError):
        _check_c_trace(bad, trace)


def test_c_comparison_rejects_exact_min_normal_underflow_mutation():
    trace = pair_trace(0x00800000, 0, 0x3F800000, 0)
    bad = list(trace)
    bad[4] |= UF
    bad[24] |= UF
    with pytest.raises(AssertionError):
        _check_c_trace(bad, trace)


@pytest.mark.parametrize('line', [
    '00000000 00000000 3f800000\n',
    '00000000 00000000 3f800000 00000000 extra\n',
    '-1 00000000 3f800000 00000000\n',
    '100000000 00000000 3f800000 00000000\n',
    '00000000\x00 00000000 3f800000 00000000\n',
    ' ' * 512 + '\n',
])
def test_c_malformed_input_rejected(c_reference, line):
    result = subprocess.run([str(c_reference)], input=line, capture_output=True, text=True)
    assert result.returncode != 0 and not result.stdout.strip()


def test_c_file_cli_and_blank_lines(c_reference, tmp_path):
    inputs, output = tmp_path / 'inputs.txt', tmp_path / 'outputs.txt'
    inputs.write_text('\n  \t\n' + ' '.join(f'0x{word:08X}' for word in NATIVE_WITNESS) + '\n')
    result = subprocess.run([str(c_reference), '--input', str(inputs), '--output', str(output)],
                            capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == '', result.stderr
    _check_c_trace(tuple(int(word, 16) for word in output.read_text().split()),
                   pair_trace(*NATIVE_WITNESS))
    inputs.write_text('007f8000\n7f800001\n')
    result = subprocess.run([str(c_reference), '--converter', '--input', str(inputs),
                             '--output', str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == '00800000 00000001\n7fc00000 00000010\n'


@pytest.mark.parametrize('arguments', [
    ['--unknown'], ['--converter', '--converter'], ['--input'],
    ['--output'], ['--self-test', '--converter'], ['--help', '--self-test'],
])
def test_c_invalid_cli_rejected(c_reference, arguments):
    result = subprocess.run([str(c_reference), *arguments], capture_output=True, text=True)
    assert result.returncode != 0 and not result.stdout.strip()


def test_c_input_output_same_path_rejected(c_reference, tmp_path):
    path = tmp_path / 'preserved.txt'
    path.write_text('00000000\n')
    result = subprocess.run([str(c_reference), '--converter', '--input', str(path),
                             '--output', str(path)], capture_output=True, text=True)
    assert result.returncode != 0 and path.read_text() == '00000000\n'


@pytest.fixture(scope='module')
def ftz_daz_reference(c_reference, tmp_path_factory):
    if platform.machine().lower() not in ('x86_64', 'amd64', 'i386', 'i686'):
        pytest.skip('MXCSR FTZ/DAZ control is an x86-only host rejection test')
    directory = tmp_path_factory.mktemp('bf16_ftz_daz')
    source, executable = directory / 'host_mode.c', directory / 'host_mode'
    source.write_text(
        '#define _POSIX_C_SOURCE 200809L\n'
        '#include <stdlib.h>\n#include <xmmintrin.h>\n'
        '#define main reference_main\n'
        f'#include "{ROOT / "scripts/rope_bf16_candidate_reference.c"}"\n'
        '#undef main\n'
        'int main(int argc, char **argv) {\n'
        '    if (argc < 2) return 2;\n'
        '    _mm_setcsr(_mm_getcsr() | (unsigned)strtoul(argv[1], NULL, 0));\n'
        '    return reference_main(argc - 1, argv + 1);\n}\n')
    subprocess.run([shutil.which('gcc'), '-std=c11', '-O2', '-frounding-math',
                    '-ffp-contract=off', '-fno-fast-math', str(source), '-lm',
                    '-o', str(executable)], check=True, capture_output=True, text=True)
    return executable


@pytest.mark.parametrize('mask', ['0x8000', '0x40', '0x8040'])
def test_c_rejects_ftz_daz(ftz_daz_reference, mask):
    result = subprocess.run([str(ftz_daz_reference), mask, '--self-test'],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert 'FTZ' in result.stderr or 'DAZ' in result.stderr
    assert 'PASS' not in result.stdout


@pytest.mark.parametrize('alias_kind', [
    'relative_absolute', 'absolute_relative', 'hardlink', 'symlink_output', 'symlink_input',
])
def test_c_file_alias_rejected_without_truncation(c_reference, tmp_path, alias_kind):
    original, alias = tmp_path / 'input.txt', tmp_path / 'alias.txt'
    original.write_text('007f8000\n7f800001\n')
    input_path, output_path = str(original), str(alias)
    if alias_kind == 'relative_absolute':
        input_path, output_path = original.name, str(original)
    elif alias_kind == 'absolute_relative':
        input_path, output_path = str(original), original.name
    elif alias_kind == 'hardlink':
        alias.hardlink_to(original)
    elif alias_kind == 'symlink_output':
        alias.symlink_to(original)
    else:
        alias.symlink_to(original)
        input_path, output_path = str(alias), str(original)
    result = subprocess.run([str(c_reference), '--converter', '--input', input_path,
                             '--output', output_path], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode != 0, 'aliased input/output must be rejected'
    assert original.read_text() == '007f8000\n7f800001\n'


def test_c_output_alias_to_stdin_file_rejected(c_reference, tmp_path):
    path = tmp_path / 'input.txt'
    path.write_text('007f8000\n7f800001\n')
    with path.open() as source:
        result = subprocess.run([str(c_reference), '--converter', '--output', str(path)],
                                stdin=source, capture_output=True, text=True)
    assert result.returncode != 0
    assert path.read_text() == '007f8000\n7f800001\n'
