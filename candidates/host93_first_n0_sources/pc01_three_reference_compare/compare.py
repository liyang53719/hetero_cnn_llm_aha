"""Read-only full PC01 data observation. Caller retains native/source qualification."""
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import time

COUNT = 196608
BYTES = 786432
SECONDS = 60
N0_SHA = '3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f'
RECEIPT_PIN = (1249, 'ae61290bf5ba0d5ff2f21920c8913a15736c788e3093a06ff2c9e0ba89b586f6')
REFERENCES = {
    'qraw.typed.f32le': (786432, '346b2974824f3e2849206d5ea72f7a066c328439c4faa088bf2a13d742b713f1'),
    'qraw.math.f32le': (786432, '42604d286bb7f237c4dc982b4a65065ea74edec82714a4e0f0ad07fcd6172851'),
    'qraw.math.f64le': (1572864, 'ef5d02aa4b9ad77afdb61eb2842786780d218978bc1dac4641068ec4856710e8'),
}
# Fixed canonical burst-write geometry. Source derivation/review accompanies this file.
QRAW_B_RESPONSES = 2048
AXI_KEYS = frozenset('ars rbeats_expected rbeats rlasts aws wbeats_expected wbeats wbeats_committed bs strobed_bytes ar_stall aw_stall w_stall r_stall b_stall'.split())
TEXT_FIELDS = {'scope': 'PC0_ACK0_PC1_ACK1_M128_ONLY', 'status': 'ACK1_ACTUAL_CAPTURED',
               'numeric_comparison': 'NOT_RUN',
               'pc1_window_definition': 'accepted_PC1_high_through_ACK1_high_inclusive'}
FIXED_INTS = {'total_cycle_budget': 8000000, 'launches': 1, 'n0_jobs': 1, 'n0_dones': 1,
              'ack0s': 1, 'n0_committed': BYTES, 'pc1_jobs': 1, 'pc1_dones': 1, 'ack1s': 1,
              'qraw_committed_bytes': BYTES, 'qraw_successful_b': QRAW_B_RESPONSES,
              'post_pc': 2, 'post_issued_jobs': 2, 'further_eval_calls_after_ack1': 0,
              'useful_macs': 301989888, 'executed_macs': 301989888,
              'fixed_physical_macs_per_cycle': 4096, 'utilization_numerator': 301989888,
              'matrix_wide_steps': 73728, 'matrix_slice_steps': 589824,
              'binary_add_requests': 12288, 'binary_add_results': 12288,
              'qraw_values': COUNT, 'qraw_bytes': BYTES}
VARIABLE_INTS = frozenset('total_cycles n0_cycles pc1_entry_edge pc1_accept_edge ack1_edge pc1_complete_window_cycles utilization_denominator matrix_stalls n0_read_bytes_pc1 wq_read_bytes_pc1'.split())
COUNT_KEYS = frozenset(TEXT_FIELDS) | frozenset(FIXED_INTS) | VARIABLE_INTS | {'official_raw_numeric_pass', 'full_block_pass', 'pc1_axi'}


def need(ok, code):
    if not ok:
        raise ValueError(code)


def deadline(stop):
    if time.monotonic() >= stop:
        raise TimeoutError('PC01_COMPARISON_DEADLINE')


