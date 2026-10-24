"""Prepare an isolated head0/M64 plan from CLI-supplied private inputs; never execute it.

Uses stdlib only. Hashes the admitted source/runtime closure, snapshots source and
slices data, and pins the new helper code. No Git command, native load, or build.
The generated plan contains local paths and must remain private, outside Git.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

HERE = Path(__file__).resolve().parent
CHECKPOINT = HERE.parents[2]


def need(ok, why):
    if not ok:
        raise ValueError(why)


def signature(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def checked(path, expected=None, capture=False):
    path = Path(path)
    resolved = path.resolve(strict=True)
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode), 'regular input required')
        need(before.st_size <= 64 << 20, 'input extent cap')
        h = hashlib.sha256()
        data = bytearray() if capture else None
        while block := stream.read(1 << 20):
            h.update(block)
            if capture:
                data.extend(block)
        after = os.fstat(stream.fileno())
    need(signature(before) == signature(after) == signature(path.stat()) and
         path.resolve(strict=True) == resolved, 'input changed while hashing')
    pin = {'bytes': before.st_size, 'sha256': h.hexdigest()}
    if expected is not None:
        need(pin == expected, 'input digest/extent mismatch: ' + path.name)
    return dict(pin, resolved=str(resolved)), bytes(data) if capture else None


def create(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('repository', 'runtime-site', 'python', 'vector-library',
                   'vector-metadata', 'compiler', 'saved-prep', 'saved-pins',
                   'saved-progress', 'official-output', 'output'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--cpu', type=int, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    runtime = args.runtime_site.resolve(strict=True)
    out = args.output.resolve()
    for protected in (root, runtime, CHECKPOINT):
        need(out != protected and protected not in out.parents,
             'output must be outside source/runtime/checkpoint trees')
    need(not os.path.lexists(out), 'fresh preparation directory required')
    need(args.cpu in os.sched_getaffinity(0), 'CPU not allowed')
    spec = json.loads((HERE / 'pins.json').read_text())
    inputs = {}

    def admit(path, expected=None, capture=False):
        path = Path(path).absolute()
        pin, raw = checked(path, expected, capture)
        inputs[str(path)] = pin
        return raw

    # Check all dependencies before creating any output.
    source_data = {}
    for relative, pin in spec['sources'].items():
        source_data[relative] = admit(root / relative, pin, capture=True)
    runtime_rows = []
    for name in spec['runtime']['site_tree']['roots']:
        directory = runtime / name
        need(directory.is_dir() and not directory.is_symlink(), 'runtime subtree')
        for path in sorted(directory.rglob('*')):
            if '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            need(not path.is_symlink(), 'runtime symlink not admitted')
            if not path.is_file():
                continue
            admit(path)
            pin = inputs[str(path)]
            runtime_rows.append([path.relative_to(runtime).as_posix(), pin['bytes'], pin['sha256']])
    encoded = json.dumps(sorted(runtime_rows), separators=(',', ':'), ensure_ascii=True).encode()
    tree = spec['runtime']['site_tree']
    need(len(runtime_rows) == tree['files'] and hashlib.sha256(encoded).hexdigest() ==
         tree['canonical_sha256'], 'runtime tree digest mismatch')
    for name, path in (('python', args.python), ('vector_library', args.vector_library),
                       ('vector_metadata', args.vector_metadata), ('compiler', args.compiler)):
        admit(path, spec['runtime'][name])
    artifact = spec['artifacts']
    prep = admit(args.saved_prep, artifact['actual/cold128.prep.actual.fp32le'], True)
    reference = admit(args.official_output, artifact['official_chunk_m128.bf16le'], True)
    admit(args.saved_pins, artifact['metadata/prior_pins.json'])
    progress = json.loads(admit(args.saved_progress, artifact['metadata/actual_progress.json'], True))
    need([(x['phase'], x['role']) for x in progress['commands']] ==
         [('cold128', role) for role in ('input_norm', 'qkv', 'z', 'ab', 'conv_silu', 'prep')],
         'original six-terminal provenance required')
    need(all(x['terminal_accepted'] is True and x['complete'] is True and x['status'] is None
             for x in progress['commands']), 'original terminal completion required')
    need(len(prep) == 128 * 25600 and len(reference) == 128 * 16 * 128 * 2, 'input extents')
    for name in ('prepare_chunk.py', 'chunk_child.py', 'launch_chunk.py', 'compare_chunk.py', 'pins.json'):
        admit(HERE / name)
    os.umask(0o077)
    out.mkdir(mode=0o700)
    for relative, raw in source_data.items():
        target = out / 'source_snapshot' / relative
        create(target, raw)
        admit(target, spec['sources'][relative])
    saved_slice = out / 'inputs/saved_prep_first64.fp32le'
    ref_slice = out / 'reference/official_head0_first64.bf16le'
    create(saved_slice, prep[:64 * 25600])
    create(ref_slice, b''.join(reference[(r * 16 * 128) * 2:(r * 16 * 128 + 128) * 2]
                              for r in range(64)))
    admit(saved_slice, artifact['saved_prep_first64.fp32le'])
    admit(ref_slice, artifact['official_head0_first64.bf16le'])
    plan = {
        'schema': 'qwen35_head0_m64_isolated_v1',
        'python': str(args.python.resolve(strict=True)), 'repository': str(root),
        'numpy_site': str(runtime), 'vector_library': str(args.vector_library.resolve(strict=True)),
        'cleanup_helper': str(root / 'scripts/idma_source_export_20261017/strict_cleanup.py'),
        'cpu': args.cpu, 'environment': spec['environment'], 'inputs': inputs,
        'source_commit': spec['source_commit'], 'source_scope': spec['source_scope'],
        'saved_prep_slice': str(saved_slice), 'saved_prep_slice_sha256': inputs[str(saved_slice)]['sha256'],
        'reference_directory': str(ref_slice.parent), 'reference_slice': str(ref_slice),
        'reference_paths': [str(args.official_output.resolve(strict=True)), str(ref_slice)],
        'run_directory': str(out / 'run'), 'policy': spec['policy'], 'limits': spec['limits'],
        'historical_input_pin_count': spec['historical_input_pin_count'],
        'historical_plan_sha256': spec['historical_plan_sha256'],
        'note': 'Relocatable helper adaptation, not the original plan or an original-run continuation.',
    }
    plan['child_argv'] = [plan['python'], '-I', '-S', '-B', '-X',
                          'pycache_prefix=' + str(out / 'run/pycache'),
                          str(HERE / 'chunk_child.py'), str(out / 'PLAN.json')]
    for name, pin in inputs.items():
        current, _ = checked(name)
        need(current == pin, 'input changed after preparation')
    raw = (json.dumps(plan, sort_keys=True, indent=2) + '\n').encode()
    create(out / 'PLAN.json', raw)
    print(json.dumps({'status': 'PREPARED_NOT_EXECUTED', 'plan_sha256': hashlib.sha256(raw).hexdigest(),
                      'input_pins': len(inputs), 'historical_input_pins': 1101}, sort_keys=True))


if __name__ == '__main__':
    main()
