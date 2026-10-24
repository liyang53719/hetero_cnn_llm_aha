"""One bounded pure-metadata test pass; never calls prepare_successor or writes assembly."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import resource
import time

resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
started = time.monotonic()
source = Path(__file__).with_name('prepare_successor.py')
with source.open('rb') as stream:
    before = os.fstat(stream.fileno())
    assert before.st_size <= 2 * 1024 * 1024
    raw = stream.read(2 * 1024 * 1024 + 1)
    after = os.fstat(stream.fileno())
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    assert tuple(getattr(before, k) for k in fields) == tuple(getattr(after, k) for k in fields)
tree = ast.parse(raw, filename=str(source))
assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) and
               any(x.name.split('.')[0] in ('subprocess', 'ctypes', 'numpy', 'torch') for x in n.names)
               for n in ast.walk(tree))
namespace = {'__name__': '_synthetic_successor_metadata_only', '__file__': str(source)}
exec(compile(tree, str(source), 'exec', dont_inherit=True, optimize=0), namespace)
pin, encode = namespace['pin'], namespace['encoded']
validate = namespace['validate_runtime']
validate_profile = namespace['validate_profile_manifest']
snapshot = Path('/synthetic/fixed-snapshot')
old_git, old_profile = '/synthetic/original/git', '/synthetic/original/profile'
git_names, profile_names = namespace['GIT_NAMES'], namespace['PROFILE_NAMES']
mapping = {old_git + '/' + n: str(snapshot / 'git' / n) for n in git_names}
mapping.update({old_profile + '/' + n: str(snapshot / 'profile' / n) for n in profile_names})
profile_pins = {n: pin(('synthetic:' + n).encode()) for n in profile_names}
profile_raw = encode({'schema': 1, 'files': {n: s for n, s in profile_pins.items() if n != 'MANIFEST.json'}})
profile_pins['MANIFEST.json'] = pin(profile_raw)
files = {'/synthetic/unrelated/' + str(i): pin(('item:' + str(i)).encode()) for i in range(1620)}
files.update({old_git + '/' + n: pin(('git:' + n).encode()) for n in git_names})
files.update({old_profile + '/' + n: s for n, s in profile_pins.items()})
old = {'schema': 1, 'status': 'UNCHANGED', 'files': files,
       'git_environment': {'GIT_DIR': old_git, 'GIT_CONFIG_NOSYSTEM': '1'},
       'git_profile_root': old_profile,
       'git_profile_manifest_sha256': profile_pins['MANIFEST.json']['sha256'],
       'total_file_bytes': sum(s['bytes'] for s in files.values()),
       'unrelated': {'enabled': False, 'count': 1}}
new = copy.deepcopy(old)
new['files'] = {mapping.get(n, n): s for n, s in files.items()}
new['git_environment']['GIT_DIR'] = str(snapshot / 'git')
new['git_profile_root'] = str(snapshot / 'profile')
snapshot_files = {str(Path(n).relative_to(snapshot)): new['files'][n] for n in mapping.values()}
snapshot_files['RUNTIME_PINS.json'] = pin(encode(new))
receipt = {'old_to_new_path': mapping, 'unchanged_count': 1620, 'runtime_count': 1638,
           'snapshot_files': snapshot_files, 'profile_files': profile_pins}
results = []


def run_case(name, change=None, profile=False, accepted=False):
    a, b, r, p = copy.deepcopy(old), copy.deepcopy(new), copy.deepcopy(receipt), profile_raw
    if change:
        changed = change(a, b, r, p)
        if changed is not None:
            p = changed
    try:
        if profile:
            validate_profile(p, r, b)
        else:
            assert validate(a, b, r, snapshot) == mapping
    except (ValueError, KeyError, TypeError) as error:
        assert not accepted, (name, str(error))
        results.append({'case': name, 'result': 'REJECTED_AS_REQUIRED', 'reason': str(error)})
    else:
        assert accepted, name + ' unexpectedly accepted'
        results.append({'case': name, 'result': 'ACCEPTED_AS_REQUIRED'})


def half(a, b, r, p):
    for source_name, target_name in sorted(mapping.items())[:9]:
        b['files'][source_name] = b['files'].pop(target_name)


def migrated_payload_changed(name):
    def mutate(a, b, r, p):
        replacement = pin(b'changed synthetic dependency')
        r['snapshot_files'][name] = replacement
        b['files'][str(snapshot / name)] = replacement
        if name.startswith('profile/'):
            r['profile_files'][name[8:]] = replacement
        b['total_file_bytes'] = sum(s['bytes'] for s in b['files'].values())
    return mutate


run_case('exact_18_migrations_and_1620_unchanged', accepted=True)
run_case('exact_profile_manifest_association', profile=True, accepted=True)
run_case('nongenerated_git_dependency_changed', migrated_payload_changed('git/HEAD'))
run_case('nongenerated_profile_dependency_changed', migrated_payload_changed('profile/README.md'))
run_case('half_migration', half)
run_case('unrelated_runtime_pin_changed', lambda a, b, r, p: b['files']['/synthetic/unrelated/0'].update(sha256='0' * 64))
run_case('unknown_runtime_pin_added', lambda a, b, r, p: b['files'].update({'/synthetic/unknown': pin(b'x')}))
run_case('runtime_pin_missing', lambda a, b, r, p: (b['files'].pop('/synthetic/unrelated/0'), None)[1])
run_case('mapping_missing', lambda a, b, r, p: (r['old_to_new_path'].pop(next(iter(mapping))), None)[1])
run_case('mapping_extra', lambda a, b, r, p: r['old_to_new_path'].update({'/unknown': '/synthetic/fixed-snapshot/git/extra'}))
run_case('mapping_wrong_target', lambda a, b, r, p: r['old_to_new_path'].update({next(iter(mapping)): '/other/git/HEAD'}))
run_case('runtime_count_wrong', lambda a, b, r, p: r.update(runtime_count=1637))
run_case('unchanged_count_wrong', lambda a, b, r, p: r.update(unchanged_count=1619))
run_case('new_total_bytes_wrong', lambda a, b, r, p: b.update(total_file_bytes=b['total_file_bytes'] + 1))
run_case('old_total_bytes_wrong', lambda a, b, r, p: a.update(total_file_bytes=a['total_file_bytes'] + 1))
run_case('runtime_profile_manifest_sha_wrong', lambda a, b, r, p: b.update(git_profile_manifest_sha256='0' * 64))
run_case('old_git_dir_retained', lambda a, b, r, p: b['git_environment'].update(GIT_DIR=old_git))
run_case('old_profile_root_retained', lambda a, b, r, p: b.update(git_profile_root=old_profile))
run_case('snapshot_pin_missing', lambda a, b, r, p: (r['snapshot_files'].pop('git/HEAD'), None)[1])
run_case('snapshot_pin_extra', lambda a, b, r, p: r['snapshot_files'].update({'git/unknown': pin(b'x')}))
run_case('profile_pin_missing', lambda a, b, r, p: (r['profile_files'].pop('README.md'), None)[1])
run_case('profile_pin_extra', lambda a, b, r, p: r['profile_files'].update({'unknown': pin(b'x')}))
run_case('unrelated_runtime_status_changed', lambda a, b, r, p: b.update(status='CHANGED'))
run_case('unrelated_runtime_numeric_type_changed', lambda a, b, r, p: b.update(schema=True))
run_case('runtime_pin_bytes_boolean', lambda a, b, r, p: b['files']['/synthetic/unrelated/0'].update(bytes=True))
run_case('profile_manifest_files_disagree', lambda a, b, r, p: encode({'schema': 1, 'files': {}}), profile=True)
run_case('profile_manifest_schema_boolean', lambda a, b, r, p: encode({'schema': True, 'files': json.loads(p)['files']}), profile=True)
run_case('profile_manifest_self_pin_wrong', lambda a, b, r, p: r['profile_files']['MANIFEST.json'].update(sha256='0' * 64), profile=True)
run_case('profile_runtime_sha_wrong', lambda a, b, r, p: b.update(git_profile_manifest_sha256='0' * 64), profile=True)
elapsed = time.monotonic() - started
assert elapsed < 10
print(json.dumps({'status': 'PASS_PURE_SYNTHETIC_ONLY', 'tests': results, 'count': len(results),
    'source_pin': pin(raw), 'wall_seconds': elapsed, 'max_address_space_bytes': 128 * 1024 * 1024,
    'cpu_affinity_count': len(os.sched_getaffinity(0)), 'cpu_limit_seconds': 10,
    'materialization_executed': False, 'git_executed': False, 'preflight_executed': False,
    'native_executed': False, 'DUT_imported': False, 'real_runtime_or_payload_files_opened': 0}, indent=2, sort_keys=True))
