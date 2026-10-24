"""One new software-wrapper process using an existing sealed repaired ELF.
No compiler, original ELF, model, arithmetic unit, or hardware execution.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types


def need(ok, why):
    if not ok:
        raise ValueError(why)


def checked(path, pin):
    p = Path(path)
    need(str(p.resolve(strict=True)) == pin.get('resolved', str(p)), 'canonical input')
    s = p.stat()
    stamp = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
    need(stat.S_ISREG(s.st_mode) and s.st_size == pin['bytes'], 'regular pinned input')
    with p.open('rb') as f:
        need(stamp(s) == stamp(os.fstat(f.fileno())), 'input FD identity')
        raw = f.read(s.st_size + 1)
        need(stamp(s) == stamp(os.fstat(f.fileno())) == stamp(p.stat()), 'input drift')
    need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], 'input raw SHA')
    return raw


def main():
    need(len(sys.argv) == 2 and sys.flags.isolated and sys.flags.no_site and
         sys.flags.dont_write_bytecode and not sys.flags.optimize and
         sys.version_info[:3] == (3, 12, 14), 'fixed CPython child')
    plan_path = Path(sys.argv[1])
    plan_raw = plan_path.read_bytes()
    need(len(plan_raw) < 1024**2, 'bounded plan')
    plan = json.loads(plan_raw)
    need(plan['schema'] == 'strict-reference-wrapper-bound-v1' and
         str(plan_path) == plan['plan_path'], 'fixed plan')
    need(sys.pycache_prefix == str(Path(plan['work']) / 'tmp' / 'pycache'), 'fresh pycache root')
    checked(__file__, plan['inputs'][__file__])
    library = plan['library_path']
    seal = json.loads(checked(plan['library_seal_path'], plan['inputs'][plan['library_seal_path']]))
    need(seal['path'] == library and seal['compile_natural_cleanup'] is True and
         seal['plan_sha256'] == plan['prior_compile_plan_sha256'] and
         seal['candidate_cpp_sha256'] == plan['inputs'][plan['candidate_cpp_path']]['sha256'] and
         seal['pin'] == {k: plan['inputs'][library][k] for k in ('bytes', 'sha256')},
         'exact prior repaired ELF/source provenance, no rebuilt library')
    checked(plan['candidate_cpp_path'], plan['inputs'][plan['candidate_cpp_path']])
    checked(library, plan['inputs'][library])
    import ctypes as C
    # Only these two candidate imports need preparation before the no-pyc gate.
    # A fresh absent prefix plus -B makes their cache probes fall back to source.
    need(not os.path.lexists(sys.pycache_prefix), 'fresh pycache root absent before preload')
    stdlib = Path(plan['python']).parent.parent / 'lib' / 'python3.12'
    preload_paths = {name: str(stdlib / (name + '.py'))
                     for name in ('dataclasses', 'fractions')}
    for path in preload_paths.values():
        need(path in plan['python_runtime_sources'], 'preload in original runtime source closure')
        checked(path, plan['inputs'][path])
    import dataclasses
    import fractions
    for name, module in (('dataclasses', dataclasses), ('fractions', fractions)):
        path = preload_paths[name]
        need(module.__file__ == path and module.__spec__.origin == path,
             'preloaded stdlib exact pinned source origin')
        checked(path, plan['inputs'][path])
    need(not os.path.lexists(sys.pycache_prefix), 'fresh pycache root absent after preload')
    loaded = []
    def audit(event, args):
        if event.startswith('socket.') or event == 'urllib.Request' or event in {
                'os.system', 'os.exec', 'os.posix_spawn', 'subprocess.Popen'}:
            raise RuntimeError('native controls cannot launch process/network')
        if event == 'ctypes.dlopen':
            need(args[0] == library and not loaded, 'one exact existing repaired ELF only')
            loaded.append(args[0])
        if event == 'open' and isinstance(args[0], (str, bytes)):
            need(not os.fsdecode(args[0]).endswith(('.pyc', '.pyo')), 'no cached code input')
    sys.addaudithook(audit)
    def raw_module(key, name):
        path = plan[key]
        raw = checked(path, plan['inputs'][path])
        module = types.ModuleType(name)
        module.__file__ = path
        sys.modules[name] = module
        exec(compile(raw, path, 'exec', dont_inherit=True), module.__dict__)
        return module
    W = raw_module('wrapper_path', 'fixed_strict_reference')
    R = raw_module('reference_path', 'fixed_fraction_reference')
    T = raw_module('controls_path', 'fixed_protocol_controls')
    need(W.POLICY_ID == plan['policy_id'] and W.FATAL_MASK == 30, 'fixed one-lane strict policy')
    # Explicit MOCK service replies only. They do not change the native binding.
    protocol = T.run_controls(W)
    lib = C.CDLL(library)
    U, I, P = C.c_uint32, C.c_int, C.POINTER(C.c_uint32)
    signatures = {
        'gdn_vector16_environment': ([], I),
        'gdn_vector16_trace': ([U, P, P, P, U, P], I),
        'uf_diagnostic_environment': ([], I),
        'uf_diagnostic_snapshot': ([P], None),
    }
    functions = {}
    for name, (args, restype) in signatures.items():
        f = getattr(lib, name)
        f.argtypes, f.restype = args, restype
        functions[name] = f
    def mappings():
        raw = Path('/proc/self/maps').read_bytes()
        need(len(raw) < 2 * 1024**2, 'bounded mappings')
        rows = []
        for line in raw.decode().splitlines():
            cols = line.split(None, 5)
            if len(cols) != 6 or not cols[5].startswith('/') or 'x' not in cols[1]:
                continue
            need(not cols[5].endswith(' (deleted)'), 'no deleted executable mapping')
            resolved = str(Path(cols[5]).resolve(strict=True))
            need(resolved in plan['mapped_elf_inputs'], 'pinned executable mapping')
            checked(resolved, plan['inputs'][resolved])
            rows.append({'start': int(cols[0].split('-')[0], 16),
                         'end': int(cols[0].split('-')[1], 16), 'path': resolved})
        need(any(x['path'] == library for x in rows), 'existing repaired ELF actually loaded')
        for name, f in functions.items():
            address = C.cast(f, C.c_void_p).value
            need(any(x['path'] == library and x['start'] <= address < x['end'] for x in rows), 'symbol source binding')
            need(f.argtypes == signatures[name][0] and f.restype is signatures[name][1], 'fixed ABI')
        return rows
    mapped_before = mappings()
    def snapshot():
        data = (U * 4)()
        functions['uf_diagnostic_snapshot'](data)
        return dict(fe_round=data[0], fe_standard_sticky=data[1], mxcsr=data[2],
                    mxcsr_controls=data[2] & ~63, mxcsr_sticky=data[2] & 63,
                    mxcsr_denormal_operand=(data[2] >> 1) & 1, x87_control=data[3])
    def environment():
        need(functions['gdn_vector16_environment']() == 0 and
             functions['uf_diagnostic_environment']() == 0, 'RNE/gradual and masked traps; no repair')
    def retained(a, b):
        for key in ('fe_round', 'fe_standard_sticky', 'mxcsr_controls', 'x87_control'):
            need(a[key] == b[key], 'standard sticky/control preserved')
    environment()
    initial = snapshot()
    native = W.NativeTrace1(C, functions['gdn_vector16_trace'],
                           functions['gdn_vector16_environment'], functions['uf_diagnostic_environment'])
    wrapper = W.StrictReference(native)
    table = json.loads(checked(plan['stimuli_path'], plan['inputs'][plan['stimuli_path']]))
    need(len(table['cases']) == 52 and table['scope'] == '20_existing_directed_plus_32_zero_combinations', 'fixed52 requests')
    observed = []
    for row in table['cases']:
        a, b, acc = (int(row[k], 16) for k in ('a', 'b', 'acc'))
        expected = R.strict(a, b, acc)
        environment()
        before, calls = snapshot(), native.calls
        actual = wrapper.evaluate(a, b, acc)
        after = snapshot()
        retained(before, after)
        state = {0: 'OK', 4: 'MUL_FATAL', 5: 'ADD_FATAL'}[expected['status']]
        need(actual['status'] == state and actual['product'] == expected['product'] and
             actual['mulFlags'] == expected['mul_flags'] and actual['productValid'] and
             actual['mulFlagsValid'] and actual['passesCompleted'] == expected['attempted'] and
             actual['traceCalls'] == expected['attempted'] == native.calls - calls and
             actual['value'] == expected['value'] and actual['addFlags'] == expected['add_flags'] and
             actual['valueValid'] == actual['addFlagsValid'] == (expected['attempted'] == 2) and
             actual['accCommit'] == (expected['status'] == 0) and actual['backendReturn'] is None,
             'actual wrapper two-pass bits/flags/valid/commit versus independent Fraction')
        if 'expected' in row:
            need(expected == row['expected'], 'original hand-derived directed table still matches')
        observed.append(dict(id=row['id'], a=row['a'], b=row['b'], acc=row['acc'],
                             result=actual, fraction=expected, before=before, after=after))
    # Native-bound wrapper rejects these without calling native arithmetic.
    denied = []
    for index in range(3):
        for raw in (0x7F800000, 0xFF800000, 0x7FC00001, 0x7F800001):
            inputs = [0x3F800000] * 3
            inputs[index] = raw
            calls = native.calls
            actual = wrapper.evaluate(*inputs)
            need(actual['status'] == 'NONFINITE_INPUT' and native.calls == calls and
                 actual['traceCalls'] == actual['passesCompleted'] == 0 and
                 not any(actual[k] for k in ('productValid', 'valueValid', 'mulFlagsValid', 'addFlagsValid', 'accCommit')),
                 'all-three preadmission before actual native call')
            denied.append({'position': index, 'word': f'{raw:08x}', 'status': actual['status'], 'trace_calls': 0})
    environment()
    final = snapshot()
    mapped_after = mappings()
    need(mapped_after == mapped_before and loaded == [library], 'native identity stable')
    checked(library, plan['inputs'][library])
    result = dict(status='PASS_ISOLATED_STRICT_REFERENCE_WRAPPER_SOFTWARE_ONLY', policy=W.POLICY_ID,
                  native_requests=52, native_trace_calls=native.calls, nonfinite_prechecks=denied,
                  cases=observed, protocol_controls=protocol, initial_environment=initial,
                  final_environment=final, executable_mappings=mapped_after, library=seal,
                  lane_count=1, compiled_or_rebuilt=False, raw_probe_executed=False,
                  old_cpp_or_model_modified=False, HardFloat_executed=False, RTL_executed=False,
                  G11_hardware_group_regression_executed=False, hardware_flags_gate_remains=True)
    raw = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
    need(len(raw) <= 192 * 1024, 'bounded wrapper result')
    with (Path(plan['work']) / 'WRAPPER_RESULT.json').open('xb') as f:
        f.write(raw)
    print(json.dumps({'status': result['status'], 'native_requests': 52,
                      'trace_calls': native.calls, 'bytes': len(raw),
                      'sha256': hashlib.sha256(raw).hexdigest()}), flush=True)


if __name__ == '__main__':
    main()
