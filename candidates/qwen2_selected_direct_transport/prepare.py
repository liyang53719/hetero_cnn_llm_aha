"""Source-only selected direct route over the already-reviewed QK16 overlay."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = 'candidates/qwen2_resident_matrix/'
PUBLIC = (BASE + 'ffn_public/execute_numeric.py', BASE + 'ffn_public/fullgraph_execution.py')
PUBLIC_POST = ('cdf203f9e7113db7fb29dd290ea6355adf3f7df86e145e5828daf13a5ac51b73',
               'bdc4218fcc6136c1c1c2b6d9c15338b539e4b6abe46b96bd6baeb93379a6e9ab')
GUARDED_POST = 'e67f3bf53dec946e0ee423f591ecf345f52636ea00fd8796d17312df17a714f8'
RUNTIME = BASE + 'production_qk16_model/direct_transport.py'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    path = Path(path).absolute()
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('regular non-symlink file required: ' + str(path))
    return path.read_bytes()


def verify(source_root):
    pins = json.loads(read(HERE / 'INPUT_PINS.json'))
    sources = {}
    for name, expected in pins['sources'].items():
        raw = read(Path(source_root) / name)
        if len(raw) != expected['bytes'] or sha(raw) != expected['sha256']:
            raise ValueError('fixed input source differs: ' + name)
        sources[name] = raw
    own = json.loads(read(HERE / 'CODE_PINS.json'))
    if set(own) != {'direct_transport.py', 'direct_guard.patch'}:
        raise ValueError('exact direct runtime pin set required')
    for name, expected in own.items():
        if sha(read(HERE / name)) != expected:
            raise ValueError('direct candidate source differs: ' + name)
    return pins, sources


def compose(source_root, destination):
    pins, sources = verify(source_root)
    path = Path(source_root) / 'candidates/qwen2_selected_scala_model/prepare.py'
    spec = importlib.util.spec_from_file_location('_fixed_selected_schedule_prepare', path)
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)  # Verified stdlib source-only assembler, not model imports.
    destination = Path(destination).absolute()
    previous = prior.compose(source_root, destination)
    (destination / 'COMPOSITION.json').rename(destination / 'SCHEDULE_COMPOSITION.json')
    for name in PUBLIC:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(sources[name])
    logs = [prior.patch(destination, sources[BASE + 'raw_kv_public/public_execution.patch'])]
    if tuple(sha(read(destination / name)) for name in PUBLIC) != PUBLIC_POST:
        raise ValueError('existing public raw-off patch postimages differ')
    logs.append(prior.patch(destination, read(HERE / 'direct_guard.patch')))
    if sha(read(destination / PUBLIC[0])) != GUARDED_POST:
        raise ValueError('selected direct public guard postimage differs')
    (destination / RUNTIME).write_bytes(read(HERE / 'direct_transport.py'))
    names = (*previous['composed_files'], *PUBLIC, RUNTIME)
    files = {name:sha(read(destination / name)) for name in sorted(names)}
    report = dict(schema=1, status='TEMP_DIRECT_OWNER_DRIVER_OVERLAY_ONLY',
        source_commit=pins['source_commit'], source_tree=pins['source_tree'],
        composed_files=files, patch_logs=logs, original_schedule_files_unchanged=True,
        raw_kv_enabled=False, additional_payload_or_cache_allocation=False,
        full_numeric_admission=False, native_execution=False, scala_or_rtl_execution=False,
        limitation='This is not a complete full-block profile/source/input freeze. Existing full-run admission is unchanged.')
    (destination / 'DIRECT_COMPOSITION.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(compose(args.source_root, args.output), sort_keys=True, indent=2))
