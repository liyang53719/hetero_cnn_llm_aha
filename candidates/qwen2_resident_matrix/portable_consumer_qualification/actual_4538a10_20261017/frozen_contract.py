"""Cold input contract. No candidate, NumPy, ctypes, compiler or process imports."""
import hashlib
import json
import math
import os
import re
from pathlib import Path, PurePosixPath

PROFILE = 'hosted-generic-consumer-fixed-cases-v1'
WORKFLOW = '.github/workflows/portable-consumer-qualification-launch-r1.yml'
PREFIX = 'candidates/qwen2_resident_matrix/'
OWN = PREFIX + 'portable_consumer_qualification/'
FILES = ('contract.py', 'run_ci.py', 'worker.py', 'test_contract.py')
GENERATED = (PREFIX + 'ffn_attention/matrix_numeric.cpp', PREFIX + 'ffn_attention/matrix_service.py')
ARITHMETIC = (GENERATED[0], PREFIX + 'official_bf16/silu_recipe.cpp',
              PREFIX + 'transposed_down/numeric_smoke.cpp', PREFIX + 'ffn_tiles/silu_recipe.cpp')
INVENTORY_SHA256 = '82f6455a4455b4c9ceb94add6c290ef574d245ed14edf6ba65a6a8d5a9297d84'

def need(value, message):
    if not value:
        raise ValueError(message)

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()

def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()

def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    with Path(path).open('rb') as stream:
        raw = stream.read(262145)
    need(len(raw) <= 262144, 'bounded JSON metadata')
    def number(value):
        parsed = float(value)
        need(math.isfinite(parsed), 'finite JSON only')
        return parsed
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_float=number, parse_constant=lambda value: need(False, 'finite JSON only'))

def atomic(path, value):
    path = Path(path)
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    need(len(raw) <= 262144, 'bounded evidence output')
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)

def safe(root, name):
    need(type(name) is str and name and '\\' not in name, 'relative source name')
    parts = PurePosixPath(name).parts
    need(not PurePosixPath(name).is_absolute() and all(p not in ('.', '..') for p in parts),
         'relative source name')
    root = Path(root).resolve(strict=True)
    current = root
    for part in parts:
        current /= part
        need(not current.is_symlink(), 'source symlink forbidden')
    need(current.is_file() and current.resolve().is_relative_to(root), 'source file required')
    return current

def shape(value):
    keys = {'schema', 'profile', 'status', 'workflow', 'budgets', 'runtime',
            'source_sha256', 'payload_sha256', 'generated_sha256', 'arithmetic_sources', 'claims'}
    need(type(value) is dict and set(value) == keys, 'exact contract keys')
    need(type(value['schema']) is int and value['schema'] == 1 and value['profile'] == PROFILE,
         'qualification schema/profile')
    need(value['status'] == 'PROPOSAL_ONLY_NOT_EXECUTED' and value['workflow'] == WORKFLOW,
         'qualification proposal/launch identity')
    need(value['budgets'] == {'worker_seconds': 150, 'cleanup_seconds': 10, 'job_minutes': 10} and
         all(type(v) is int for v in value['budgets'].values()),
         'bounded total execution and cleanup')
    need(value['runtime'] == {'python': '3.12', 'numpy': '2.3.5', 'system': 'Linux', 'machine': 'x86_64'},
         'distinct consumer runtime')
    need(value['arithmetic_sources'] == list(ARITHMETIC), 'four arithmetic sources')
    need(value['claims'] == {'rtl': False, 'public_m16': False, 'full_m128': False,
                             'ninety_percent': False, 'producer_qualified': False,
                             'selected_fault_timing_qualified': False} and
         all(v is False for v in value['claims'].values()), 'scope claims')
    for name in ('source_sha256', 'payload_sha256', 'generated_sha256'):
        need(type(value[name]) is dict and value[name] and all(digest(v) for v in value[name].values()),
             'SHA256 source maps')
    inventory = hashlib.sha256(canonical(sorted(value['source_sha256']))).hexdigest()
    need(inventory == INVENTORY_SHA256, 'exact input closure')
    need(set(value['payload_sha256']) == {*(OWN + n for n in FILES), WORKFLOW}, 'exact proposal payload')
    need(set(value['generated_sha256']) == set(GENERATED), 'exact generated targets')
    return value

def admit(environ, out):
    need(environ.get('GITHUB_ACTIONS') == 'true' and environ.get('GITHUB_EVENT_NAME') == 'push'
         and environ.get('GITHUB_RUN_ATTEMPT') == '1', 'only first push attempt')
    need(not any(environ.get(k) for k in ('LD_PRELOAD', 'PYTHONPATH',
              'NPY_DISABLE_CPU_FEATURES', 'NPY_ENABLE_CPU_FEATURES')), 'no runtime backend overrides')
    launch = environ.get('GITHUB_SHA', '')
    need(len(launch) == 40 and all(x in '0123456789abcdef' for x in launch), 'launch commit identity')
    need(not Path(out).exists(), 'fresh isolated output required')
    return launch

