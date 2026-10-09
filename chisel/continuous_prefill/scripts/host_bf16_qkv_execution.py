#!/usr/bin/env python3
"""Independent artifact/physical-memory checks for actual Host QKV execution.

The C++ PASS marker is insufficient: reconstruct every ACKed physical write,
check per-completion writable snapshots, all final DDR bytes, each role's raw
actual/reference/frozen terminal files, and four separate native thresholds.
This module never builds or runs anything merely by being imported.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import subprocess
import sys
import numpy as np
from host_bf16_qkv_descriptor import COLUMNS, ROLES, parse_host_qkv_descriptor, validate_qkv_bindings
from pack_host_bf16_qkv_fixture import ROOT, fixture_input_hashes
from verify_host_bf16_qkv_fixture import verify

BUILD_STATUS = 'BUILT_HOST_QKV_PROJECTIONS_ONLY_NOT_NUMERICAL_PASS'
MODES = ('pass', 'last-write-error', 'activation-read-error', 'weight-read-error', 'output-alias', 'reset-recovery')
PREFIX = 'HOST_BF16_QKV_'
SCHEMA = {
    'BEGIN': 'run mode commands epoch',
    'WRITE_REQUEST': 'run pc cycle address bytes final',
    'WRITE_ACK': 'run pc cycle address bytes error final',
    'COMPLETION_HOLD': 'run pc cycle word',
    'COMMAND': 'run cycle role pc status signal write_ack_bytes published previous_outputs_preserved guards_unchanged',
    'NATIVE': 'run stage elements bit_differences max_abs mean_abs gate',
    'PASS': 'run scope commands tokens token_base checked_bf16 canonical_bit_differences independent_terminal_checked native_operator_gate cycles write_ack_bytes metadata_reads logical_matrix_engines physical_matrix_slices idma_instances unchanged_guards prior_outputs_preserved delayed_final_ack_commands completion_backpressure_commands norm_supported rope_supported full_block_supported',
    'FAULT_PASS': 'run mode failed_pc status successful_commands write_ack_bytes published_bytes failed_command_published_bytes previous_outputs_preserved guards_unchanged',
    'END': 'run status result_epoch result_pc completions successful issued_jobs metadata_reads read_beats read_ack_beats write_beats write_ack_beats published_bytes reset_required',
    'RESET_RECOVERY_PASS': 'same_dut unchanged_input_constants expected_output_injection commands',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _layout(fixture):
    lines = (fixture / 'launch.txt').read_text().splitlines()
    require(len(lines) == 5 and lines[0] == 'HOST_QKV_PROJECTION_V1', 'launch format')
    names = 'base limit cb cl commands db dl descriptors meta scratch aa rows first count independent'.split()
    values = list(map(int, lines[1].split()))
    require(len(values) == len(names), 'launch header size')
    layout = dict(zip(names, values))
    require(layout['commands'] == 3 and layout['descriptors'] == 63, 'QKV command inventory')
    fields = 'role n weight output records wait signal destination_root'.split()
    specs = [dict(zip(fields, map(int, line.split()))) for line in lines[2:]]
    require(all(len(line.split()) == len(fields) for line in lines[2:]), 'launch role fields')
    command_bytes = (fixture / 'host_commands.bin').read_bytes()
    descriptor_bytes = (fixture / 'host_descriptors.bin').read_bytes()
    records = {i: int.from_bytes(descriptor_bytes[i*16:(i+1)*16], 'little') for i in range(layout['descriptors'])}
    bindings = [parse_host_qkv_descriptor(int.from_bytes(command_bytes[i*16:(i+1)*16], 'little'), records) for i in range(3)]
    validate_qkv_bindings(bindings)
    for index, (spec, binding) in enumerate(zip(specs, bindings)):
        require(spec == dict(role=index, n=binding.n, weight=binding.weight_ddr, output=binding.output_ddr,
                            records=21, wait=index, signal=index+1, destination_root=index*21+18), 'launch/descriptor binding')
        require((binding.rows, binding.token_base, binding.token_count, binding.activation_ddr) ==
                (layout['rows'], layout['first'], layout['count'], layout['aa']), 'launch activation/window binding')
        spec['begin'] = binding.job['dst']
        spec['bytes'] = binding.job['writeBytes']
        spec['end'] = spec['begin'] + spec['bytes']
    return layout, specs


def _initial(fixture, layout, specs, mode):
    memory = bytearray(bytes.fromhex('3cc35aa5') * ((layout['limit']-layout['base'])//4))
    def load(name, address, size):
        data = (fixture/name).read_bytes()
        require(len(data) == size and layout['base'] <= address and address+size <= layout['limit'], 'input physical allocation')
        offset = address-layout['base']; memory[offset:offset+size] = data
    load('host_commands.bin', layout['cb'], layout['cl']-layout['cb'])
    load('host_descriptors.bin', layout['db'], layout['dl']-layout['db'])
    load('activation.bf16le', layout['aa'], layout['rows']*2048)
    for role, spec in zip(ROLES, specs):
        load('weight_'+role+'.bf16le', spec['weight'], 1024*spec['n']*2)
    if mode == 'output-alias':
        q, k = specs[:2]
        address = q['begin']-layout['first']*k['n']*2
        offset = layout['db']+k['destination_root']*16-layout['base']
        memory[offset+7:offset+13] = (address & ((1<<48)-1)).to_bytes(6, 'little')
        memory[offset+15] = address >> 48
    return memory


def _events(log):
    events = []
    for line in Path(log).read_text().splitlines():
        if not line.startswith(PREFIX):
            continue
        tokens = line.split(); kind = tokens[0][len(PREFIX):]
        require(kind in SCHEMA, 'unknown/failure driver event: '+kind)
        fields = [token.split('=', 1) for token in tokens[1:]]
        require(all(len(pair) == 2 for pair in fields), 'malformed driver event')
        data = dict(fields)
        require(len(data) == len(fields) and set(data) == set(SCHEMA[kind].split()), 'duplicate/unknown/missing event fields: '+kind)
        events.append((kind, data))
    require(events, 'missing driver events')
    return events


def _expect(data, **expected):
    require(all(data.get(key) == str(value) for key, value in expected.items()), 'event value drift: '+repr(expected))


def _native_metrics(actual, native, n, count, role):
    a = np.frombuffer(actual, dtype='<u2').reshape(count, n)
    b = np.frombuffer(native, dtype='<u2').reshape(count, n)
    def one(x, y):
        af = (x.astype('<u4') << 16).view('<f4').astype(np.float64)
        bf = (y.astype('<u4') << 16).view('<f4').astype(np.float64)
        error = np.abs(af-bf)
        require(np.isfinite(error).all(), 'nonfinite native output')
        maximum, mean = float(error.max()), float(error.mean())
        return dict(elements=int(x.size), bit_differences=int(np.count_nonzero(x != y)), max_abs=maximum, mean_abs=mean,
                    gate='PASS' if maximum <= .03125 and mean <= .005 else 'FAIL')
    if role == 'q':
        a, b = a.reshape(count, 8, 512), b.reshape(count, 8, 512)
        return dict(q_content=one(a[..., :256], b[..., :256]), q_gate=one(a[..., 256:], b[..., 256:]))
    return {role: one(a, b)}


def verify_execution(fixture, outputs, log, mode, *, session=None, reference_session=None):
    fixture, outputs, log = map(Path, (fixture, outputs, log))
    require(mode in MODES, 'unknown execution mode')
    admitted = verify(fixture, session=session, reference_session=reference_session)
    manifest = json.loads((fixture/'manifest.json').read_text())
    layout, specs = _layout(fixture)
    events = _events(log); cursor = 0; reports = []
    modes = [mode, 'pass'] if mode == 'reset-recovery' else [mode]
    for run_id, run_mode in enumerate(modes):
        directory = outputs if run_id == 0 else outputs/'recovery'
        require(directory.is_dir() and not directory.is_symlink(), 'missing actual output directory')
        expected = _initial(fixture, layout, specs, run_mode)
        references, actuals, metrics = {}, {}, {}
        for role, spec in zip(ROLES, specs):
            references[role] = (directory/('reference_'+role+'.bf16le')).read_bytes()
            actuals[role] = (directory/('actual_'+role+'.bf16le')).read_bytes()
            require(len(references[role]) == len(actuals[role]) == spec['bytes'], 'role output length')
            if layout['independent']:
                require(references[role] == (fixture/('independent_'+role+'.bf16le')).read_bytes(), 'frozen independent terminal mismatch: '+role)
        require(cursor < len(events) and events[cursor][0] == 'BEGIN', 'missing/duplicate BEGIN')
        _expect(events[cursor][1], run=run_id, mode=run_mode, commands=3, epoch=9+run_id); cursor += 1
        failed_pc = 1 if run_mode == 'output-alias' else 0 if run_mode == 'reset-recovery' else 2
        successful = 3 if run_mode == 'pass' else failed_pc
        expected_completions = 3 if run_mode == 'pass' else failed_pc+1
        pc=0; pending=None; last_cycle=-1; ack_bytes=[0]*3; requested=[[] for _ in range(3)]
        final_acks=[0]*3; holds=[0]*3; last_hold_cycle=[-1]*3; held_word=None; error_acks=0; snapshots={}; end=None; summary=None; native_events={}
        while cursor < len(events):
            kind, data = events[cursor]; cursor += 1
            require(kind not in ('BEGIN', 'RESET_RECOVERY_PASS'), 'missing END before new run')
            _expect(data, run=run_id)
            if kind in ('WRITE_REQUEST', 'WRITE_ACK', 'COMPLETION_HOLD', 'COMMAND'):
                require(pc < expected_completions and int(data['pc']) == pc, 'missing/duplicate/out-of-order command event')
                cycle = int(data['cycle']); require(cycle >= last_cycle, 'event cycle reversal'); last_cycle = cycle
            if kind == 'WRITE_REQUEST':
                require(pending is None and held_word is None, 'overlapping write or write before held completion acceptance')
                spec=specs[pc]; address=int(data['address']); size=int(data['bytes'])
                require(address%64 == 0 and size%64 == 0 and 0 < size <= 1024 and spec['begin'] <= address < address+size <= spec['end'], 'write physical window/beat bound')
                require((address & 4095)+size <= 4096, 'write burst crosses 4K boundary')
                require(all(address+size <= lo or hi <= address for lo, hi in requested[pc]), 'duplicate/overlapping physical write')
                _expect(data, final=int(address+size == spec['end']))
                require(run_mode != 'output-alias' or pc == 0, 'alias command issued a physical write')
                requested[pc].append((address,address+size)); pending=data
            elif kind == 'WRITE_ACK':
                require(pending is not None, 'ACK without actual write request')
                for key in ('pc','address','bytes','final'):
                    require(data[key] == pending[key], 'ACK/request identity mismatch')
                require(int(data['cycle']) > int(pending['cycle']), 'early write ACK')
                if data['final'] == '1':
                    require(int(data['cycle'])-int(pending['cycle']) >= 53, 'final ACK delay not exercised')
                require(data['error'] in ('0','1'), 'invalid ACK error flag')
                address, size = int(data['address']), int(data['bytes']); spec = specs[pc]
                if data['error'] == '1':
                    require(run_mode == 'last-write-error' and pc == 2 and data['final'] == '1' and error_acks == 0, 'unexpected/repeated write fault')
                    error_acks += 1
                else:
                    offset=address-layout['base']; source=address-spec['begin']
                    expected[offset:offset+size] = references[ROLES[pc]][source:source+size]
                    ack_bytes[pc] += size; final_acks[pc] += data['final'] == '1'
                pending = None
            elif kind == 'COMPLETION_HOLD':
                require(pending is None, 'completion exposed before write ACK')
                require(cycle > last_hold_cycle[pc], 'duplicate/non-increasing completion hold cycle')
                last_hold_cycle[pc]=cycle
                ok=pc < successful; status=0 if ok else 9 if run_mode == 'output-alias' else 3
                word=int(data['word']); expected_word=pc | 2 << 29 | status << 32 | (pc+1) << 40
                require(word == expected_word and (held_word is None or held_word == word), 'held completion identity changed')
                if ok:
                    require(ack_bytes[pc] == specs[pc]['bytes'] and final_acks[pc] == 1, 'completion visible before final ACK')
                held_word=word; holds[pc]+=1
            elif kind == 'COMMAND':
                require(pending is None and holds[pc] >= 11, 'publication before ACK/completion backpressure coverage')
                require(cycle > last_hold_cycle[pc], 'completion accepted before the held cycle ended')
                ok=pc < successful; status=0 if ok else 9 if run_mode == 'output-alias' else 3
                _expect(data, role=ROLES[pc], status=status, signal=pc+1, write_ack_bytes=ack_bytes[pc], published=int(ok), previous_outputs_preserved=1, guards_unchanged=1)
                if ok:
                    require(ack_bytes[pc] == specs[pc]['bytes'] and final_acks[pc] == 1, 'successful completion before exact final ACK')
                elif run_mode != 'last-write-error':
                    require(ack_bytes[pc] == 0 and not requested[pc], 'read/alias fault changed failed output')
                else:
                    require(error_acks == 1 and ack_bytes[pc] < specs[pc]['bytes'] and sum(hi-lo for lo,hi in requested[pc]) == specs[pc]['bytes'], 'final-write fault ACK scope')
                snapshot = directory/('writable_after_command'+str(pc)+'.bin')
                require(snapshot.read_bytes() == expected[layout['scratch']-layout['base']:], 'physical coexistence/guard snapshot mismatch at command '+str(pc))
                snapshots[snapshot.name]=sha(snapshot); pc+=1; held_word=None
            elif kind == 'NATIVE':
                require(run_mode == 'pass' and pc == 3 and summary is None and data['stage'] not in native_events, 'native event out of scope/repeated')
                require(data['stage'] in ('q_content','q_gate','k','v'), 'unknown native comparison')
                native_events[data['stage']]=data
            elif kind in ('PASS','FAULT_PASS'):
                require(summary is None and pc == expected_completions and pending is None, 'premature/duplicate summary')
                require(kind == ('PASS' if run_mode == 'pass' else 'FAULT_PASS'), 'wrong result kind')
                summary=data
            elif kind == 'END':
                require(summary is not None and pending is None and pc == expected_completions, 'early/missing result termination')
                end=data; break
            else:
                raise ValueError('unexpected event '+kind)
        require(end is not None, 'missing END')
        published=sum(specs[i]['bytes'] for i in range(successful)); metadata=sum(1+specs[i]['records'] for i in range(expected_completions))
        status=0 if run_mode == 'pass' else 9 if run_mode == 'output-alias' else 3
        _expect(end, status=status, result_epoch=9+run_id, result_pc=expected_completions-1,
                completions=expected_completions, successful=successful,
                issued_jobs=1 if run_mode == 'output-alias' else expected_completions, metadata_reads=metadata,
                published_bytes=published, reset_required=int(run_mode != 'pass'))
        require(int(end['read_beats']) == int(end['read_ack_beats']) >= metadata and
                int(end['write_beats']) == int(end['write_ack_beats']) == sum(hi-lo for spans in requested for lo,hi in spans)//64, 'ACK beat accounting')
        final = directory/'ddr_after.bin'
        require(final.read_bytes() == expected, 'final physical DDR/source/guard/output mismatch')
        for index, (role, spec) in enumerate(zip(ROLES, specs)):
            offset=spec['begin']-layout['base']
            require(actuals[role] == expected[offset:offset+spec['bytes']], 'actual role file not actual physical DDR')
            if index < successful:
                require(actuals[role] == references[role], 'canonical actual/reference mismatch: '+role)
        if run_mode == 'pass':
            for role, spec in zip(ROLES,specs):
                native=(fixture/('native_'+role+'.bf16le')).read_bytes()
                start=layout['first']*spec['n']*2
                metrics.update(_native_metrics(actuals[role],native[start:start+spec['bytes']],spec['n'],layout['count'],role))
            require(set(native_events) == set(metrics), 'missing native comparisons')
            for stage, result in metrics.items():
                observed=native_events[stage]
                _expect(observed, elements=result['elements'], bit_differences=result['bit_differences'], gate=result['gate'])
                for key in ('max_abs','mean_abs'):
                    require(math.isfinite(float(observed[key])) and math.isclose(float(observed[key]),result[key],rel_tol=1e-12,abs_tol=1e-15), 'native metric not actual raw output')
                require(result['gate'] == 'PASS', 'unchanged native operator threshold failed: '+stage)
            _expect(summary, scope='PROJECTION_ONLY', commands=3, tokens=layout['count'], token_base=layout['first'],
                    checked_bf16=layout['count']*sum(COLUMNS), canonical_bit_differences=0, independent_terminal_checked=layout['independent'],
                    native_operator_gate='PASS', write_ack_bytes=sum(ack_bytes), metadata_reads=metadata, logical_matrix_engines=1,
                    physical_matrix_slices=8, idma_instances=1, unchanged_guards=1, prior_outputs_preserved=1,
                    delayed_final_ack_commands=3, completion_backpressure_commands=3, norm_supported=0, rope_supported=0, full_block_supported=0)
            require(int(summary['cycles']) > 0, 'missing actual cycles')
        else:
            _expect(summary, mode=run_mode, failed_pc=failed_pc, status=status, successful_commands=successful,
                    write_ack_bytes=sum(ack_bytes), published_bytes=published, failed_command_published_bytes=0,
                    previous_outputs_preserved=1, guards_unchanged=1)
            require(not native_events, 'fault run claimed native pass')
        expected_files = {'ddr_after.bin'} | {prefix+role+'.bf16le' for role in ROLES for prefix in ('actual_','reference_')} | set(snapshots)
        actual_files={p.name for p in directory.iterdir() if p.is_file()}
        expected_dirs={'recovery'} if mode == 'reset-recovery' and run_id == 0 else set()
        require(actual_files == expected_files and {p.name for p in directory.iterdir() if p.is_dir()} == expected_dirs
                and all(not p.is_symlink() for p in directory.iterdir()), 'output artifact inventory drift')
        reports.append(dict(run=run_id, mode=run_mode, status=status, successful_commands=successful,
            write_ack_bytes=sum(ack_bytes), published_bytes=published, metadata_reads=metadata, native=metrics,
            actual_sha256={role:sha(directory/('actual_'+role+'.bf16le')) for role in ROLES},
            reference_sha256={role:sha(directory/('reference_'+role+'.bf16le')) for role in ROLES},
            ddr_after_sha256=sha(final), writable_snapshot_sha256=snapshots,
            physical_ddr_bytes_checked=len(expected), physical_write_requests=sum(map(len,requested)),
            readonly_and_guard_bytes_checked=len(expected)-sum(ack_bytes), independent_terminal_checked=bool(layout['independent'])))
    if mode == 'reset-recovery':
        require(cursor < len(events) and events[cursor][0] == 'RESET_RECOVERY_PASS', 'missing same-DUT reset result')
        _expect(events[cursor][1], same_dut=1, unchanged_input_constants=1, expected_output_injection=0, commands=3); cursor+=1
    require(cursor == len(events), 'unexpected/duplicate trailing execution event')
    return dict(status='PASS_HOST_QKV_ARTIFACT_CHECK_ONLY' if layout['independent'] else 'PASS_C_ONLY_HOST_QKV_ARTIFACT_DIAGNOSTIC',
                actual_dut_identity_verified=False, numerical_acceptance_eligible=bool(layout['independent']),
                scope='PROJECTION_ONLY', mode=mode, runs=reports,
                fixture_sha256=sha(fixture/'manifest.json'), log_sha256=sha(log),
                input_sha256=fixture_input_hashes(fixture,manifest), source_admission=admitted,
                native_full_block_failures=manifest['native_full_block_failures'])


def verify_all_build_sources(build, log_name='final_source_verify.log'):
    ready=json.loads((build/'build_ready.json').read_text())
    require(sha(build/'sources.sha256.json') == ready['source_manifest_sha256'], 'built source-manifest identity drift')
    with (build/log_name).open('w') as log:
        subprocess.run([sys.executable,str(ROOT/'chisel/continuous_prefill/scripts/production_source_identity.py'),
                        'verify',str(ROOT),str(build),ready['hardfloat_source']], stdout=log,stderr=subprocess.STDOUT,check=True)


def _build_identity(build):
    ready=json.loads((build/'build_ready.json').read_text())
    require(ready['status'] == BUILD_STATUS and ready['numerical_pass'] is False,'expected QKV build-only receipt')
    executable=build/'obj/VHostBlockTop'; rtl=build/'generated/HostBlockTop.sv'
    require(sha(executable) == ready['binary_sha256'] and sha(rtl) == ready['rtl_sha256'], 'DUT binary/RTL identity drift')
    require(sha(build/'sources.sha256.json') == ready['source_manifest_sha256'], 'built source-manifest identity drift')
    files=(executable,rtl,build/'build_ready.json',build/'sources.sha256.json',build/'hardfloat.sha256.json')
    return {str(path):sha(path) for path in files}


def run_case(build, fixture, mode='pass', session=None, *, label=None, reference_session=None):
    """Run one bounded actual case with before/after source, binary and RTL binding.

    A single case result does not claim complete fault coverage or full128.
    """
    build,fixture=Path(build),Path(fixture)
    require(mode in MODES, 'unknown actual driver case')
    label=mode if label is None else label
    require(type(label) is str and label and all(c.isalnum() or c in '_-' for c in label), 'invalid output label')
    admission=verify(fixture,session=session,reference_session=reference_session)
    from host_bf16_qkv_reference import independent_admitted
    require(independent_admitted(admission),
            'BLOCKED_INDEPENDENT_TERMINALS_REQUIRED: C-only diagnostics are not numerical acceptance')
    identity=_build_identity(build)
    verify_all_build_sources(build,label+'_initial_source_verify.log')
    output=build/label; log=build/(label+'.log')
    require(not output.exists() and not log.exists(), 'execution evidence must be fresh')
    with log.open('w') as stream:
        process=subprocess.run([str(build/'obj/VHostBlockTop'),str(fixture),str(output),mode],stdout=stream,stderr=subprocess.STDOUT,timeout=1800)
    (build/(label+'.exit')).write_text(str(process.returncode)+'\n')
    require(process.returncode == 0,'production Host QKV execution failed: '+mode)
    result=verify_execution(fixture,output,log,mode,session=session,reference_session=reference_session)
    require(_build_identity(build) == identity,'DUT or build receipt changed during execution')
    verify_all_build_sources(build,label+'_final_source_verify.log')
    result.update(status='PASS_PRODUCTION_HOST_QKV_CASE',actual_dut_identity_verified=True,
                  binary_sha256=identity[str(build/'obj/VHostBlockTop')],rtl_sha256=identity[str(build/'generated/HostBlockTop.sv')],
                  build_ready_sha256=identity[str(build/'build_ready.json')],source_immutability_verified=True)
    (build/(label+'.result.json')).write_text(json.dumps(result,indent=2)+'\n')
    return result


def run_representative(build, fixture, session=None, *, modes=MODES, reference_session=None):
    """Explicit execution entrypoint. Build-only receipts never mean numerical PASS."""
    build,fixture=Path(build),Path(fixture)
    require(tuple(modes) == MODES, 'representative acceptance requires every fault/reset mode')
    admitted=verify(fixture,session=session,reference_session=reference_session)
    executable=build/'obj/VHostBlockTop'; rtl=build/'generated/HostBlockTop.sv'
    identity=_build_identity(build)
    verify_all_build_sources(build,'initial_execution_source_verify.log')
    results={}
    for mode in modes:
        results[mode]=run_case(build,fixture,mode,session,reference_session=reference_session)
    verify(fixture,session=session,reference_session=reference_session)
    require(all(sha(Path(path)) == digest for path,digest in identity.items()),'DUT changed during execution')
    verify_all_build_sources(build)
    report=dict(status='PASS_PRODUCTION_HOST_QKV_PROJECTIONS_ONLY',scope='PROJECTION_ONLY',
                experimental_default_off=True,norm_supported=False,rope_supported=False,full_block_supported=False,
                actual_host_root=True,logical_matrix_engines=1,physical_matrix_slices=8,pinned_idma_instances=1,
                binary_sha256=identity[str(executable)],rtl_sha256=identity[str(rtl)],source_immutability_verified=True,
                cases=results,source_admission=admitted)
    (build/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('fixture','outputs','log'): parser.add_argument(name,type=Path)
    parser.add_argument('mode',choices=MODES)
    args=parser.parse_args()
    print(json.dumps(verify_execution(args.fixture,args.outputs,args.log,args.mode),indent=2))
