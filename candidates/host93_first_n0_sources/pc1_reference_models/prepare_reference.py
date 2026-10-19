"""Pinned SOURCE preparation only. No subprocess, compiler, native or full-model dispatch."""
import hashlib
import json
import os
from pathlib import Path
import stat
import types


class Rejected(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Rejected(code)


# Filled from the final candidate bytes before SOURCE freeze; never learned from a supplied manifest.
LOCAL_PINS = {'exact_oracle.py': (3605, 'd4e5554f9c73a6a3f45a73bb62c53ccc5988deb97d8e20e74be9fae4516a7e6f'), 'SOURCE_PINS.json': (4648, '5ed07e1f048e46e3518e6178c78f19604ca3f7019800470050554afacd8f344e'), 'pc1_reference_main.cpp': (11125, '6c286c0ed94e077405057b9ac4b135acd7a48f946f59afba7050b05199893433'), 'exact_math.hpp': (5383, 'dcb9d9cde6ec30dc2a336748dd9b22a49b78955feced976213b7f64ff97c7d0b'), 'dot16.inc': (1078, '175a8c3ff32287c6403a9bdf83c91d45249b6824cf4633753fcccb65c48d4ad6'), 'sha256.hpp': (4541, '7a47104d65a6366cf5eaf38772abea38fcc58c0cfb5a882b1084cb7efd8ece8e')}
INPUTS = {
    'independent_n0': (786432, '3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f'),
    'accepted_n0_identity_only': (786432, '3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f'),
    'wq': (4718592, 'ad7ce2dae58deb01656348a6ee2bd6919ed6c2bc83f31b88eed75381cd718b72'),
}
NATIVE_FILES = ('pc1_reference_main.cpp', 'exact_math.hpp', 'dot16.inc', 'sha256.hpp')


def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def canonical_file(path):
    p = Path(path)
    require(p.is_absolute() and '..' not in p.parts, 'ABSOLUTE_CANONICAL_REQUIRED')
    require(p.resolve(strict=True) == p and p.is_file(), 'FILE_REQUIRED')
    require(not any(q.is_symlink() for q in (p, *p.parents)), 'SYMLINK_FORBIDDEN')
    return p


def fixed_bytes(path, pin):
    p = Path(path)
    size, digest = pin
    require(p.is_absolute() and '..' not in p.parts and type(size) is int and
            0 <= size <= 16 * 1024**2, 'BOUNDED_FIXED_FILE')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in p.parent.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        f = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(f)
            require(stat.S_ISREG(before.st_mode) and before.st_size == size, 'FIXED_FILE_SIZE')
            chunks, count = [], 0
            while count <= size:
                chunk = os.read(f, min(65536, size + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
            data = b''.join(chunks)
            stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            require(identity(data) == {'bytes': size, 'sha256': digest} and
                    stamp(before) == stamp(os.fstat(f)) ==
                    stamp(os.stat(p.name, dir_fd=fd, follow_symlinks=False)), 'BYTE_IDENTITY')
            return data
        finally:
            os.close(f)
    finally:
        os.close(fd)


def local_sources(source_dir):
    root = Path(source_dir)
    return {name: fixed_bytes(root / name, pin) for name, pin in LOCAL_PINS.items()}


def load_oracle(source_dir):
    data = fixed_bytes(Path(source_dir) / 'exact_oracle.py', LOCAL_PINS['exact_oracle.py'])
    module = types.ModuleType('pc1_exact_small_oracle')
    exec(compile(data, 'exact_oracle.py', 'exec'), module.__dict__)
    return module


def verify_repository(repo, source_dir):
    data = local_sources(source_dir)
    pins = json.loads(data['SOURCE_PINS.json'])
    require(pins['schema'] == 1, 'SOURCE_SCHEMA')
    originals = {}
    for name, pin in pins['sources'].items():
        originals[name] = fixed_bytes(Path(repo) / name, (pin['bytes'], pin['sha256']))
    for local, original in pins['exact_copied_sources'].items():
        require(data[local] == originals[original], 'ORIGINAL_COPY_CHANGED')
    return data, originals


def prepare(repo, source_dir, independent_n0, accepted_n0, wq, destination):
    """Future admitted run: identity-check all three inputs; only independent bytes feed models.

    Caller must separately bind the accepted prior N0 receipt and runtime/tool admission.
    A passed accepted_n0 hash does not resume old RAM or authorize another model/RTL run.
    """
    sources, originals = verify_repository(repo, source_dir)
    paths = {'independent_n0': independent_n0, 'accepted_n0_identity_only': accepted_n0, 'wq': wq}
    raw = {name: fixed_bytes(path, INPUTS[name]) for name, path in paths.items()}
    require(raw['independent_n0'] == raw['accepted_n0_identity_only'], 'ACCEPTED_N0_DIFFERENT')
    dest = Path(destination)
    require(dest.is_absolute() and '..' not in dest.parts and not dest.exists(), 'FRESH_DESTINATION_REQUIRED')
    require(dest.parent.resolve(strict=True) == dest.parent and
            not any(p.is_symlink() for p in (dest.parent, *dest.parents)), 'DESTINATION_PARENT')
    # Finish admission before writing any output. Newly created work remains private evidence on failure.
    dest.mkdir()
    for leaf in ('source', 'inputs', 'outputs'):
        (dest / leaf).mkdir()
    for name in NATIVE_FILES:
        (dest / 'source' / name).write_bytes(sources[name])
    (dest / 'inputs' / 'independent_n0.f32le').write_bytes(raw['independent_n0'])
    (dest / 'inputs' / 'wq.bf16le').write_bytes(raw['wq'])
    require(verify_repository(repo, source_dir) == (sources, originals), 'SOURCE_POSTFLIGHT')
    for name, path in paths.items():
        require(fixed_bytes(path, INPUTS[name]) == raw[name], 'INPUT_POSTFLIGHT')
    report = {
        'schema': 1, 'status': 'PREPARED_NOT_EXECUTED', 'official_raw_numeric_pass': None,
        'source_identities': {k: identity(v) for k, v in sources.items()},
        'repository_identities': {k: identity(v) for k, v in originals.items()},
        'inputs': {k: identity(v) for k, v in raw.items()},
        'accepted_n0_used_as_reference': False, 'accepted_n0_checked_for_identity_only': True,
        'prior_process_resumed': False, 'bias_used': False, 'output_bf16_rounded': False,
        'native_executed': False, 'full_model_executed': False, 'rtl_executed': False,
    }
    (dest / 'PREPARED.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def verify_complete_outputs(directory):
    root = Path(directory)
    rp = canonical_file(root / 'RESULT.json')
    require(rp.stat().st_size <= 65536, 'RESULT_SIZE')
    result_bytes = rp.read_bytes()
    require(len(result_bytes) <= 65536, 'RESULT_SIZE')
    r = json.loads(result_bytes)
    require(r['schema'] == 1 and r['status'] == 'COMPLETE_TWO_MODEL_DIAGNOSTIC' and
            type(r['elements']) is int and r['elements'] == 196608 and
            r['logical_macs'] == 301989888 and r['official_raw_numeric_pass'] is None and
            r['application_accuracy_pass'] is None and r['typed_recipe_bit_exact_to_rtl'] is None and
            r['rtl_executed'] is False and r['nonfinite_count'] == 0, 'RESULT_SCOPE')
    outputs = {}
    for filename, size, key in (
        ('qraw.math.f32le', 786432, 'math_fp32_sha256'),
        ('qraw.math.f64le', 1572864, 'math_fp64_sha256'),
        ('qraw.typed.f32le', 786432, 'typed_fp32_sha256'),
    ):
        data = fixed_bytes(root / filename, (size, r[key]))
        width = 8 if filename.endswith('f64le') else 4
        exponent_mask = 0x7ff0000000000000 if width == 8 else 0x7f800000
        for offset in range(0, len(data), width):
            require(int.from_bytes(data[offset:offset+width], 'little') & exponent_mask != exponent_mask,
                    'OUTPUT_NONFINITE')
        outputs[filename] = identity(data)
    hist = r['ulp_histogram_0_1_2to3_4to7_8to15_16to255_over255']
    require(len(hist) == 7 and all(type(x) is int and x >= 0 for x in hist) and sum(hist) == 196608,
            'HISTOGRAM_COVERAGE')
    require(type(r['bit_equal_to_math_fp32']) is int and 0 <= r['bit_equal_to_math_fp32'] <= hist[0],
            'BIT_EQUAL_COUNT')
    return {'result_identity': identity(result_bytes), 'outputs': outputs, 'metrics': r,
            'supervisor_success_still_required': True, 'full_comparison_to_rtl': False}