def loader(environ, executable):
    """Only setup-python's one validated interpreter-local loader directory."""
    names = ('RUNNER_TOOL_CACHE', 'pythonLocation', 'LD_LIBRARY_PATH')
    need(all(type(environ.get(n)) is str and environ[n] for n in names), 'explicit hosted Python loader identity')
    raw = environ['LD_LIBRARY_PATH']
    need(':' not in raw, 'one loader path component required')
    cache, location, lib = (Path(environ[n]) for n in names)
    for path in (cache, location, lib):
        need(path.is_absolute() and '..' not in path.parts and path.is_dir(), 'existing absolute Python toolcache directory')
        need(not any(p.is_symlink() for p in (path, *path.parents)), 'nonsymlink Python toolcache directories')
    cache, location, lib = (p.resolve(strict=True) for p in (cache, location, lib))
    need(location.is_relative_to(cache), 'selected Python within runner toolcache')
    relative = location.relative_to(cache)
    need(len(relative.parts) == 3 and relative.parts[0] == 'Python' and
         re.fullmatch(r'3\.12\.\d+', relative.parts[1]) is not None and relative.parts[2] == 'x64',
         'reviewed setup-python toolcache layout')
    binary = Path(executable).resolve(strict=True)
    need(binary.is_file() and binary.parent == location / 'bin', 'actual interpreter under selected Python root')
    need(lib == location / 'lib' and raw == str(lib), 'only selected interpreter lib directory')
    return dict(RUNNER_TOOL_CACHE=str(cache), pythonLocation=str(location), LD_LIBRARY_PATH=str(lib),
                toolcache_relative=str(relative))

def validate(origin, here, workflow=None):
    value = shape(read(Path(here) / 'input-contract.json'))
    for name, expected in value['source_sha256'].items():
        need(sha(safe(origin, name)) == expected, 'source input drift: ' + name)
    for name, expected in value['payload_sha256'].items():
        path = Path(workflow) if name == WORKFLOW and workflow else safe(origin, name)
        need(sha(path) == expected, 'proposal payload drift: ' + name)
    pins = read(safe(origin, PREFIX + 'attention_packed_native/pins.json'))
    need(value['generated_sha256'] == pins['generated'], 'original generated-source pins')
    return value

def result(value, launch, input_contract=None):
    need(type(value) is dict and set(value) == {'profile', 'status', 'library_sha256', 'identities', 'checks', 'observations'},
         'exact current result')
    need(value['profile'] == PROFILE and value['status'] == 'PASS_FIXED_ACTUAL_CASES' and
         digest(value['library_sha256']), 'actual result profile/status/ELF')
    need(value['checks'] == {'profile2_original_suite': True, 'scalar_original_tests': 7,
                             'silu_success_vectors': 2, 'silu_fault_vectors': 3} and
         value['checks']['profile2_original_suite'] is True and
         all(type(value['checks'][k]) is int for k in ('scalar_original_tests', 'silu_success_vectors', 'silu_fault_vectors')),
         'exact completed tests')
    need(type(value['identities']) is dict and set(value['identities']) == {'build', 'profile2', 'scalar_silu'},
         'three actual process identities')
    observations(value['observations'])
    def text(value):
        return type(value) is str and 0 < len(value) <= 256 and all(32 <= ord(x) < 127 for x in value)
    def file(value):
        need(type(value) is dict and set(value) == {'name', 'bytes', 'sha256'}, 'exact ELF file identity')
        need(text(value['name']) and '/' not in value['name'] and '\\' not in value['name'] and
             type(value['bytes']) is int and 0 < value['bytes'] < 1 << 30 and digest(value['sha256']),
             'bounded basename/size/ELF digest')
    for identity in value['identities'].values():
        identity_result(identity, value['library_sha256'], launch, input_contract, text, file)
    return value

