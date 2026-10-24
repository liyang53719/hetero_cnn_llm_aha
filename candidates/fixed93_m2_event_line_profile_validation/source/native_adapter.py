"""Existing verified profile2 ELF only. Import/preflight never loads native code.

This is new orchestration, not an arithmetic change. The actual entry requires
the separately reviewed parent admission. No compiler, dladdr, current-process
CDLL, reset, or arithmetic call is made here.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import types

from m2_authority import require_actual_runtime
from m2_authority import _STATE
need_state = _STATE
if type(need_state) is not dict:
    raise ValueError('M2 authority must precede native adapter import')
HERE = need_state['base']
SOURCE = HERE / 'source'
PINS = HERE / 'NATIVE_REUSE_PINS.json'
PINS_SHA256 = 'aaa95050d4d2540af185fa7410663e44606cc8361c6656f359a10787863c08c2'
ELF_SHA256 = 'c03ab303a6d0780f379a13f8f0339872a6b00e066c8481b8e8f39a16243cf5b8'
_LOADED = None


def need(ok, message):
    if not ok:
        raise ValueError(message)


def checked(spec):
    path = Path(spec['path'])
    need(path.is_absolute() and path.resolve() == path and path.is_file() and
         not any(p.is_symlink() for p in (path, *path.parents)), 'native pin path alias')
    stat = path.stat()
    need(stat.st_size == spec['bytes'], 'native pin size')
    if 'device' in spec:
        need((stat.st_dev, stat.st_ino) == (spec['device'], spec['inode']), 'native pin identity')
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == spec['sha256'], 'native pin bytes')
    return raw


def pins():
    raw = PINS.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == PINS_SHA256, 'native reuse pins drift')
    value = json.loads(raw)
    need(value['schema'] == 'fixed93-existing-native-reuse-pins-v1' and
         value['fresh_build'] is False and value['full_hermetic_toolchain'] is False,
         'native reuse claim scope')
    need(value['files']['elf']['sha256'] == ELF_SHA256, 'wrong existing ELF')
    for spec in value['files'].values():
        checked(spec)
    for relative, digest in value['native_source_sha256'].items():
        path = SOURCE / relative
        need(path.resolve() == path and path.is_file() and
             hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'native source drift')
    receipt = json.loads(checked(value['files']['compile']))
    need(receipt['source_sha256'] == value['native_source_sha256'] and
         receipt['compiler'] == value['compiler'] and
         receipt['argv'][1:6] == value['strict_flags'] ==
         ['-shared', '-fPIC', '-O2', '-ffp-contract=off', '-fno-fast-math'] and
         receipt['returncode'] == 0 and receipt['library_sha256'] == ELF_SHA256 and
         receipt['library'] == value['files']['elf']['path'],
         'historical build provenance drift')
    return value, receipt


def identity():
    value, _ = pins()
    return {role: {k: value['files'][key][k] for k in ('path', 'bytes', 'sha256')}
            for role, key in (('library', 'elf'), ('receipt', 'compile'))}


def _same_code(a, b):
    if (type(a) is not types.CodeType or type(b) is not types.CodeType or a != b or
            a.co_filename != b.co_filename or a.co_firstlineno != b.co_firstlineno or
            a.co_linetable != b.co_linetable or a.co_exceptiontable != b.co_exceptiontable):
        return False
    return all(_same_code(x, y) for x, y in zip(a.co_consts, b.co_consts)
               if isinstance(x, types.CodeType))


def _configure_function(module, name, relative, manifest):
    path = SOURCE / relative
    need(type(module) is types.ModuleType and Path(module.__file__).resolve() == path,
         'ABI configurator module path')
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == manifest['source_sha256'][relative],
         'ABI configurator source hash')
    compiled = compile(raw, str(path), 'exec', dont_inherit=True, optimize=0)
    expected = [c for c in compiled.co_consts if isinstance(c, types.CodeType) and c.co_name == name]
    fn = vars(module).get(name)
    need(len(expected) == 1 and type(fn) is types.FunctionType and
         fn.__globals__ is module.__dict__ and fn.__defaults__ is None and
         fn.__kwdefaults__ is None and _same_code(fn.__code__, expected[0]),
         'ABI configurator loaded code/defaults')
    return fn


def _maps():
    records = []
    for line in Path('/proc/self/maps').read_text().splitlines():
        parts = line.split(maxsplit=5)
        need(len(parts) in (5, 6), 'mapped row format')
        lo, hi = (int(x, 16) for x in parts[0].split('-'))
        need(0 <= lo < hi and len(parts[1]) == 4, 'mapped row range')
        records.append(dict(lo=lo, hi=hi, permissions=parts[1], device=parts[3],
                            inode=int(parts[4]), path=parts[5] if len(parts) == 6 else '',
                            raw=line))
    return records


def _loaded_receipt(library, value, runtime, ctypes_module):
    spec = value['files']['elf']
    checked(spec)
    need(type(library) is ctypes_module.CDLL and library._name == spec['path'], 'loaded CDLL identity')
    records = _maps()
    device = (os.major(spec['device']), os.minor(spec['device']))
    matches = [r for r in records if r['path'] == spec['path']]
    need(matches and all(r['inode'] == spec['inode'] and
         tuple(int(x, 16) for x in r['device'].split(':')) == device for r in matches),
         'mapped ELF path/device/inode')
    symbols = {}
    for name in ('matrix_normal_step', 'td_step', 'sf_vector_bf16_v1'):
        address = ctypes_module.cast(getattr(library, name), ctypes_module.c_void_p).value
        need(type(address) is int and any(r['lo'] <= address < r['hi'] and
             'x' in r['permissions'] and 'w' not in r['permissions'] for r in matches),
             'ABI symbol not in verified executable ELF mapping: ' + name)
        symbols[name] = address
    math_files = {}
    for row in records:
        p = Path(row['path'])
        if not p.is_absolute() or not any(p.name.startswith(n) for n in
                ('libm.so', 'libc.so', 'libstdc++', 'libgcc_s')):
            continue
        p = p.resolve()
        pin = runtime['files'].get(str(p))
        need(pin is not None, 'unbound mapped math runtime')
        checked(dict(path=str(p), **pin))
        st = p.stat()
        need(row['inode'] == st.st_ino and tuple(int(x, 16) for x in row['device'].split(':')) ==
             (os.major(st.st_dev), os.minor(st.st_dev)), 'mapped math runtime identity')
        math_files[str(p)] = dict(pin, device=st.st_dev, inode=st.st_ino)
    need(any(Path(p).name.startswith('libm.so') for p in math_files) and
         any(Path(p).name.startswith('libc.so') for p in math_files), 'mapped libc/libm absent')
    return dict(status='VERIFIED_EXISTING_ELF_LOAD_ONLY', library=spec['path'],
                library_sha256=ELF_SHA256, mapped_identity={'device': spec['device'], 'inode': spec['inode']},
                artifact_identity_before={
                    role: {k: value['files'][key][k] for k in ('path', 'bytes', 'sha256')}
                    for role, key in (('library', 'elf'), ('receipt', 'compile'))},
                mapped_rows=[r['raw'] for r in matches], symbol_addresses=symbols,
                loaded_math_runtime=math_files, compilation_performed=False, fresh_build=False,
                full_hermetic_toolchain=False, numerical_acceptance_inherited=False,
                old_numeric_state_reused=False, reset_performed_by_loader=False,
                hardware_simulation=False)


def load(dense):
    global _LOADED
    need(_LOADED is None, 'existing ELF load is one-use')
    # This missing/default-fail-closed parent gate is checked before importing ctypes.
    admitted = require_actual_runtime('existing_profile2_elf_load')
    value, receipt = pins()
    manifest = admitted['source_manifest']
    runtime = admitted['runtime_pins']
    need(type(manifest) is dict and type(runtime) is dict, 'new actual source/runtime binding')
    import ctypes
    expected_module = sys.modules.get('candidates.qwen2_resident_matrix.ffn_attention.matrix_service')
    configure = _configure_function(expected_module, 'configure_library',
        'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py', manifest)
    silu = _configure_function(dense, 'configure_silu_library',
        'candidates/qwen2_resident_matrix/official_bf16/dense_silu.py', manifest)
    need(dense.configure_library is configure and dense.C is ctypes, 'ABI configurator imported dependency')
    library = ctypes.CDLL(value['files']['elf']['path'])
    _LOADED = library  # A subsequent failure cannot retry the loader.
    library = silu(configure(library))
    loaded = _loaded_receipt(library, value, runtime, ctypes)
    return library, receipt, loaded
