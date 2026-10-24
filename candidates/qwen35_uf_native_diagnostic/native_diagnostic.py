"""One fixed software-native diagnostic, not RTL or executed HardFloat."""
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
    need(str(p.resolve(strict=True)) == pin.get('resolved', str(p)), 'source canonical identity')
    s = p.stat()
    stamp = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
    need(stat.S_ISREG(s.st_mode) and s.st_size == pin['bytes'], 'source regular size')
    with p.open('rb') as f:
        need(stamp(s) == stamp(os.fstat(f.fileno())), 'source FD identity')
        raw = f.read(s.st_size + 1)
        need(stamp(s) == stamp(os.fstat(f.fileno())) == stamp(p.stat()), 'source drift')
    need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], 'source bytes')
    return raw


def main():
    need(len(sys.argv) == 2 and sys.flags.isolated and sys.flags.no_site and
         sys.flags.dont_write_bytecode and sys.version_info[:3] == (3, 12, 14), 'fixed child ABI')
    plan_path = Path(sys.argv[1])
    plan_raw = plan_path.read_bytes()
    need(len(plan_raw) <= 2 * 1024**2, 'bounded fixed plan')
    plan = json.loads(plan_raw)
    need(plan['schema'] == 'uf-native-diagnostic-bound-v1' and str(plan_path) == plan['plan_path'], 'fixed plan')
    need(sys.pycache_prefix == str(Path(plan['work']) / 'tmp' / 'pycache'), 'fresh no-pyc source imports')
    own = Path(__file__).resolve()
    checked(own, plan['inputs'][str(own)])
    table_raw = checked(plan['stimuli_path'], plan['inputs'][plan['stimuli_path']])
    table = json.loads(table_raw)
    need(len(table['finite_single_lane_cases']) == 24 and len(table['native_batch_policy_cases']) == 3, 'bounded stimuli')
    reference_raw = checked(plan['reference_path'], plan['inputs'][plan['reference_path']])
    reference = types.ModuleType('uf_fixed_fraction_reference')
    reference.__file__ = plan['reference_path']
    exec(compile(reference_raw, reference.__file__, 'exec', dont_inherit=True), reference.__dict__)
    # ctypes initialization can use the process handle. Only the following new
    # library may be loaded after initialization. No other project code imports.
    import ctypes as C
    seal_path = Path(plan['work']) / 'LIBRARY_SEAL.json'
    seal = json.loads(seal_path.read_bytes())
    library = str(Path(plan['work']) / 'libuf_diagnostic.so')
    need(seal['path'] == library and seal['compile_natural_cleanup'] is True and
         hashlib.sha256(plan_raw).hexdigest() == seal['plan_sha256'], 'new library and frozen plan provenance')
    checked(library, seal['pin'])
    loaded = []

    def audit(event, args):
        if event.startswith('socket.') or event == 'urllib.Request' or event in {
            'os.system', 'os.exec', 'os.posix_spawn', 'subprocess.Popen'}:
            raise RuntimeError('native child process/network forbidden')
        if event == 'ctypes.dlopen':
            need(args[0] == library and not loaded, 'only one fixed new diagnostic ELF')
            loaded.append(args[0])
        if event == 'open' and isinstance(args[0], (str, bytes)):
            name = os.fsdecode(args[0])
            need(not name.endswith(('.pyc', '.pyo')), 'no cached Python payload')
    sys.addaudithook(audit)
    lib = C.CDLL(library)
    U, I, P = C.c_uint32, C.c_int, C.POINTER(C.c_uint32)
    signatures = {
        'gdn_vector16_environment': ([], I),
        'gdn_vector16_trace': ([U, P, P, P, U, P], I),
        'gdn_vector16_mul_add_policy_trace': ([P, P, P, P, U, P, C.POINTER(I), U], U),
        'uf_diagnostic_environment': ([], I),
        'uf_diagnostic_snapshot': ([P], None),
        'uf_diagnostic_raw': ([U, U, U, P], I),
    }
    functions = {}
    for name, (args, restype) in signatures.items():
        f = getattr(lib, name)
        f.argtypes, f.restype = args, restype
        functions[name] = f

    def mappings():
        raw = Path('/proc/self/maps').read_bytes()
        need(len(raw) <= 2 * 1024**2, 'bounded mappings')
        rows = []
        for line in raw.decode().splitlines():
            cols = line.split(None, 5)
            if len(cols) != 6 or not cols[5].startswith('/'):
                continue
            name = cols[5]
            need(not name.endswith(' (deleted)'), 'no deleted mapped input')
            if 'x' not in cols[1]:
                continue
            resolved = str(Path(name).resolve(strict=True))
            need(resolved == library or resolved in plan['mapped_elf_inputs'], 'only pinned executable mappings')
            pin = seal['pin'] if resolved == library else plan['inputs'][resolved]
            checked(resolved, pin)
            rows.append({'start': int(cols[0].split('-')[0], 16),
                         'end': int(cols[0].split('-')[1], 16), 'path': resolved})
        need(any(x['path'] == library for x in rows), 'diagnostic ELF actually mapped')
        for name, f in functions.items():
            address = C.cast(f, C.c_void_p).value
            need(any(x['path'] == library and x['start'] <= address < x['end'] for x in rows), 'symbol in new ELF')
        return rows

    mapped_before = mappings()
    snapshot_words = U * 4
    def snapshot():
        data = snapshot_words()
        functions['uf_diagnostic_snapshot'](data)
        return {'fe_round': data[0], 'fe_standard_sticky': data[1],
                'mxcsr': data[2], 'mxcsr_controls': data[2] & ~63,
                'mxcsr_sticky': data[2] & 63, 'mxcsr_denormal_operand': (data[2] >> 1) & 1,
                'x87_control': data[3]}

    def environment():
        need(functions['gdn_vector16_environment']() == 0, 'legacy RNE/FTZ/DAZ admission')
        need(functions['uf_diagnostic_environment']() == 0, 'additional diagnostic masked traps')

    def retained(before, after):
        for key in ('fe_round', 'fe_standard_sticky', 'mxcsr_controls', 'x87_control'):
            need(before[key] == after[key], 'original standard flags/control preservation')
        # Bit 1 is DE, not FE_ALL_EXCEPT. Record it; never silently clear it.
        # Per-unit sticky distribution is reported, not an extra legacy promise.

    environment()
    initial_environment = snapshot()
    cases, by_id = [], {}
    for row in table['finite_single_lane_cases']:
        op, a, b = row['op'], int(row['a'], 16), int(row['b'], 16)
        expected, spec_flags = (reference.mul if op else reference.add)(a, b)
        need(expected == int(row['expected_value'], 16) and spec_flags == row['hardfloat_source_spec_flags'], 'independent Fraction matches fixed derivation')
        va, vb, out, flags = U(a), U(b), U(0xDEADBEEF), U(0xDEADBEEF)
        environment()
        before = snapshot()
        actual = functions['gdn_vector16_trace'](op, C.byref(va), C.byref(vb), C.byref(out), 1, C.byref(flags))
        after = snapshot()
        retained(before, after)
        need(actual >= 0 and actual == flags.value == row['cpp_postfix_flags_source_prediction'] and
             out.value == expected and va.value == a and vb.value == b, 'original primitive bits/postfix flags')
        raw_out = U(0xDEADBEEF)
        raw_before = snapshot()
        host_flags = functions['uf_diagnostic_raw'](op, a, b, C.byref(raw_out))
        raw_after = snapshot()
        retained(raw_before, raw_after)
        need(host_flags >= 0 and host_flags <= 31 and raw_out.value == expected and
             (host_flags & ~2) == (actual & ~2), 'separate raw expression bits/non-UF flags')
        observed = {'id': row['id'], 'op': op, 'a': row['a'], 'b': row['b'],
                    'value': f'{out.value:08x}', 'cpp_postfix_flags': actual,
                    'cpp_fatal30': bool(actual & 30), 'fraction_value': f'{expected:08x}',
                    'hardfloat_source_spec_flags': spec_flags, 'hardfloat_spec_fatal30': bool(spec_flags & 30),
                    'flags_differ': actual != spec_flags, 'raw_separate_expression_flags': host_flags,
                    'before_original': before, 'after_original': after,
                    'before_raw_probe': raw_before, 'after_raw_probe': raw_after}
        need(observed['flags_differ'] == row['expected_flags_difference'], 'explicit flags contract difference')
        cases.append(observed)
        by_id[row['id']] = row
    batches = []
    for row in table['native_batch_policy_cases']:
        pair = by_id[row['reuse_case']]
        va, vb, acc = U(int(pair['a'], 16)), U(int(pair['b'], 16)), U(int(row['acc'], 16))
        out, lane, issues = U(0xDEADBEEF), U(0xDEADBEEF), (I * 2)(-999, -999)
        environment()
        before = snapshot()
        stages = functions['gdn_vector16_mul_add_policy_trace'](C.byref(va), C.byref(vb), C.byref(acc),
            C.byref(out), 1, C.byref(lane), issues, 30)
        after = snapshot()
        retained(before, after)
        need(stages == row['cpp_stage_prediction'] and list(issues) == row['cpp_issue_flags_prediction'], 'real original mask30 stop/continue')
        need(vb.value == int(pair['expected_value'], 16), 'in-place rounded product')
        if stages == 1:
            need(out.value == 0xDEADBEEF and lane.value == issues[0], 'Add genuinely unexecuted output sentinel')
        else:
            value, add_flags = reference.add(vb.value, acc.value)
            need(out.value == value and issues[1] == lane.value == add_flags, 'separate executed Add')
        batches.append({'id': row['id'], 'stages': stages, 'issue_flags': list(issues),
                        'product': f'{vb.value:08x}', 'output_storage': f'{out.value:08x}',
                        'output_valid': stages == 2, 'final_lane_flags': lane.value,
                        'hardfloat_spec_mul_fatal': row['hardfloat_spec_mul_fatal'],
                        'before': before, 'after': after})
    environment()
    final_environment = snapshot()
    mapped_after = mappings()
    need(mapped_after == mapped_before and loaded == [library], 'loaded identity stable')
    checked(library, seal['pin'])
    result = {'status': 'PASS_ORIGINAL_CPP_SOFTWARE_DIAGNOSTIC_ONLY', 'cases': cases, 'batches': batches,
              'single_lane_cases': 24, 'batch_policy_cases': 3, 'library': seal,
              'initial_environment': initial_environment, 'final_environment': final_environment,
              'executable_mappings': mapped_after, 'HardFloat_executed': False, 'RTL_executed': False,
              'raw_host_flags_are_separate_probe': True, 'old_cpp_source_modified': False,
              'future_integration_flags_blocker_remains': True,
              'flags_difference_case_ids': [x['id'] for x in cases if x['flags_differ']]}
    target = Path(plan['work']) / 'NATIVE_RESULT.json'
    raw = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
    need(len(raw) < 256 * 1024, 'bounded diagnostic result')
    with target.open('xb') as f:
        f.write(raw)
    print(json.dumps({'status': result['status'], 'cases': 24, 'batches': 3,
                      'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}), flush=True)


if __name__ == '__main__':
    main()
