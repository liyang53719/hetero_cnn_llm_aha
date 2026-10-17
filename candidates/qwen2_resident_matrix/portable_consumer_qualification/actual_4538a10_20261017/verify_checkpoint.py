"""Offline metadata verifier. Never load arithmetic, native libraries, or run CI."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
LAUNCH = '4538a108904789de619a7a3bdb0b741fb8fc28c0'
RUN = '38991969943'
LIBRARY = 'd059c8d9bc04d964b15790fdcfc411f23303dd25b0e6294ff38b688f1cd86624'
CONTRACT = '287565c9af2ad155fb14a066fc007229b47be0296e73e743dfc479286f894ebf'
EXACT = {
    'summary.json': (2099, 'e5cdbdee545b329aeb65b4c8a78877d844e16f6f87d65143b2333bebd8bf8152'),
    'identities.json': (37926, '3ca5852da5ab1156e5a6f476907b2f0d5bb02dc851ad55e0d4295d863cd4be46'),
    'source_hashes.json': (17205, '9ccad51b071829ea63483c2eacd8caa3d92fc2bf008c5fcaa151085233a67801'),
    'frozen_input_contract.json': (18132, CONTRACT),
    'frozen_contract.py': (14902, '23ea59a4a398555a0f025e3ac9e67cd6188dc093839ef954117f4485e090c818'),
}
FILES = set(EXACT) | {'README_CN.md', 'PROVENANCE.json', 'COLD_TESTS.json',
                      'verify_checkpoint.py', 'test_checkpoint.py'}
CLAIMS = {'rtl': False, 'public_m16': False, 'full_m128': False,
          'ninety_percent': False, 'producer_qualified': False,
          'selected_fault_timing_qualified': False}


def need(value, message):
    if not value:
        raise ValueError(message)


def forbid_execution(event, args):
    if event == 'import' and (args[0].split('.')[0] in {'numpy', 'ctypes', 'torch', 'candidates'}
                              or args[0] in {'worker', 'run_ci'}):
        raise RuntimeError('cold archive forbids arithmetic/native imports')
    if event in {'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn',
                 'socket.connect', 'ctypes.dlopen'}:
        raise RuntimeError('cold archive forbids process, network, and native execution')


sys.addaudithook(forbid_execution)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def same(actual, expected):
    return json.dumps(actual, sort_keys=True, separators=(',', ':'), allow_nan=False) == \
           json.dumps(expected, sort_keys=True, separators=(',', ':'), allow_nan=False)


def plain(root, name):
    path = Path(root) / name
    need('/' not in name and '\\' not in name and name not in {'.', '..'}, 'flat archive path')
    need(not path.is_symlink() and path.is_file(), 'regular nonsymlink archive file')
    need(path.stat().st_size <= 262144, 'bounded archive file')
    return path


def frozen_contract(root=HERE):
    path = plain(root, 'frozen_contract.py')
    raw = path.read_bytes()
    need((len(raw), sha(raw)) == EXACT[path.name], 'frozen validator identity')
    spec = importlib.util.spec_from_file_location('portable_frozen_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_records(summary, identities, sources, contract):
    """Validate original record semantics using the unchanged reviewed validator."""
    c = frozen_contract()
    c.shape(contract)
    expected_keys = {'schema', 'profile', 'status', 'phase', 'launch_commit', 'run_id',
                     'run_attempt', 'claims', 'contract_sha256', 'library_sha256',
                     'checks', 'observations', 'elapsed_seconds'}
    need(type(summary) is dict and set(summary) == expected_keys, 'exact actual summary schema')
    need(type(summary['schema']) is int and summary['schema'] == 1, 'summary schema')
    need(summary['phase'] == 'complete' and summary['launch_commit'] == LAUNCH and
         summary['run_id'] == RUN and type(summary['run_attempt']) is int and
         summary['run_attempt'] == 1, 'exact completed hosted launch')
    need(summary['contract_sha256'] == CONTRACT and summary['library_sha256'] == LIBRARY,
         'actual contract and ELF identities')
    need(type(summary['claims']) is dict and summary['claims'] == CLAIMS and
         all(v is False for v in summary['claims'].values()), 'no widened qualification claims')
    elapsed = summary['elapsed_seconds']
    need(type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 < elapsed <= 160,
         'bounded recorded elapsed time')
    expected_sources = {'input': contract['source_sha256'], 'proposal': contract['payload_sha256'],
                        'generated': contract['generated_sha256']}
    need(type(sources) is dict and sources == expected_sources, 'exact frozen evidence source maps')
    need([len(sources[k]) for k in ('input', 'proposal', 'generated')] == [114, 5, 2],
         'exact 114/5/2 closure')
    result = {k: summary[k] for k in ('profile', 'status', 'library_sha256', 'checks', 'observations')}
    result['identities'] = identities
    c.result(result, LAUNCH, contract)
    for stage, identity in identities.items():
        need(identity['python_version'] == '3.12.15' and identity['numpy_version'] == '2.3.5',
             'observed runtime versions')
        need(identity['compiler']['version'] ==
             'x86_64-linux-gnu-g++-13 (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0',
             'observed compiler version')
        need(identity['runner']['image_os'] == 'ubuntu24' and
             identity['runner']['image_version'] == '20261012.334.1', 'observed hosted image')
        flags = identity['cpu_flags_common']
        need('avx2' in flags and not any(x.startswith(('avx512', 'amx')) for x in flags),
             'observed AVX2 host without AVX512 or AMX')
        need(len(identity['python_sources']) == {'build': 5, 'profile2': 10, 'scalar_silu': 11}[stage],
             'actual imported source inventory size')
        names = [x['module'] for x in identity['python_sources']]
        need(len(names) == len(set(names)), 'unique actual imported module names')
    return result


def verify(root=HERE):
    root = Path(root)
    need(root.is_dir() and not root.is_symlink(), 'archive directory')
    need({p.name for p in root.iterdir()} == FILES | {'MANIFEST.json'}, 'exact archive inventory')
    c = frozen_contract(root)
    manifest = c.read(plain(root, 'MANIFEST.json'))
    need(type(manifest) is dict and set(manifest) == {'schema', 'files'} and
         type(manifest['schema']) is int and manifest['schema'] == 1 and
         type(manifest['files']) is dict and set(manifest['files']) == FILES, 'exact manifest')
    total = 0
    for name in sorted(FILES):
        raw = plain(root, name).read_bytes()
        total += len(raw)
        expected = {'bytes': len(raw), 'sha256': sha(raw)}
        record = manifest['files'][name]
        need(type(record) is dict and record == expected and type(record['bytes']) is int,
             'manifest file identity: ' + name)
        if name in EXACT:
            need((len(raw), sha(raw)) == EXACT[name], 'immutable original/frozen bytes: ' + name)
    need(total <= 131072, 'compact archive byte budget')
    load = lambda name: c.read(plain(root, name))
    summary, identities, sources, contract = (load(name) for name in
        ('summary.json', 'identities.json', 'source_hashes.json', 'frozen_input_contract.json'))
    validate_records(summary, identities, sources, contract)
    p = load('PROVENANCE.json')
    need(set(p) == {'schema', 'status', 'run', 'artifact', 'preservation', 'closure', 'claims', 'preparation'}
         and type(p['schema']) is int and p['schema'] == 1 and
         p['status'] == 'PRESERVED_ACTUAL_FIXED_CASES', 'provenance schema')
    need(same(p['run'], {'id': RUN, 'attempt': 1, 'job_id': '117276108074', 'launch_commit': LAUNCH,
         'reported_conclusion': 'success', 'conclusion_source':
         'Parent verified hosted run and job; not queried by this offline checkpoint.'}), 'provenance run')
    need(same(p['artifact'], {'id': '12084699511', 'bytes': 12008,
         'sha256': '11269eb83d8bd34ccca1584e36bbf38f81cd37370fcc24d8428962929b482b75',
         'members': ['identities.json', 'source_hashes.json', 'summary.json'],
         'zip_digest_and_exact_members_verified_locally': True, 'archive_in_publication': False}),
         'provenance artifact')
    need(same(p['preservation'], {'mode': 'EXACT_ORIGINAL_JSON_BYTES', 'original_json_bytes': 57230,
         'original_files_modified': False}), 'exact-copy preservation')
    need(same(p['closure'], {'input_sources': 114, 'payload_sources': 5, 'generated_targets': 2,
         'cold_source_preflight': 'PASS_FROZEN_SOURCE_BYTES_AND_MAPS',
         'cold_check_scope': 'Reads and hashes reviewed source bytes; does not execute arithmetic.'}),
         'recorded cold source preflight')
    need(p['claims'] == CLAIMS and all(v is False for v in p['claims'].values()), 'provenance scope')
    need(same(p['preparation'], {'native_runs': 0, 'builds': 0, 'installs': 0, 'producer_runs': 0,
         'ci_launches': 0, 'pushes': 0, 'uploaded_weights_tensors_npz_logs': False}), 'cold preservation scope')
    tests = load('COLD_TESTS.json')
    need(type(tests) is dict and set(tests) == {'schema', 'status', 'normal', 'optimized', 'native_execution'}
         and type(tests['schema']) is int and tests['schema'] == 1 and
         tests['status'] == 'PASS_COLD_ARCHIVE_TESTS' and tests['native_execution'] is False,
         'completed cold test receipt')
    for mode in ('normal', 'optimized'):
        record = tests[mode]
        need(type(record) is dict and set(record) == {'tests', 'failures', 'errors'} and
             all(type(x) is int for x in record.values()) and record['tests'] >= 18 and
             record['failures'] == record['errors'] == 0, 'passed cold tests in both Python modes')
    need(tests['normal'] == tests['optimized'], 'same normal and optimized test inventory')
    # Hash validation alone cannot prove that a remote run occurred. The exact
    # original result is retained; this verifier only establishes local consistency.
    return {'status': 'VALID_PRESERVED_ACTUAL_FIXED_CASES', 'run_id': RUN,
            'original_status': summary['status'], 'payload_files': len(FILES) + 1,
            'manifested_bytes': total, 'source_counts': [114, 5, 2],
            'claims': CLAIMS, 'native_execution': False}


if __name__ == '__main__':
    print(json.dumps(verify(), sort_keys=True))