def observations(observed):
    need(type(observed) is dict and set(observed) == {'profile2_cases', 'silu_phase_sha256'}, 'exact actual observations')
    expected_cases = [
        dict(case='qk', profile=2, steps=8, fmas=32768),
        dict(case='pv', profile=2, steps=3, fmas=6144),
        dict(case='pv128_boundary', profile=2, steps=128, fmas=262144),
        dict(case='pv', profile=1, steps=3, fmas=12288),
        dict(case='legacy_default', steps=8, fmas=4096),
        dict(case='nonselected_nonfinite', protocol_error=False, selected_fault_timing_qualified=False),
        dict(case='selected_nonfinite', protocol_error=False, selected_fault_timing_qualified=False)]
    cases = observed['profile2_cases']
    need(type(cases) is list and len(cases) == 7, 'exact original native case inventory')
    for index, (actual, expected) in enumerate(zip(cases, expected_cases)):
        need(type(actual) is dict, 'actual native case object')
        extra = {'output_sha256'} if index in (0, 1, 3) else set()
        need(set(actual) == set(expected) | extra and
             all(type(actual[k]) is type(v) and actual[k] == v for k, v in expected.items()),
             'original actual case shape and counters')
        if extra:
            need(digest(actual['output_sha256']), 'actual profile2 full result-word digest')
    need(type(observed['silu_phase_sha256']) is list and len(observed['silu_phase_sha256']) == 2 and
         all(digest(x) for x in observed['silu_phase_sha256']), 'actual complete SiLU phase digests')
    return observed

def identity_result(identity, library_sha256, launch, input_contract, text, file):
        need(type(identity) is dict and set(identity) == {'interpreter', 'python_version', 'numpy_version',
             'numpy_extension', 'compiler', 'compiler_name', 'libm', 'combined_elf', 'loaded_elfs',
             'system', 'machine', 'kernel', 'runner', 'loader', 'python_sources', 'cpu_flags_common', 'committed_head'}, 'exact actual runtime identity')
        for name in ('interpreter', 'numpy_extension', 'libm', 'combined_elf'):
            file(identity[name])
        need(identity['combined_elf']['sha256'] == library_sha256, 'runtime ELF digest match')
        need(type(identity['loaded_elfs']) is list and 1 <= len(identity['loaded_elfs']) <= 128, 'bounded actual ELF inventory')
        for loaded in identity['loaded_elfs']:
            file(loaded)
        need(all(identity[name] in identity['loaded_elfs'] for name in ('numpy_extension', 'libm', 'combined_elf')),
             'observed mapped dependencies')
        need(type(identity['compiler']) is dict and set(identity['compiler']) == {'sha256', 'version'} and
             digest(identity['compiler']['sha256']) and text(identity['compiler']['version']), 'actual compiler identity')
        need(all(text(identity[name]) for name in ('compiler_name', 'python_version', 'kernel')), 'bounded runtime text')
        need(identity['python_version'].startswith('3.12.') and identity['numpy_version'] == '2.3.5' and
             identity['system'] == 'Linux' and identity['machine'] == 'x86_64' and identity['committed_head'] == launch,
             'qualified interpreter and genuine source commit')
        runner = identity['runner']
        need(type(runner) is dict and set(runner) == {'os', 'arch', 'environment', 'image_os', 'image_version'} and
             all(text(x) for x in runner.values()) and runner['os'] == 'Linux' and runner['arch'] == 'X64' and
             runner['environment'] == 'github-hosted', 'bounded observed hosted runner details')
        loader_value = identity['loader']
        need(type(loader_value) is dict and set(loader_value) == {'policy', 'toolcache_relative', 'libpython'} and
             loader_value['policy'] == 'setup-python-single-lib' and
             loader_value['toolcache_relative'] == 'Python/' + identity['python_version'] + '/x64',
             'observed exact selected Python loader root')
        file(loader_value['libpython'])
        need(loader_value['libpython'] in identity['loaded_elfs'] and
             loader_value['libpython']['name'].startswith('libpython3.12.so'), 'actual mapped libpython identity')
        sources = identity['python_sources']
        need(type(sources) is list and 1 <= len(sources) <= 256 and input_contract is not None,
             'bounded observed imported Python source identities')
        for source in sources:
            need(type(source) is dict and set(source) == {'module', 'tree', 'path', 'sha256'} and
                 text(source['module']) and source['tree'] in ('origin', 'generated'), 'actual module identity')
            path = source['path']
            need(type(path) is str and text(path) and not PurePosixPath(path).is_absolute() and
                 '..' not in PurePosixPath(path).parts, 'bounded relative imported source path')
            expected = {**input_contract['source_sha256'], **input_contract['payload_sha256']}
            if source['tree'] == 'generated':
                expected.update(input_contract['generated_sha256'])
            need(path in expected and source['sha256'] == expected[path], 'actual imported source is in exact reviewed closure')
        flags = identity['cpu_flags_common']
        need(type(flags) is list and 1 <= len(flags) <= 512 and flags == sorted(set(flags)) and
             all(type(flag) is str and 0 < len(flag) < 64 and all(x.isascii() and (x.isalnum() or x == '_') for x in flag)
                 for flag in flags), 'bounded observed CPU flags')