def identity(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def decode(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'DUPLICATE_JSON_KEY')
            out[key] = value
        return out
    def invalid(unused):
        raise ValueError('NONFINITE_JSON_NUMBER')
    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    need(type(result) is dict, 'JSON_OBJECT')
    return result


def read_fixed(path, cap, stop, expected=None):
    """No-follow directory walk; stable regular fd; hash and consume this buffer."""
    deadline(stop)
    p = Path(path)
    need(p.is_absolute() and '..' not in p.parts and bool(p.name), 'ABSOLUTE_FIXED_PATH')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in p.parent.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        fd = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= cap, 'REGULAR_BOUNDED_FILE')
            if expected is not None:
                need(before.st_size == expected[0], 'FIXED_SIZE')
            chunks, count = [], 0
            while count <= before.st_size:
                deadline(stop)
                chunk = os.read(fd, min(65536, before.st_size + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk); count += len(chunk)
            raw = b''.join(chunks)
            stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            need(len(raw) == before.st_size and stamp(before) == stamp(os.fstat(fd)) ==
                 stamp(os.stat(p.name, dir_fd=parent, follow_symlinks=False)), 'STABLE_SAME_BUFFER')
            if expected is not None:
                need(hashlib.sha256(raw).hexdigest() == expected[1], 'FIXED_HASH')
            deadline(stop)
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def verify_counts(c):
    need(type(c) is dict and set(c) == COUNT_KEYS, 'EXACT_CAPTURE_SCHEMA')
    for key, value in TEXT_FIELDS.items():
        need(type(c[key]) is str and c[key] == value, 'CAPTURE_SCOPE_OR_STATUS')
    need(c['official_raw_numeric_pass'] is None and c['full_block_pass'] is False, 'CAPTURE_NO_NUMERIC_AUTHORITY')
    for key in set(FIXED_INTS) | VARIABLE_INTS:
        need(type(c[key]) is int and 0 <= c[key] < 2**64, 'UINT64_CAPTURE_COUNTER')
    for key, value in FIXED_INTS.items():
        need(c[key] == value, 'FIXED_CAPTURE_COUNTER')
    need(0 < c['n0_cycles'] == c['pc1_entry_edge'] <= c['pc1_accept_edge'] <= c['ack1_edge'] and
         c['total_cycles'] == c['ack1_edge'] + 1 <= c['total_cycle_budget'] and
         c['pc1_complete_window_cycles'] == c['ack1_edge'] - c['pc1_accept_edge'] + 1 and
         c['utilization_denominator'] == 4096 * c['pc1_complete_window_cycles'] and
         c['utilization_numerator'] <= c['utilization_denominator'], 'CAPTURE_CYCLE_RELATIONS')
    a = c['pc1_axi']
    need(type(a) is dict and set(a) == AXI_KEYS, 'EXACT_AXI_SCHEMA')
    for value in a.values():
        need(type(value) is int and 0 <= value < 2**64, 'UINT64_AXI_COUNTER')
    need(a['aws'] == a['bs'] == c['qraw_successful_b'] and
         a['wbeats_expected'] == a['wbeats'] == a['wbeats_committed'] == BYTES // 64 and
         a['strobed_bytes'] == BYTES, 'COMPLETE_WRITE_RETIREMENT')
    need(0 < a['ars'] == a['rlasts'] and a['rbeats_expected'] == a['rbeats'] and
         a['ars'] <= a['rbeats'] <= 256 * a['ars'], 'COMPLETE_READ_RETIREMENT')
    need(c['n0_read_bytes_pc1'] > 0 and c['n0_read_bytes_pc1'] % 64 == 0 and
         c['wq_read_bytes_pc1'] > 0 and c['wq_read_bytes_pc1'] % 64 == 0 and
         c['n0_read_bytes_pc1'] + c['wq_read_bytes_pc1'] <= 64 * a['rbeats'], 'OPERAND_READ_COVERAGE')
    need(c['matrix_stalls'] <= c['total_cycles'] and
         all(a[key] <= c['total_cycles'] for key in ('ar_stall','aw_stall','w_stall','r_stall','b_stall')),
         'STALL_CYCLE_BOUNDS')
    return c


def units(bits, width, unit_exponent):
    f, eb, bias = (23, 8, 127) if width == 32 else (52, 11, 1023)
    exponent = (bits >> f) & ((1 << eb) - 1)
    fraction = bits & ((1 << f) - 1)
    need(exponent != (1 << eb) - 1, 'NONFINITE_ARRAY_VALUE')
    significand = fraction if exponent == 0 else fraction + (1 << f)
    shift = (1 - bias - f if exponent == 0 else exponent - bias - f) - unit_exponent
    value = significand << shift
    return -value if bits >> (width - 1) else value


def widen32(bits):
    exponent, fraction, sign = (bits >> 23) & 255, bits & 0x7fffff, (bits >> 31) << 63
    need(exponent != 255, 'NONFINITE_ARRAY_VALUE')
    if exponent:
        return sign | ((exponent + 896) << 52) | (fraction << 29)
    if not fraction:
        return sign
    n = fraction.bit_length()
    return sign | ((n + 873) << 52) | ((fraction - (1 << (n - 1))) << (53 - n))


def ordered(bits, width):
    sign = 1 << (width - 1)
    return sign - (bits & (sign - 1)) if bits & sign else sign + bits


def ratio(numerator, denominator):
    try:
        value = numerator / denominator
    except OverflowError:
        return {'approx_f64': None, 'overflow_f64': True}
    need(math.isfinite(value), 'NONFINITE_DIAGNOSTIC')
    return {'approx_f64': value, 'overflow_f64': False}


def math_track(actual, reference, width, count, stop):
    need(len(actual) == count * 4 and len(reference) == count * (width // 8) and count > 0, 'TRACK_SHAPE')
    exponent = -149 if width == 32 else -1074
    maximum = total = max_ulp = equal = zero_refs = nonzero_over_zero = 0
    max_index = ulp_index = 0
    rel_index = None
    relative_n, relative_d = 0, 1
    histogram = [0] * 7
    for i, ((a,), (r,)) in enumerate(zip(struct.iter_unpack('<I', actual), struct.iter_unpack('<I' if width == 32 else '<Q', reference))):
        if i % 256 == 0:
            deadline(stop)
        au, ru = units(a, 32, exponent), units(r, width, exponent)
        error = abs(au - ru); total += error
        if error > maximum:
            maximum, max_index = error, i
        abits = a if width == 32 else widen32(a)
        equal += abits == r
        distance = abs(ordered(abits, width) - ordered(r, width))
        if distance > max_ulp:
            max_ulp, ulp_index = distance, i
        bucket = 0 if distance == 0 else 1 if distance == 1 else 2 if distance <= 3 else 3 if distance <= 7 else 4 if distance <= 15 else 5 if distance <= 255 else 6
        histogram[bucket] += 1
        if ru == 0:
            zero_refs += 1; nonzero_over_zero += error != 0
        elif error:
            denominator = abs(ru)
            shift = min((error & -error).bit_length(), (denominator & -denominator).bit_length()) - 1
            numerator, denominator = error >> shift, denominator >> shift
            if numerator * relative_d > relative_n * denominator:
                relative_n, relative_d, rel_index = numerator, denominator, i
        elif rel_index is None:
            rel_index = i
    deadline(stop)
    return {'reference_format': 'FP' + str(width), 'elements': count,
            'actual_format_for_ulp': 'FP32' if width == 32 else 'exact FP32-to-FP64 widening',
            'error_reference_scope': 'RN-even exported mathematical values, not unrounded exact real dots',
            'absolute_error_unit_exponent': exponent,
            'max_abs_error_units_hex': format(maximum, 'x'), 'sum_abs_error_units_hex': format(total, 'x'),
            'max_abs_error': ratio(maximum, 1 << -exponent),
            'mean_abs_error': ratio(total, count << -exponent), 'max_abs_error_index': max_index,
            'bit_equal_values': equal, 'max_ulp': max_ulp, 'max_ulp_index': ulp_index,
            'ulp_histogram_0_1_2to3_4to7_8to15_16to255_over255': histogram,
            'ulp_signed_zero_policy': 'positive and negative zero have distance zero; bit equality remains separate',
            'max_relative_over_nonzero_references': None if zero_refs == count else {**ratio(relative_n, relative_d),
                'numerator_hex': format(relative_n, 'x'), 'denominator_hex': format(relative_d, 'x'), 'index': rel_index},
            'zero_reference_count': zero_refs, 'nonzero_error_over_zero_reference_count': nonzero_over_zero}


def typed_track(actual, reference, count, stop):
    need(len(actual) == len(reference) == 4 * count, 'TYPED_SHAPE')
    equal, first = 0, None
    for i, ((a,), (r,)) in enumerate(zip(struct.iter_unpack('<I', actual), struct.iter_unpack('<I', reference))):
        if i % 256 == 0:
            deadline(stop)
        units(a, 32, -149); units(r, 32, -149)
        if a == r:
            equal += 1
        elif first is None:
            first = i
    deadline(stop)
    return {'elements': count, 'bit_equal_values': equal, 'mismatch_values': count - equal,
            'bit_exact': equal == count, 'hash_exact': identity(actual) == identity(reference),
            'first_mismatch_index': first, 'signed_zero_compared_bitwise': True}


def compare(capture_root, reference_root, reference_receipt, *, shared_stop):
    need(type(shared_stop) in (int, float) and math.isfinite(shared_stop), 'FINITE_SHARED_DEADLINE')
    started = time.monotonic(); stop = min(started + SECONDS, shared_stop); deadline(stop)
    capture, references, receipt = Path(capture_root), Path(reference_root), Path(reference_receipt)
    need(receipt == references / 'RESULT.json', 'FIXED_REFERENCE_RECEIPT_LEAF')
    buffers, requests = {}, {}
    def take(name, path, cap, pin=None):
        raw = read_fixed(path, cap, stop, pin); buffers[name] = raw
        requests[name] = (path, cap, (len(raw), hashlib.sha256(raw).hexdigest()))
        return raw
    counts = verify_counts(decode(take('capture_counts', capture/'counts.json', 16384)))
    take('fresh_pc0_n0', capture/'actual_n0.f32le', BYTES, (BYTES, N0_SHA))
    actual = take('actual_qraw', capture/'actual_qraw.f32le', BYTES)
    need(len(actual) == BYTES, 'FULL_QRAW_LENGTH')
    result = decode(take('reference_receipt', receipt, 16384, RECEIPT_PIN))
    need(result['status'] == 'COMPLETE_TWO_MODEL_DIAGNOSTIC' and type(result['elements']) is int and result['elements'] == COUNT and
         result['official_raw_numeric_pass'] is None and result['application_accuracy_pass'] is None and
         result['typed_recipe_bit_exact_to_rtl'] is None and result['rtl_executed'] is False and result['nonfinite_count'] == 0,
         'REFERENCE_RECEIPT_SCOPE')
    for leaf, pin in REFERENCES.items():
        take(leaf, references/leaf, pin[0], pin)
    need(result['typed_fp32_sha256'] == REFERENCES['qraw.typed.f32le'][1] and
         result['math_fp32_sha256'] == REFERENCES['qraw.math.f32le'][1] and
         result['math_fp64_sha256'] == REFERENCES['qraw.math.f64le'][1], 'REFERENCE_RECEIPT_IDENTITIES')
    typed = typed_track(actual, buffers['qraw.typed.f32le'], COUNT, stop)
    math32 = math_track(actual, buffers['qraw.math.f32le'], 32, COUNT, stop)
    math64 = math_track(actual, buffers['qraw.math.f64le'], 64, COUNT, stop)
    for name, (path, cap, pin) in requests.items():
        need(read_fixed(path, cap, stop, pin) == buffers[name], 'POST_COMPARISON_BYTES_CHANGED')
    deadline(stop)
    observation = {'schema': 'PC01_THREE_REFERENCE_DATA_OBSERVATION_V1', 'status': 'COMPLETE_DATA_OBSERVATION_ONLY',
            'elements': COUNT, 'shape': [128,1536], 'seconds': time.monotonic()-started,
            'local_seconds_cap': SECONDS, 'shared_deadline_extended': False,
            'capture_counts': counts, 'identities': {name: identity(raw) for name,raw in buffers.items()},
            'typed_reference': typed, 'mathematical_fp32': math32, 'mathematical_fp64': math64,
            'qualification': {'caller_native_exit_cleanup_source_association_required': True,
                'completion_payload_independently_observed_by_consumer': False,
                'completion_control_flow_evidence': 'fixed reviewed driver success path plus caller-associated native exit0',
                'fresh_process_and_same_RAM_claim_requires_caller_provenance': True},
            'official_raw_numeric_pass': None, 'application_accuracy_pass': None,
            'typed_recipe_bit_exact_to_rtl': None, 'full_block_pass': False, 'new_tolerance': None}
    finished = time.monotonic()
    if finished >= stop:
        raise TimeoutError('PC01_COMPARISON_DEADLINE')
    observation['seconds'] = finished - started
    return observation
