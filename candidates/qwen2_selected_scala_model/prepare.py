"""Source-only owner overlay, not a replacement for any full-run admission gate.

Compose the existing owner.patch, then the narrow selected-owner admission patch.
No model imports, native libraries, weights, full-run receipts, or Scala build.
The output is a partial overlay, not a qualified full-model executable checkout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
BASE = 'candidates/qwen2_resident_matrix/'
CANDIDATE = 'candidates/qwen2_selected_scala_model/'
TARGETS = (BASE + 'ffn_attention/attention_owner.py', BASE + 'official_bf16/owners.py')
BASE_POST = ('ae5fcc65b0d238e8b3697d563ad5fc309ee17e72a078f39cfd841838c96bf929',
             '0c87797587281b4e7f23663242e947ffe4157db9a644e788d67eb5c9045c50c1')
SELECTED_POST = '2f8a6f9657771fa7d4c267a5151e1c739164e44c4768bacd9385275029625cdb'
RUNTIME = ('schedule.py', 'routing.py', 'entry.py')
HOOKS = BASE + 'attention_packed_owner/hooks.py'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('regular non-symlink source required: ' + str(path))
    return path.read_bytes()


def verified_sources(source_root):
    pins = json.loads(regular(HERE / 'INPUT_PINS.json'))
    result = {}
    for name, pin in pins['sources'].items():
        raw = regular(Path(source_root) / name)
        if len(raw) != pin['bytes'] or digest(raw) != pin['sha256']:
            raise ValueError('fixed source pin mismatch: ' + name)
        result[name] = raw
    return pins, result


def patch(destination, body):
    run = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'], cwd=destination,
                         input=body, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    log = run.stdout.decode('utf8', errors='strict')
    if run.returncode or any(word in log.lower() for word in ('offset', 'fuzz', 'failed', 'reversed')):
        raise ValueError('exact patch composition failed: ' + log)
    return log


def compose(source_root, destination):
    pins, sources = verified_sources(source_root)
    own = json.loads(regular(HERE / 'CODE_PINS.json'))
    expected_names = {CANDIDATE + 'selected_hooks.patch',
                      CANDIDATE + 'selected_owner.patch',
                      *(CANDIDATE + n for n in RUNTIME)}
    if set(own) != expected_names:
        raise ValueError('exact runtime source pin set required')
    own_sources = {}
    for name, expected in own.items():
        raw = regular(HERE.parents[1] / name)
        if digest(raw) != expected:
            raise ValueError('candidate source pin mismatch: ' + name)
        own_sources[name] = raw
    destination = Path(destination).absolute()
    if destination.exists() or any(p.is_symlink() for p in destination.parents):
        raise ValueError('fresh non-symlink destination required')
    destination.mkdir(parents=True)
    for name in TARGETS:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(sources[name])
    logs = [patch(destination, sources[BASE + 'attention_packed_owner/owner.patch'])]
    if tuple(digest(regular(destination / name)) for name in TARGETS) != BASE_POST:
        raise ValueError('original owner.patch postimages differ')
    logs.append(patch(destination, own_sources[CANDIDATE + 'selected_owner.patch']))
    if digest(regular(destination / TARGETS[0])) != SELECTED_POST:
        raise ValueError('selected owner postimage differs')
    target = destination / HOOKS
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(sources[HOOKS])
    logs.append(patch(destination, own_sources[CANDIDATE + 'selected_hooks.patch']))
    if digest(regular(target)) != 'e4aed930d1a3f1742c95eaf1ec92350ef5c142ed276fbacb7821d473b4cf202d':
        raise ValueError('selected hooks postimage differs')
    for name in (BASE + 'production_qk16_model/' + n for n in RUNTIME):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(own_sources[CANDIDATE + Path(name).name])
    files = {str(path.relative_to(destination)):digest(regular(path))
             for path in sorted(destination.rglob('*')) if path.is_file()}
    report = dict(schema=1, status='TEMP_OWNER_OVERLAY_ONLY', source_commit=pins['source_commit'],
        source_tree=pins['source_tree'], selected_scala_postimages=pins['selected_scala_postimages'],
        composed_files=files, patch_logs=logs, full_numeric_admission=False,
        scala_or_rtl_execution=False, inherited_historical_pass=False,
        limitation='Existing full M128 source/hash admission remains unchanged and rejects this changed closure. A separate reviewed profile/input freeze is required.')
    (destination / 'COMPOSITION.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(compose(args.source_root, args.output), sort_keys=True, indent=2))
